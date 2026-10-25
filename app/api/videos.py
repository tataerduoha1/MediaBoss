"""视频 API：列表/详情/流媒体/缩略图/进度/收藏评分/标签/截图/整理/NFO。"""
import os
import re
import time
import xml.sax.saxutils as sx

from .. import config, db, util
from ..httpd import ApiError, Response, json_ok, router
from ..services import ffmpegtool, mpv, organize as organizer, thumbs

PLAYABLE = {".mp4": "video/mp4", ".webm": "video/webm", ".m4v": "video/mp4",
            ".mkv": "video/x-matroska", ".ts": "video/mp2t", ".mov": "video/quicktime"}


def _get_video(vid: int) -> dict:
    v = db.db().query_one("SELECT * FROM videos WHERE id=?", (vid,))
    if not v:
        raise ApiError(404, "视频不存在")
    return v


@router.get("/videos")
def list_videos(req):
    q = req.query
    where, vals = ["1=1"], []
    if kw := q.get("q", "").strip():
        where.append("(v.title LIKE ? OR v.filename LIKE ? OR j.code LIKE ? OR j.title LIKE ? OR j.cn_title LIKE ?)")
        like = f"%{kw}%"
        vals += [like, like, like, like, like]
    if dir_id := q.get("dir_id"):
        where.append("v.dir_id=?")
        vals.append(int(dir_id))
    if watched := q.get("watched"):
        where.append("v.watched=?")
        vals.append(int(watched))
    if fav := q.get("favorite"):
        where.append("v.favorite=?")
        vals.append(int(fav))
    if min_rating := q.get("min_rating"):
        where.append("v.rating>=?")
        vals.append(int(min_rating))
    if tag := q.get("tag"):
        where.append("v.id IN (SELECT video_id FROM video_tags WHERE tag_id=(SELECT id FROM tags WHERE name=?))")
        vals.append(tag)
    if ext := q.get("ext"):
        where.append("v.ext=?")
        vals.append(ext.lower())

    seed = 0
    if q.get("sort") == "random":
        try:
            seed = int(q.get("seed", "0")) % 100000 or 7919
        except ValueError:
            seed = 7919
        sort_col = f"(v.id * {seed}) % 104729"  # 带种子的确定性伪随机
    else:
        sort_map = {
            "created": "v.created_at", "mtime": "v.mtime", "size": "v.size",
            "duration": "v.duration", "rating": "v.rating", "play_count": "v.play_count",
            "last_played": "v.last_played_at", "title": "v.title COLLATE NOCASE",
        }
        sort_col = sort_map.get(q.get("sort", "created"), "v.created_at")
    order = "DESC" if q.get("order", "desc") == "desc" else "ASC"
    page = max(1, int(q.get("page", 1)))
    page_size = min(200, max(10, int(q.get("page_size", db.get_setting("page_size", "60")))))
    offset = (page - 1) * page_size

    base = ("FROM videos v LEFT JOIN jav j ON j.video_id=v.id WHERE " + " AND ".join(where))
    d = db.db()
    total = d.scalar(f"SELECT COUNT(*) {base}", vals)
    rows = d.query(
        f"SELECT v.id, v.fingerprint, v.path, v.filename, v.ext, v.size, v.duration, v.width, v.height,"
        f" v.title, v.play_count, v.last_played_at, v.resume_position, v.watched, v.rating, v.favorite,"
        f" v.thumb_status, v.scrape_status, v.created_at, v.dir_id,"
        f" j.code, j.cover_path, j.cn_title, j.release_date"
        f" {base} ORDER BY {sort_col} {order} LIMIT ? OFFSET ?", (*vals, page_size, offset))
    has_more = offset + len(rows) < total
    return json_ok({
        "items": [_slim(r) for r in rows],
        "total": total, "page": page, "page_size": page_size, "has_more": has_more,
    })


def _slim(r: dict) -> dict:
    return {
        "id": r["id"], "filename": r["filename"], "title": r["title"], "ext": r["ext"],
        "size": r["size"], "duration": r["duration"], "width": r["width"], "height": r["height"],
        "play_count": r["play_count"], "resume_position": r["resume_position"],
        "watched": r["watched"], "rating": r["rating"], "favorite": r["favorite"],
        "thumb_status": r["thumb_status"], "scrape_status": r["scrape_status"],
        "code": r.get("code") or "", "cover_path": r.get("cover_path") or "",
        "cn_title": r.get("cn_title") or "", "release_date": r.get("release_date") or "",
        "thumb_url": thumbs.thumb_url(r["id"]), "sprite_url": thumbs.sprite_url(r["id"]),
    }


