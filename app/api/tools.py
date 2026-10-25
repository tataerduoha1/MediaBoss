"""工具箱 API：海报自选抽帧、重复检测、NFO 批量导出、存储分析与孤儿缓存清理。"""
import os
import re
import time
import zipfile
from io import BytesIO

from .. import config, db, util
from ..httpd import ApiError, Response, json_ok, router
from ..services import ffmpegtool, thumbs


# ============ A2 海报自选 ============

def _frames_dir() -> str:
    p = os.path.join(config.cfg().thumb_dir, "frames")
    os.makedirs(p, exist_ok=True)
    return p


def _custom_poster(vid: int) -> str | None:
    p = os.path.join(config.cfg().thumb_dir, "custom", f"v{vid}.jpg")
    return p if os.path.isfile(p) else None


def _extract_frame(v: dict, at: float, out: str) -> bool:
    ok, _ = ffmpegtool.run_ffmpeg(
        ["-ss", f"{max(0.0, at):.2f}", "-i", v["path"], "-frames:v", "1",
         "-vf", "scale=640:-2", "-q:v", "4", out], timeout=120)
    return ok and os.path.isfile(out)


@router.get("/videos/{vid}/frames/{idx}")
def video_frame(req):
    """按 n 等分取第 idx 帧（0-based），缓存后返回 JPEG。缓存键 v{vid}_{n}_{idx}.jpg。"""
    vid, idx = int(req.params["vid"]), int(req.params["idx"])
    n = min(24, max(2, int(req.query.get("n", "8"))))
    v = db.db().query_one("SELECT path, duration FROM videos WHERE id=?", (vid,))
    if not v:
        raise ApiError(404, "视频不存在")
    if not os.path.isfile(v["path"]):
        raise ApiError(410, "文件不存在，请重新扫描")
    if not ffmpegtool.detect_ffmpeg():
        raise ApiError(400, "ffmpeg 不可用，请先在设置中安装")
    out = os.path.join(_frames_dir(), f"v{vid}_{n}_{idx}.jpg")
    if not os.path.isfile(out):
        dur = v["duration"] or 0
        at = dur * (idx + 0.5) / n if dur > 0 else 1.0
        if not _extract_frame(v, at, out + ".tmp.jpg"):
            raise ApiError(500, "抽帧失败")
        os.replace(out + ".tmp.jpg", out)
    with open(out, "rb") as f:
        return Response(200, f.read(), "image/jpeg", {"Cache-Control": "public, max-age=86400"})


@router.post("/videos/{vid}/poster")
def set_poster(req):
    """自选海报：body {n, idx} 按等分帧 或 {at} 指定秒数。写入自定义海报并接管封面。"""
    vid = int(req.params["vid"])
    v = db.db().query_one("SELECT * FROM videos WHERE id=?", (vid,))
    if not v:
        raise ApiError(404, "视频不存在")
    if not ffmpegtool.detect_ffmpeg():
        raise ApiError(400, "ffmpeg 不可用，请先在设置中安装")
    body = req.json
    if "at" in body:
        at = float(body["at"])
    else:
        n = min(24, max(2, int(body.get("n", 8))))
        at = (v["duration"] or 0) * (int(body.get("idx", 0)) + 0.5) / n
    custom_dir = os.path.join(config.cfg().thumb_dir, "custom")
    os.makedirs(custom_dir, exist_ok=True)
    out = os.path.join(custom_dir, f"v{vid}.jpg")
    if not _extract_frame(v, at, out + ".tmp.jpg"):
        raise ApiError(500, "海报生成失败")
    os.replace(out + ".tmp.jpg", out)
    # 有 JAV 记录时接管 cover_path（cover 接口优先自定义海报）
    db.db().execute("UPDATE jav SET cover_path=? WHERE video_id=?", (out, vid))
    util.logger().info("自定义海报: video=%s at=%.1fs", vid, at)
    return json_ok({"poster_url": f"/api/videos/{vid}/cover?t={int(time.time())}"})


@router.delete("/videos/{vid}/poster")
def reset_poster(req):
    vid = int(req.params["vid"])
    p = os.path.join(config.cfg().thumb_dir, "custom", f"v{vid}.jpg")
    if os.path.isfile(p):
        os.remove(p)
    # cover_path 指向自定义海报时清空，交回默认封面逻辑
    db.db().execute("UPDATE jav SET cover_path='' WHERE video_id=? AND cover_path=?", (vid, p))
    return json_ok()


# ============ A5 重复检测 ============

