"""系统 API：信息/统计/ffmpeg 安装/备份恢复/版本检查。"""
import json
import os
import platform
import shutil
import sqlite3
import sys
import tempfile
import time
import urllib.request
import zipfile
from io import BytesIO

from .. import config, db, util
from ..httpd import ApiError, Response, json_ok, router
from ..services import ffmpegtool

GITHUB_LATEST = "https://api.github.com/repos/tataerduoha1/MediaBoss/releases/latest"


@router.get("/system/ping")
def ping(req):
    return json_ok({"pong": True, "version": config.VERSION})


@router.get("/system/info")
def info(req):
    d = db.db()
    db_size = 0
    try:
        db_size = os.path.getsize(config.cfg().db_path) if os.path.isfile(config.cfg().db_path) else 0
    except OSError:
        pass
    return json_ok({
        "app": config.APP_NAME, "version": config.VERSION,
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "db_size": db_size,
        "ffmpeg": ffmpegtool.ffmpeg_status(),
        "mpv": ffmpegtool.mpv_status(),
        "lan_access": db.get_setting("lan_access", "0") == "1",
        "host": util.local_ip(),
        "port": config.cfg().port,
    })


@router.post("/system/ffmpeg/install")
def install_ffmpeg(req):
    r = ffmpegtool.download_ffmpeg()
    if r.get("ok"):
        # 安装后重试缩略图队列
        from ..services import thumbs
        thumbs.enqueue_pending()
        return json_ok(r)
    raise ApiError(500, f"ffmpeg 安装失败: {r.get('error', '')}")


@router.post("/system/detect")
def detect_tools(req):
    from ..services import thumbs
    ffmpegtool.detect_ffmpeg(force=True)
    thumbs.enqueue_pending()
    return json_ok({"ffmpeg": ffmpegtool.ffmpeg_status(), "mpv": ffmpegtool.mpv_status()})


# ============ A8 版本更新检查（私有仓库匿名 404 时优雅降级） ============

def _parse_ver(v: str):
    try:
        return tuple(int(x) for x in v.lstrip("v").split("."))
    except (ValueError, AttributeError):
        return None