@router.get("/videos/{vid}")
def video_detail(req):
    vid = int(req.params["vid"])
    v = _get_video(vid)
    d = db.db()
    jav = d.query_one(
        "SELECT j.*, s.name AS studio, se.name AS series FROM jav j"
        " LEFT JOIN studios s ON s.id=j.studio_id LEFT JOIN series se ON se.id=j.series_id"
        " WHERE j.video_id=?", (vid,)) or {}
    if jav:
        jav["actresses"] = d.query(
            "SELECT a.id, a.name, a.avatar_path FROM actresses a"
            " JOIN jav_actresses ja ON ja.actress_id=a.id WHERE ja.jav_id=?", (jav["id"],))
        jav["genres"] = [r["name"] for r in d.query(
            "SELECT g.name FROM genres g JOIN jav_genres jg ON jg.genre_id=g.id WHERE jg.jav_id=?",
            (jav["id"],))]
    tags = [r["name"] for r in d.query(
        "SELECT t.name FROM tags t JOIN video_tags vt ON vt.tag_id=t.id WHERE vt.video_id=?", (vid,))]
    history = d.query(
        "SELECT started_at, seconds FROM watch_history WHERE video_id=? ORDER BY started_at DESC LIMIT 10", (vid,))
    shots = d.query(
        "SELECT id, time_sec, note, created_at FROM bookmarks WHERE video_id=? ORDER BY time_sec", (vid,))
    return json_ok({"video": _slim(v) | {"path": v["path"], "dir_id": v["dir_id"], "codec": v["codec"],
                                          "bitrate": v["bitrate"], "mtime": v["mtime"]},
                    "jav": jav or None, "tags": tags, "history": history, "screenshots": shots})


@router.get("/videos/{vid}/stream")
def stream_video(req):
    vid = int(req.params["vid"])
    v = _get_video(vid)
    path = v["path"]
    if not os.path.isfile(path):
        raise ApiError(410, "文件不存在，请重新扫描")
    ctype = PLAYABLE.get(v["ext"], "application/octet-stream")
    size = os.path.getsize(path)
    rng = req.header("Range")
    start, end = 0, size - 1
    if rng:
        m = re.match(r"bytes=(\d*)-(\d*)", rng)
        if m:
            if m.group(1):
                start = int(m.group(1))
            if m.group(2):
                end = int(m.group(2))
            elif not m.group(1):
                end = size - 1
            else:
                end = min(size - 1, start + 4 * 1024 * 1024 - 1)
    resp = Response(200, b"", ctype, {"Accept-Ranges": "bytes"})
    resp.stream_spec = (path, start, min(end, size - 1))
    return resp


@router.get("/videos/{vid}/thumbnail")
def thumbnail(req):
    vid = int(req.params["vid"])
    p = thumbs.find_thumb(vid)
    if not p:
        raise ApiError(404, "缩略图未生成")
    with open(p, "rb") as f:
        return Response(200, f.read(), "image/jpeg", {"Cache-Control": "public, max-age=86400"})


@router.get("/videos/{vid}/sprite")
def sprite(req):
    vid = int(req.params["vid"])
    p = thumbs.find_sprite(vid)
    if not p:
        raise ApiError(404, "预览图未生成")
    with open(p, "rb") as f:
        return Response(200, f.read(), "image/jpeg", {"Cache-Control": "public, max-age=86400"})


@router.get("/videos/{vid}/cover")
def cover(req):
    vid = int(req.params["vid"])
    jav = db.db().query_one("SELECT cover_path FROM jav WHERE video_id=?", (vid,))
    if jav and jav["cover_path"] and os.path.isfile(jav["cover_path"]):
        with open(jav["cover_path"], "rb") as f:
            return Response(200, f.read(), "image/jpeg", {"Cache-Control": "public, max-age=86400"})
    # 刮削封面缺失时回退视频帧海报（ffmpeg 从视频 10% 处抽取），刮削成功后自动被真封面替代
    p = thumbs.find_thumb(vid)
    if p:
        with open(p, "rb") as f:
            return Response(200, f.read(), "image/jpeg", {"Cache-Control": "public, max-age=86400"})
    raise ApiError(404, "封面不存在")