@router.get("/tools/duplicates")
def duplicates(req):
    d = db.db()
    groups = []
    # 1) 同番号多文件（不同路径）
    for r in d.query(
        "SELECT j.code, COUNT(*) c FROM jav j JOIN videos v ON v.id=j.video_id"
        " WHERE v.path NOT LIKE '%' GROUP BY lower(j.code) HAVING c>1 ORDER BY c DESC LIMIT 50"):
        items = d.query(
            "SELECT v.id, v.path, v.filename, v.ext, v.size, v.duration, v.created_at, j.code"
            " FROM jav j JOIN videos v ON v.id=j.video_id WHERE lower(j.code)=? ORDER BY v.size DESC",
            (r["code"],))
        groups.append({"type": "code", "label": f"同番号 {r['code']}", "items": items})
    # 2) 同大小 + 同时长（±1s）疑似重复内容
    for r in d.query(
        "SELECT v.size, CAST(v.duration AS INTEGER) dsec, COUNT(*) c FROM videos v"
        " WHERE v.size>1048576 GROUP BY v.size, dsec HAVING c>1 ORDER BY v.size DESC LIMIT 50"):
        items = d.query(
            "SELECT v.id, v.path, v.filename, v.ext, v.size, v.duration, v.created_at,"
            " j.code FROM videos v LEFT JOIN jav j ON j.video_id=v.id"
            " WHERE v.size=? AND CAST(v.duration AS INTEGER)=? ORDER BY v.size DESC",
            (r["size"], r["dsec"]))
        if len(items) > 1:
            groups.append({"type": "content", "label": f"疑似重复 · {util.human_size(r['size'])} · 约 {r['dsec']}s",
                           "items": items})
    return json_ok({"groups": groups, "total_groups": len(groups)})


# ============ A6 NFO 批量导出 ============

@router.post("/tools/export-nfo")
def export_nfo_zip(req):
    """批量导出 NFO + 封面 zip（Emby/Kodi 刮削器格式：{code}.nfo / {code}.jpg）。"""
    ids = req.json.get("video_ids") or []
    include_cover = bool(req.json.get("cover", True))
    if not ids:
        raise ApiError(400, "未选择视频")
    if len(ids) > 500:
        raise ApiError(400, "单次最多导出 500 个")
    d = db.db()
    buf = BytesIO()
    count = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        for vid in ids:
            v = d.query_one("SELECT * FROM videos WHERE id=?", (vid,))
            if not v:
                continue
            jav = d.query_one("SELECT j.*, s.name AS studio FROM jav j"
                              " LEFT JOIN studios s ON s.id=j.studio_id WHERE j.video_id=?", (vid,))
            code = (jav or {}).get("code") or os.path.splitext(v["filename"])[0]
            safe = util.safe_filename(code) or f"video{vid}"
            actresses = jav and d.query(
                "SELECT a.name FROM actresses a JOIN jav_actresses ja ON ja.actress_id=a.id"
                " WHERE ja.jav_id=?", (jav["id"],)) or []
            genres = jav and d.query(
                "SELECT g.name FROM genres g JOIN jav_genres jg ON jg.genre_id=g.id"
                " WHERE jg.jav_id=?", (jav["id"],)) or []
            nfo = _build_nfo(v, jav or {}, actresses, genres)
            zf.writestr(f"{safe}.nfo", nfo)
            count += 1
            if include_cover:
                cover_src = _cover_source(vid, jav or {})
                if cover_src:
                    try:
                        zf.write(cover_src, f"{safe}.jpg")
                    except OSError:
                        pass
    util.logger().info("批量导出 NFO: %d 个", count)
    return Response(200, buf.getvalue(), "application/zip",
                    {"Content-Disposition": f'attachment; filename="mediaboss_nfo_{count}.zip"'})