@router.get("/system/check-update")
def check_update(req):
    current = config.VERSION
    try:
        r = urllib.request.Request(GITHUB_LATEST, headers={
            "User-Agent": "MediaBoss", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(r, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        reason = "仓库私有或尚未发布 Release，无法在线检查" if getattr(e, "code", None) == 404 \
            else f"网络不可达: {e.__class__.__name__}"
        util.logger().info("检查更新失败: %s", reason)
        return json_ok({"current": current, "latest": "", "has_update": False,
                        "available": False, "reason": reason})
    latest = (data.get("tag_name") or "").lstrip("v")
    cur_t, new_t = _parse_ver(current), _parse_ver(latest)
    has_update = bool(new_t and cur_t and new_t > cur_t)
    return json_ok({
        "current": current, "latest": latest, "has_update": has_update, "available": True,
        "name": data.get("name") or "", "notes": (data.get("body") or "")[:2000],
        "url": data.get("html_url") or "",
        "published_at": (data.get("published_at") or "")[:10],
    })


# ============ A4 备份 / 恢复 ============

_BACKUP_META = "mediaboss.json"


@router.get("/system/backup")
def backup(req):
    """导出全量备份 zip：数据库快照 + 封面头像 + 自定义海报 + 备份元信息。"""
    c = config.cfg()
    d = db.db()
    # WAL checkpoint 后快照数据库（sqlite backup API 输出一致的静态副本）
    try:
        d.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except Exception:  # noqa: BLE001
        pass
    snap = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    snap.close()
    try:
        src = d._conn()
        dst = sqlite3.connect(snap.name)
        with dst:
            src.backup(dst)
        dst.close()
        ver = sqlite3.connect(snap.name).execute("PRAGMA user_version").fetchone()[0]
        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            meta = {"app": config.APP_NAME, "version": config.VERSION,
                    "schema_version": ver, "created_at": time.time(),
                    "video_count": d.scalar("SELECT COUNT(*) FROM videos")}
            zf.writestr(_BACKUP_META, json.dumps(meta, ensure_ascii=False))
            zf.write(snap.name, "mediaboss.db")
            for label, path in (("covers", c.cover_dir), ("custom", os.path.join(c.thumb_dir, "custom"))):
                if not os.path.isdir(path):
                    continue
                for root, _, files in os.walk(path):
                    for f in files:
                        full = os.path.join(root, f)
                        arc = os.path.join(label, os.path.relpath(full, path))
                        try:
                            zf.write(full, arc)
                        except OSError:
                            pass
        util.logger().info("导出备份: videos=%d schema=v%d", meta["video_count"], ver)
        return Response(200, buf.getvalue(), "application/zip",
                        {"Content-Disposition":
                         f'attachment; filename="mediaboss_backup_{time.strftime("%Y%m%d_%H%M%S")}.zip"'})
    finally:
        try:
            os.remove(snap.name)
        except OSError:
            pass


@router.post("/system/restore")
def restore(req):
    """从备份 zip 恢复（整库覆盖）。body 原始 zip 字节，query/头携带 confirm=RESTORE。"""
    if str(req.query.get("confirm", "")).upper() != "RESTORE":
        raise ApiError(400, "请在 URL 上携带 ?confirm=RESTORE 以确认恢复操作")
    body = req.body
    if not body or len(body) < 100:
        raise ApiError(400, "备份文件为空")
    try:
        zf = zipfile.ZipFile(BytesIO(body))
    except zipfile.BadZipFile:
        raise ApiError(400, "不是合法的备份 zip 文件")
    if "mediaboss.db" not in zf.namelist():
        raise ApiError(400, "备份缺少数据库文件")
    meta = {}
    if _BACKUP_META in zf.namelist():
        try:
            meta = json.loads(zf.read(_BACKUP_META).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            pass
    c = config.cfg()
    d = db.db()
    cur_ver = d._conn().execute("PRAGMA user_version").fetchone()[0]
    bak_ver = int(meta.get("schema_version", cur_ver) or cur_ver)
    if bak_ver > cur_ver:
        raise ApiError(400, f"备份 schema 版本 (v{bak_ver}) 高于当前程序 (v{cur_ver})，请先升级 MediaBoss")
    # 1) 恢复数据库：从备份 db 覆盖当前整库（事务性）
    snap = tempfile.mkdtemp(suffix="_restore")
    db_path = os.path.join(snap, "mediaboss.db")
    try:
        zf.extract("mediaboss.db", snap)
    except OSError:
        shutil.rmtree(snap, ignore_errors=True)
        raise ApiError(500, "解压备份失败")
    src = sqlite3.connect(db_path)
    dst = d._conn()
    try:
        dst.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        with dst:
            src.backup(dst)
        src.close()
    finally:
        shutil.rmtree(snap, ignore_errors=True)
    # 2) 恢复封面 / 自定义海报
    restored_files = 0
    for label, target in (("covers", c.cover_dir), ("custom", os.path.join(c.thumb_dir, "custom"))):
        names = [n for n in zf.namelist() if n.startswith(label + "/") and not n.endswith("/")]
        for n in names:
            rel = os.path.relpath(n, label)
            out = os.path.normpath(os.path.join(target, rel))
            if not out.startswith(os.path.normpath(target)):
                continue  # 防路径穿越
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(out, "wb") as f:
                f.write(zf.read(n))
            restored_files += 1
    # 3) 兼容旧版本备份：补跑缺失迁移
    try:
        d.migrate()
    except Exception:  # noqa: BLE001
        util.logger().exception("恢复后补迁移失败")
    util.logger().warning("恢复备份完成: schema=v%d 视频=%s 恢复文件=%d",
                          bak_ver, meta.get("video_count", "?"), restored_files)
    return json_ok({"schema_version": bak_ver, "restored_files": restored_files,
                    "video_count": meta.get("video_count"),
                    "note": "恢复完成，建议刷新页面；如界面数据未变化请重新登录"})