@router.post("/videos/{vid}/progress")
def progress(req):
    vid = int(req.params["vid"])
    body = req.json
    pos = float(body.get("position", 0))
    dur = float(body.get("duration", 0))
    started = bool(body.get("started"))
    _get_video(vid)
    d = db.db()
    sets = ["resume_position=?", "updated_at=?"]
    vals = [pos, time.time()]
    if started:
        sets.append("play_count=play_count+1")
        sets.append("last_played_at=?")
        vals.append(time.time())
    if dur > 0 and pos / dur >= 0.9:
        sets.append("watched=1")
        sets.append("resume_position=0")
    vals.append(vid)
    d.execute(f"UPDATE videos SET {', '.join(sets)} WHERE id=?", vals)
    if started or dur > 0:
        # 同一视频只保留一条历史（upsert），seconds 记录最近观看位置
        d.execute(
            "INSERT INTO watch_history(video_id, started_at, seconds) VALUES(?,?,?)"
            " ON CONFLICT(video_id) DO UPDATE SET started_at=excluded.started_at, seconds=excluded.seconds",
            (vid, time.time(), pos if dur > 0 else 0))
    return json_ok()


@router.post("/videos/{vid}/mpv")
def play_mpv(req):
    vid = int(req.params["vid"])
    v = _get_video(vid)
    pos = float(req.json.get("position", v["resume_position"] or 0))
    title = v["title"]
    r = mpv.launch(v["path"], start_at=pos, title=title)
    if not r.get("ok"):
        raise ApiError(400, r.get("error", "启动失败"))
    return json_ok(r)


@router.patch("/videos/{vid}")
def update_video(req):
    vid = int(req.params["vid"])
    _get_video(vid)
    body = req.json
    fields, vals = [], []
    for k in ("title", "rating", "favorite", "watched"):
        if k in body:
            fields.append(f"{k}=?")
            vals.append(body[k])
    if fields:
        fields.append("updated_at=?")
        vals.extend([time.time(), vid])
        db.db().execute(f"UPDATE videos SET {', '.join(fields)} WHERE id=?", vals)
    return json_ok()


@router.post("/videos/{vid}/favorite")
def toggle_favorite(req):
    vid = int(req.params["vid"])
    _get_video(vid)
    db.db().execute("UPDATE videos SET favorite=1-favorite, updated_at=? WHERE id=?", (time.time(), vid))
    row = db.db().query_one("SELECT favorite FROM videos WHERE id=?", (vid,))
    return json_ok({"favorite": row["favorite"]})


@router.post("/videos/{vid}/tags")
def set_tags(req):
    vid = int(req.params["vid"])
    _get_video(vid)
    names = [str(t).strip()[:40] for t in req.json.get("tags", []) if str(t).strip()]
    d = db.db()
    d.execute("DELETE FROM video_tags WHERE video_id=?", (vid,))
    for name in names:
        # INSERT OR IGNORE 后 lastrowid 可能是连接上一次插入的旧 rowid，必须 SELECT 查回
        d.execute("INSERT OR IGNORE INTO tags(name) VALUES(?)", (name,))
        tag_id = d.scalar("SELECT id FROM tags WHERE name=?", (name,))
        d.execute("INSERT OR IGNORE INTO video_tags(video_id, tag_id) VALUES(?,?)", (vid, tag_id))
    return json_ok({"tags": names})


@router.delete("/videos/{vid}")
def delete_video(req):
    vid = int(req.params["vid"])
    v = _get_video(vid)
    delete_file = bool(req.json.get("delete_file")) if req.method != "DELETE" else False
    if delete_file and os.path.isfile(v["path"]):
        try:
            os.remove(v["path"])
        except OSError as e:
            raise ApiError(500, f"删除文件失败: {e}")
    # 清理产物
    for p in (thumbs.find_thumb(vid), thumbs.find_sprite(vid)):
        if p:
            try:
                os.remove(p)
            except OSError:
                pass
    db.db().execute("DELETE FROM videos WHERE id=?", (vid,))
    return json_ok()


@router.post("/videos/{vid}/screenshots")
def take_screenshot(req):
    vid = int(req.params["vid"])
    v = _get_video(vid)
    at = float(req.json.get("time", 0))
    if not ffmpegtool.detect_ffmpeg():
        raise ApiError(400, "ffmpeg 不可用，无法截图")
    out = os.path.join(config.cfg().shot_dir, f"v{vid}_{int(at)}.jpg")
    ok, msg = ffmpegtool.run_ffmpeg(
        ["-ss", f"{max(0, at):.2f}", "-i", v["path"], "-frames:v", "1", "-q:v", "3", out], timeout=120)
    if not ok or not os.path.isfile(out):
        raise ApiError(500, f"截图失败: {msg[-200:]}")
    cur = db.db().execute(
        "INSERT INTO bookmarks(video_id, time_sec, image_path, note, created_at) VALUES(?,?,?,?,?)",
        (vid, at, out, str(req.json.get("note", ""))[:200], time.time()))
    return json_ok({"id": cur.lastrowid, "time_sec": at, "note": req.json.get("note", ""),
                    "url": f"/api/videos/{vid}/screenshots/{cur.lastrowid}/image"})