def _build_nfo(v: dict, jav: dict, actresses: list, genres: list) -> str:
    import xml.sax.saxutils as sx
    esc = sx.escape
    code = esc(jav.get("code", ""))
    lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        "<movie>", f"  <title>{esc(jav.get('title') or v['title'])}</title>",
        f"  <originaltitle>{esc(jav.get('title') or '')}</originaltitle>",
        f"  <sorttitle>{esc(code)}</sorttitle>",
        f"  <set>{esc(jav.get('series') or '')}</set>",
    ]
    if code:
        lines.append(f'  <uniqueid type="jav" default="true">{code}</uniqueid>')
        lines.append(f"  <studio>{esc(code.split('-')[0])}</studio>")
    if jav.get("studio"):
        lines.append(f"  <studio>{esc(jav['studio'])}</studio>")
    if jav.get("release_date"):
        lines.append(f"  <premiered>{esc(jav['release_date'])}</premiered>")
        lines.append(f"  <year>{jav['release_date'][:4]}</year>")
    if jav.get("director"):
        lines.append(f"  <director>{esc(jav['director'])}</director>")
    if jav.get("duration_sec"):
        lines.append(f"  <runtime>{int(jav['duration_sec']) // 60}</runtime>")
    lines.append("  <mpaa>XXX</mpaa>")
    for a in actresses:
        lines.append(f"  <actor><name>{esc(a['name'])}</name></actor>")
    for g in genres:
        lines.append(f"  <genre>{esc(g['name'])}</genre>")
    lines.append("</movie>")
    return "\n".join(lines)


def _cover_source(vid: int, jav: dict) -> str | None:
    """封面来源优先级：刮削封面 > 自定义海报 > 缩略图。"""
    cp = jav.get("cover_path")
    if cp and os.path.isfile(cp):
        return cp
    p = _custom_poster(vid)
    if p:
        return p
    return thumbs.find_thumb(vid)


# ============ A7 存储分析 ============

@router.get("/tools/storage")
def storage(req):
    d = db.db()
    dirs = d.query(
        "SELECT id, path FROM directories ORDER BY id")
    per_dir = []
    for dr in dirs:
        row = d.query_one(
            "SELECT COUNT(*) c, COALESCE(SUM(size),0) s FROM videos WHERE dir_id=?", (dr["id"],))
        exts = d.query(
            "SELECT ext, COUNT(*) c, COALESCE(SUM(size),0) s FROM videos WHERE dir_id=?"
            " GROUP BY ext ORDER BY s DESC LIMIT 6", (dr["id"],))
        per_dir.append({"id": dr["id"], "path": dr["path"], "count": row["c"],
                        "size": row["s"], "size_h": util.human_size(row["s"]),
                        "exts": [{"ext": e["ext"], "count": e["c"], "size_h": util.human_size(e["s"])} for e in exts]})
    biggest = d.query(
        "SELECT v.id, v.filename, v.size, v.duration, j.code FROM videos v"
        " LEFT JOIN jav j ON j.video_id=v.id ORDER BY v.size DESC LIMIT 20")
    # 缓存目录占用
    c = config.cfg()
    caches = {}
    for key, path in (("covers", c.cover_dir), ("thumbs", c.thumb_dir),
                      ("sprites", c.sprite_dir), ("screenshots", c.shot_dir),
                      ("cache", c.cache_dir), ("logs", c.log_dir)):
        total, count = _walk_stats(path)
        caches[key] = {"size": total, "size_h": util.human_size(total), "count": count}
    total_size = d.scalar("SELECT COALESCE(SUM(size),0) FROM videos")
    return json_ok({
        "total_size": total_size, "total_size_h": util.human_size(total_size),
        "per_dir": per_dir, "biggest": biggest, "caches": caches,
    })


def _walk_stats(path: str) -> tuple[int, int]:
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


@router.post("/tools/cleanup-orphans")
def cleanup_orphans(req):
    """清理无引用的缩略图/雪碧图/帧缓存文件（对应视频已删除的遗留缓存）。"""
    d = db.db()
    vid_ids = {str(r["id"]) for r in d.query("SELECT id FROM videos")}
    c = config.cfg()
    cleaned = 0
    pat = re.compile(r"^v(\d+)")
    for directory, sub in ((c.thumb_dir, None), (c.sprite_dir, None),
                           (os.path.join(c.thumb_dir, "frames"), None)):
        if not os.path.isdir(directory):
            continue
        for name in os.listdir(directory):
            if not name.endswith(".jpg"):
                continue
            m = pat.match(name)
            if m and m.group(1) not in vid_ids:
                try:
                    os.remove(os.path.join(directory, name))
                    cleaned += 1
                except OSError:
                    pass
    # 自定义海报目录
    custom = os.path.join(c.thumb_dir, "custom")
    if os.path.isdir(custom):
        for name in os.listdir(custom):
            m = pat.match(name)
            if m and m.group(1) not in vid_ids:
                try:
                    os.remove(os.path.join(custom, name))
                    cleaned += 1
                except OSError:
                    pass
    util.logger().info("清理孤儿缓存: %d 个文件", cleaned)
    return json_ok({"cleaned": cleaned,
                    "msg": f"已清理 {cleaned} 个无引用缓存文件"})
