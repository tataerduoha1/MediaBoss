"""数据管理 API：数据字典（类型/作用/位置/大小）、清除、维护（VACUUM）、工厂重置。

数据分层模型：
  长期数据  —— 用户资产与索引，清除会丢功能数据：数据库、截图、ffmpeg 工具
  缓存数据  —— 可由源文件/网络重建：封面、头像、缩略图、雪碧图
  临时数据  —— 运行痕迹，可随时清理：日志、cache 目录
"""
import os
import shutil
import time

from .. import config, db, util
from ..httpd import ApiError, json_ok, router


def _dir_stats(path: str) -> tuple[int, int]:
    total = count = 0
    if not os.path.isdir(path):
        return 0, 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
                count += 1
            except OSError:
                pass
    return total, count


def _entry(key, name, typ, role, path, clearable, clear_note, rebuild="") -> dict:
    size, count = _dir_stats(path) if os.path.isdir(path) else (0, 0)
    if key == "db":
        size = 0
        for ext in ("", "-wal", "-shm"):
            p = config.cfg().db_path + ext
            if os.path.isfile(p):
                size += os.path.getsize(p)
        d = db.db()
        count = d.scalar("SELECT COUNT(*) FROM videos")
    return {
        "key": key, "name": name, "type": typ, "role": role,
        "path": path, "size": size, "size_h": util.human_size(size),
        "count": count, "clearable": clearable, "clear_note": clear_note,
        "rebuild": rebuild,
    }


def data_dict() -> list[dict]:
    c = config.cfg()
    d = db.db()
    scraped = d.scalar("SELECT COUNT(*) FROM jav WHERE cover_path!=''")
    avatars = d.scalar("SELECT COUNT(*) FROM actresses WHERE avatar_path!=''")
    return [
        _entry("db", "SQLite 数据库", "长期", 
               "全部结构化数据：视频索引、JAV 元数据、演员/厂商/系列/类别、观看历史、设置、会话。",
               c.db_path, False, "不可直接删除；可做 VACUUM 压缩，或用工厂重置清空",
               "数据丢失不可重建（元数据可重新刮削）"),
        _entry("covers", "封面与头像", "缓存",
               f"影片封面 {scraped} 张、演员头像 {avatars} 张。清除后界面无图，下次刮削自动重新下载。",
               c.cover_dir, True, "清除后所有封面/头像丢失，需重新刮削或手动更新恢复",
               "重新刮削（增量/全量更新）自动重建"),
        _entry("thumbs", "视频缩略图", "缓存",
               "无封面视频的列表缩略图（ffmpeg 从视频截取）。",
               c.thumb_dir, True, "清除后视频库缩略图暂缺，自动排队重新生成",
               "后台 ffmpeg 自动重建"),
        _entry("sprites", "进度条雪碧图", "缓存",
               "播放页进度条悬停预览图（10x10 缩略帧拼图）。",
               c.sprite_dir, True, "清除后播放页悬停无预览，自动排队重新生成",
               "后台 ffmpeg 自动重建"),
        _entry("screenshots", "用户截图", "长期",
               "播放时手动截图保存的画面（用户资产，请谨慎清除）。",
               c.shot_dir, True, "清除后截图永久丢失，不可恢复", "不可恢复"),
        _entry("cache", "网络缓存", "临时",
               "刮削过程的临时文件与下载中间产物。",
               c.cache_dir, True, "随时可安全清除", "按需自动重建"),
        _entry("logs", "运行日志", "临时",
               "服务运行日志（mediaboss.log），用于排查问题。",
               c.log_dir, True, "随时可安全清除；当前日志会被清空重写", "持续写入"),
        _entry("bin", "工具目录", "长期",
               "ffmpeg / ffprobe 可执行文件（自动下载安装）。",
               c.bin_dir, False, "不可清除，删除后缩略图/截图不可用，需重新安装 ffmpeg",
               "设置页可重新下载"),
    ]


@router.get("/data/dict")
def get_dict(req):
    d = db.db()
    counts = {
        "videos": d.scalar("SELECT COUNT(*) FROM videos"),
        "jav": d.scalar("SELECT COUNT(*) FROM jav"),
        "scraped": d.scalar("SELECT COUNT(*) FROM jav WHERE title!=''"),
        "actresses": d.scalar("SELECT COUNT(*) FROM actresses"),
        "genres": d.scalar("SELECT COUNT(*) FROM genres"),
        "studios": d.scalar("SELECT COUNT(*) FROM studios"),
        "series": d.scalar("SELECT COUNT(*) FROM series"),
        "history": d.scalar("SELECT COUNT(*) FROM watch_history"),
        "pending": d.scalar("SELECT COUNT(*) FROM videos WHERE scrape_status=0"),
        "failed": d.scalar("SELECT COUNT(*) FROM videos WHERE scrape_status=2"),
        "no_code": d.scalar("SELECT COUNT(*) FROM videos WHERE scrape_status=3"),
    }
    db_size = 0
    for ext in ("", "-wal", "-shm"):
        p = config.cfg().db_path + ext
        if os.path.isfile(p):
            db_size += os.path.getsize(p)
    return json_ok({"entries": data_dict(), "counts": counts, "db_size": db_size,
                    "db_size_h": util.human_size(db_size)})


CLEAR_HANDLERS = {}


def _clear_handler(*targets):
    def deco(fn):
        for t in targets:
            CLEAR_HANDLERS[t] = fn
        return fn
    return deco


def _wipe_dir(path: str, keep: set[str] = frozenset()) -> int:
    n = 0
    if not os.path.isdir(path):
        return 0
    for name in os.listdir(path):
        if name in keep:
            continue
        p = os.path.join(path, name)
        try:
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            else:
                os.remove(p)
                n += 1
        except OSError:
            pass
    return n