@router.get("/videos/{vid}/screenshots/{sid}/image")
def screenshot_image(req):
    row = db.db().query_one("SELECT image_path FROM bookmarks WHERE id=? AND video_id=?",
                            (int(req.params["sid"]), int(req.params["vid"])))
    if not row or not os.path.isfile(row["image_path"]):
        raise ApiError(404, "截图不存在")
    with open(row["image_path"], "rb") as f:
        return Response(200, f.read(), "image/jpeg")


@router.delete("/videos/{vid}/screenshots/{sid}")
def delete_screenshot(req):
    sid, vid = int(req.params["sid"]), int(req.params["vid"])
    row = db.db().query_one("SELECT image_path FROM bookmarks WHERE id=? AND video_id=?", (sid, vid))
    if row and os.path.isfile(row["image_path"]):
        try:
            os.remove(row["image_path"])
        except OSError:
            pass
    db.db().execute("DELETE FROM bookmarks WHERE id=?", (sid,))
    return json_ok()


@router.post("/videos/{vid}/rescrape")
def rescrape(req):
    from ..services import scraper
    scraper.rescrape_video(int(req.params["vid"]))
    return json_ok({"message": "已加入刮削队列"})


@router.get("/videos/{vid}/nfo")
def export_nfo(req):
    vid = int(req.params["vid"])
    v = _get_video(vid)
    d = db.db()
    jav = d.query_one(
        "SELECT j.*, s.name AS studio, se.name AS series FROM jav j"
        " LEFT JOIN studios s ON s.id=j.studio_id LEFT JOIN series se ON se.id=j.series_id WHERE j.video_id=?",
        (vid,)) or {}
    actresses = d.query(
        "SELECT a.name FROM actresses a JOIN jav_actresses ja ON ja.actress_id=a.id"
        " JOIN jav j ON j.id=ja.jav_id WHERE j.video_id=?", (vid,))
    genres = d.query("SELECT g.name FROM genres g JOIN jav_genres jg ON jg.genre_id=g.id"
                     " JOIN jav j ON j.id=jg.jav_id WHERE j.video_id=?", (vid,))
    esc = sx.escape
    code = esc(jav.get("code", ""))
    lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        "<movie>", f"  <title>{esc(jav.get('title') or v['title'])}</title>",
        f"  <originaltitle>{esc(jav.get('title'))}</originaltitle>",
        f"  <sorttitle>{esc(code)}</sorttitle>", f"  <set>{esc(jav.get('series') or '')}</set>",
    ]
    if code:
        lines.append(f"  <uniqueid type=\"jav\" default=\"true\">{code}</uniqueid>")
        lines.append(f"  <studio>{code.split('-')[0]}</studio>")
    if jav.get("studio"):
        lines.append(f"  <studio>{esc(jav['studio'])}</studio>")
    if jav.get("release_date"):
        lines.append(f"  <premiered>{esc(jav['release_date'])}</premiered>")
        lines.append(f"  <year>{jav['release_date'][:4]}</year>")
    if jav.get("director"):
        lines.append(f"  <director>{esc(jav['director'])}</director>")
    if jav.get("duration_sec"):
        lines.append(f"  <runtime>{int(jav['duration_sec']) // 60}</runtime>")
    lines.append(f"  <mpaa>XXX</mpaa>")
    for a in actresses:
        lines.append(f"  <actor><name>{esc(a['name'])}</name></actor>")
    for g in genres:
        lines.append(f"  <genre>{esc(g['name'])}</genre>")
    lines.append(f"  <outline>{esc(jav.get('title') or '')}</outline>")
    lines.append("</movie>")
    return Response(200, "\n".join(lines).encode("utf-8"),
                    "application/xml; charset=utf-8",
                    {"Content-Disposition": f'attachment; filename="{util.safe_filename(code or v["filename"])}.nfo"'})


@router.post("/videos/organize/preview")
def organize_preview(req):
    ids = req.json.get("video_ids") or None
    return json_ok(organizer.preview(ids))


@router.post("/videos/organize/apply")
def organize_apply(req):
    plan = req.json.get("items", [])
    if not plan:
        raise ApiError(400, "整理计划为空")
    return json_ok(organizer.apply(plan))
