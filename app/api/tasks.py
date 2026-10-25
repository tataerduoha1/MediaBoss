"""任务状态 / 观看历史 / 统计 API。"""
import time

from .. import db, util
from ..httpd import json_ok, router
from ..services import downloads, scanner, scraper, thumbs


@router.get("/tasks/status")
def task_status(req):
    return json_ok({
        "scan": scanner.status(),
        "scrape": scraper.status(),
        "thumb_queue": thumbs.queue_size(),
        "download": downloads.status(),
    })


@router.get("/history")
def history(req):
    page = max(1, int(req.query.get("page", 1)))
    page_size = min(100, max(10, int(req.query.get("page_size", 50))))
    offset = (page - 1) * page_size
    d = db.db()
    total = d.scalar("SELECT COUNT(*) FROM watch_history")
    rows = d.query(
        "SELECT h.id, h.started_at, h.seconds, v.id AS video_id, v.title, v.filename,"
        " j.code, j.cover_path FROM watch_history h"
        " JOIN videos v ON v.id=h.video_id LEFT JOIN jav j ON j.video_id=v.id"
        " ORDER BY h.started_at DESC LIMIT ? OFFSET ?", (page_size, offset))
    for r in rows:
        r["cover_url"] = f"/api/videos/{r['video_id']}/cover" if r.get("cover_path") else ""
        r["started_at_fmt"] = time.strftime("%Y-%m-%d %H:%M", time.localtime(r["started_at"]))
    return json_ok({"items": rows, "total": total, "page": page, "page_size": page_size})


@router.delete("/history/{vid}")
def history_delete_one(req):
    vid = int(req.params["vid"])
    db.db().execute("DELETE FROM watch_history WHERE video_id=?", (vid,))
    return json_ok()


@router.post("/history/batch-delete")
def history_batch_delete(req):
    ids = [int(i) for i in (req.json.get("video_ids") or [])]
    if not ids:
        return json_ok({"deleted": 0})
    d = db.db()
    marks = ",".join("?" for _ in ids)
    cur = d.execute(f"DELETE FROM watch_history WHERE video_id IN ({marks})", ids)
    return json_ok({"deleted": cur.rowcount})


@router.delete("/history")
def history_clear(req):
    cur = db.db().execute("DELETE FROM watch_history")
    return json_ok({"deleted": cur.rowcount})


@router.get("/stats")
def stats(req):
    d = db.db()
    total_videos = d.scalar("SELECT COUNT(*) FROM videos")
    total_size = d.scalar("SELECT COALESCE(SUM(size),0) FROM videos")
    total_duration = d.scalar("SELECT COALESCE(SUM(duration),0) FROM videos")
    total_jav = d.scalar("SELECT COUNT(*) FROM jav")
    scraped = d.scalar("SELECT COUNT(*) FROM jav WHERE title!=''")
    watched = d.scalar("SELECT COUNT(*) FROM videos WHERE watched=1")
    play_count = d.scalar("SELECT COALESCE(SUM(play_count),0) FROM videos")
    top_actresses = d.query(
        "SELECT id, name, avatar_path, video_count FROM actresses ORDER BY video_count DESC LIMIT 8")
    top_studios = d.query("SELECT id, name, video_count FROM studios ORDER BY video_count DESC LIMIT 8")
    recent = d.query(
        "SELECT v.id, v.title, v.created_at, j.code, j.cover_path FROM videos v"
        " LEFT JOIN jav j ON j.video_id=v.id ORDER BY v.created_at DESC LIMIT 8")
    for r in recent:
        r["cover_url"] = f"/api/videos/{r['id']}/cover" if r.get("cover_path") else ""
    week = time.time() - 7 * 86400
    week_plays = d.scalar("SELECT COUNT(*) FROM watch_history WHERE started_at>?", (week,))
    return json_ok({
        "total_videos": total_videos, "total_size": total_size,
        "total_size_h": util.human_size(total_size),
        "total_duration": total_duration,
        "total_duration_h": util.human_duration(total_duration),
        "total_jav": total_jav, "scraped": scraped, "watched": watched,
        "play_count": play_count, "week_plays": week_plays,
        "top_actresses": [{"id": r["id"], "name": r["name"],
                           "avatar_url": f"/api/actresses/{r['id']}/avatar" if r["avatar_path"] else "",
                           "count": r["video_count"]} for r in top_actresses],
        "top_studios": top_studios, "recent": recent,
    })