@_clear_handler("covers")
def _clear_covers():
    n = _wipe_dir(config.cfg().cover_dir)
    d = db.db()
    d.execute("UPDATE jav SET cover_path=''")
    d.execute("UPDATE actresses SET avatar_path=''")
    return n, "封面与头像已清除，重新刮削后自动下载"


@_clear_handler("thumbs")
def _clear_thumbs():
    n = _wipe_dir(config.cfg().thumb_dir)
    db.db().execute("UPDATE videos SET thumb_status=0")
    from ..services import thumbs
    thumbs.enqueue_pending()
    return n, "缩略图已清除，后台自动重新生成"


@_clear_handler("sprites")
def _clear_sprites():
    n = _wipe_dir(config.cfg().sprite_dir)
    # 已有缩略图的标记为待重建（不会再重复生成海报，只补雪碧图）
    db.db().execute("UPDATE videos SET thumb_status=0 WHERE thumb_status=1")
    from ..services import thumbs
    thumbs.enqueue_pending()
    return n, "雪碧图已清除，后台自动重新生成"


@_clear_handler("cache")
def _clear_cache():
    n = _wipe_dir(config.cfg().cache_dir)
    return n, "缓存已清除"


@_clear_handler("logs")
def _clear_logs():
    log_dir = config.cfg().log_dir
    cur = os.path.join(log_dir, "mediaboss.log")
    n = _wipe_dir(log_dir, keep={"mediaboss.log"})
    try:  # 当前日志文件被占用，改为截断
        if os.path.isfile(cur):
            with open(cur, "w", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} 日志已清空\n")
    except OSError:
        pass
    return n, "日志已清空"


@_clear_handler("screenshots")
def _clear_shots():
    n = _wipe_dir(config.cfg().shot_dir)
    db.db().execute("UPDATE bookmarks SET image_path=''")
    return n, "截图文件已清除（截图记录保留）"


@_clear_handler("history")
def _clear_history():
    d = db.db()
    n = d.scalar("SELECT COUNT(*) FROM watch_history")
    d.execute("DELETE FROM watch_history")
    return n, "观看历史已清空"


@router.post("/data/clear")
def clear(req):
    targets = req.json.get("targets") or []
    if not targets:
        raise ApiError(400, "未指定清除目标")
    unknown = [t for t in targets if t not in CLEAR_HANDLERS]
    if unknown:
        raise ApiError(400, f"未知目标: {', '.join(unknown)}")
    results = {}
    for t in targets:
        n, msg = CLEAR_HANDLERS[t]()
        results[t] = {"count": n, "msg": msg}
        util.logger().info("清除数据: %s (%d 项)", t, n)
    return json_ok({"results": results})


@router.post("/data/optimize")
def optimize(req):
    """压缩数据库：WAL 截断 + VACUUM + ANALYZE。"""
    d = db.db()
    before = 0
    for ext in ("", "-wal", "-shm"):
        p = config.cfg().db_path + ext
        if os.path.isfile(p):
            before += os.path.getsize(p)
    try:
        d.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        d._conn().execute("VACUUM")
        d._conn().execute("ANALYZE")
    except Exception as e:  # noqa: BLE001
        raise ApiError(500, f"优化失败: {e}")
    after = os.path.getsize(config.cfg().db_path) if os.path.isfile(config.cfg().db_path) else 0
    util.logger().info("数据库优化: %s -> %s", util.human_size(before), util.human_size(after))
    return json_ok({"before": before, "after": after,
                    "before_h": util.human_size(before), "after_h": util.human_size(after)})


@router.post("/data/reset-scrape")
def reset_scrape(req):
    """仅重置刮削状态（不动任何文件），之后可手动发起全量/增量更新。"""
    d = db.db()
    n = d.scalar("SELECT COUNT(*) FROM videos WHERE scrape_status!=0")
    d.execute("UPDATE videos SET scrape_status=0, scrape_attempts=0, next_retry_at=0")
    return json_ok({"reset": n})


@router.post("/data/factory-reset")
def factory_reset(req):
    """工厂重置：清空数据库全部业务数据与缓存文件，恢复初始状态（密码重置为 admin）。

    保留：ffmpeg 工具（bin/）、config.toml。删除：所有库表数据、封面/头像、
    缩略图/雪碧图、缓存、日志、截图。用于迁移服务器前导出干净环境或彻底重新开始。
    """
    if str(req.json.get("confirm", "")).upper() != "RESET":
        raise ApiError(400, "请在请求体中携带 confirm:\"RESET\" 以确认操作")
    d = db.db()
    # 禁用外键后按依赖倒序清空所有业务表
    d._conn().execute("PRAGMA foreign_keys=OFF")
    for t in ("jav_actresses", "jav_genres", "video_tags", "jav", "actresses", "genres",
              "studios", "series", "tags", "bookmarks", "watch_history", "downloads",
              "videos", "directories", "sessions", "api_tokens", "settings"):
        d.execute(f"DELETE FROM {t}")
    d._conn().execute("PRAGMA foreign_keys=ON")
    c = config.cfg()
    removed = sum(_wipe_dir(p) for p in (c.cover_dir, c.thumb_dir, c.sprite_dir,
                                         c.cache_dir, c.shot_dir))
    _wipe_dir(c.log_dir, keep={"mediaboss.log"})
    util.logger().warning("工厂重置完成: 清除文件 %d 个，数据库已清空", removed)
    return json_ok({"ok": True, "removed_files": removed,
                    "note": "已恢复初始状态，密码重置为 admin，请重新登录并添加媒体目录"})
