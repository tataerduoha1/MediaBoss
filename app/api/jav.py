"""JAV API：影片列表/详情/手动刮削。"""
import os

from .. import db, util
from ..httpd import ApiError, json_ok, router


def _jav_slim(j: dict, v: dict) -> dict:
    return {
        "id": j["id"], "video_id": j["video_id"], "code": j["code"],
        "title": j["title"], "cn_title": j["cn_title"],
        "release_date": j["release_date"], "duration_sec": j["duration_sec"],
        "cover_url": f"/api/videos/{j['video_id']}/cover" if j["cover_path"] else "",
        "thumb_url": f"/api/videos/{j['video_id']}/thumbnail",
        "score": j["score"], "bought": j["bought"],
        "actresses": [], "studio": "", "series": "",
        "size": v.get("size"), "play_count": v.get("play_count"),
        "watched": v.get("watched"), "favorite": v.get("favorite"),
        "rating": v.get("rating"), "resume_position": v.get("resume_position"),
        "scrape_status": v.get("scrape_status"), "ext": v.get("ext"),
    }


@router.get("/jav")
def list_jav(req):
    q = req.query
    where, vals = ["1=1"], []
    if kw := q.get("q", "").strip():
        like = f"%{kw}%"
        where.append("(j.code LIKE ? OR j.title LIKE ? OR j.cn_title LIKE ? OR j.id IN"
                     " (SELECT ja.jav_id FROM jav_actresses ja JOIN actresses a ON a.id=ja.actress_id WHERE a.name LIKE ?))")
        vals += [like, like, like, like]
    if actress_id := q.get("actress_id"):
        where.append("j.id IN (SELECT jav_id FROM jav_actresses WHERE actress_id=?)")
        vals.append(int(actress_id))
    if studio_id := q.get("studio_id"):
        where.append("j.studio_id=?")
        vals.append(int(studio_id))
    if series_id := q.get("series_id"):
        where.append("j.series_id=?")
        vals.append(int(series_id))
    if genre_id := q.get("genre_id"):
        where.append("j.id IN (SELECT jav_id FROM jav_genres WHERE genre_id=?)")
        vals.append(int(genre_id))
    if fav := q.get("favorite"):
        where.append("v.favorite=?")
        vals.append(int(fav))
    if watched := q.get("watched"):
        where.append("v.watched=?")
        vals.append(int(watched))
    if bought := q.get("bought"):
        where.append("j.bought=?")
        vals.append(int(bought))
    if q.get("unscraped"):
        where.append("v.scrape_status=2")
    if prefix := q.get("prefix", "").strip():
        if prefix == "0-9":
            where.append("substr(j.code,1,1) BETWEEN '0' AND '9'")
        elif prefix == "#":
            where.append("substr(upper(j.code),1,1) NOT BETWEEN 'A' AND 'Z'"
                         " AND substr(j.code,1,1) NOT BETWEEN '0' AND '9'")
        else:
            where.append("upper(substr(j.code,1,1))=?")
            vals.append(prefix.upper()[:1])

    seed = 0
    if q.get("sort") == "random":
        try:
            seed = int(q.get("seed", "0")) % 100000 or 7919
        except ValueError:
            seed = 7919
    sort_map = {
        "created": "v.created_at", "date": "j.release_date", "score": "j.score",
        "rating": "v.rating", "play_count": "v.play_count", "code": "j.code",
        "size": "v.size", "duration": "v.duration",
    }
    if q.get("sort") == "random":
        sort_col = f"(j.id * {seed}) % 104729"  # 带种子的确定性伪随机
    else:
        sort_col = sort_map.get(q.get("sort", "created"), "v.created_at")
    order = "DESC" if q.get("order", "desc") == "desc" else "ASC"
    page = max(1, int(q.get("page", 1)))
    page_size = min(200, max(10, int(q.get("page_size", db.get_setting("page_size", "60")))))
    offset = (page - 1) * page_size

    base = ("FROM jav j JOIN videos v ON v.id=j.video_id WHERE " + " AND ".join(where))
    d = db.db()
    total = d.scalar(f"SELECT COUNT(*) {base}", vals)
    rows = d.query(
        f"SELECT j.*, v.size, v.play_count, v.watched, v.favorite, v.rating, v.resume_position,"
        f" v.scrape_status, v.ext {base} ORDER BY {sort_col} {order} LIMIT ? OFFSET ?",
        (*vals, page_size, offset))
    # 批量取演员名（避免 N+1）
    ids = [r["id"] for r in rows]
    actress_map = {}
    if ids:
        marks = ",".join("?" for _ in ids)
        for r in d.query(
            f"SELECT ja.jav_id, a.id AS actress_id, a.name, a.avatar_path FROM jav_actresses ja"
            f" JOIN actresses a ON a.id=ja.actress_id WHERE ja.jav_id IN ({marks})", ids):
            actress_map.setdefault(r["jav_id"], []).append(
                {"id": r["actress_id"], "name": r["name"], "avatar_path": r["avatar_path"]})
    studio_map = {r["id"]: r["name"] for r in d.query("SELECT id, name FROM studios")}
    series_map = {r["id"]: r["name"] for r in d.query("SELECT id, name FROM series")}
    items = []
    for r in rows:
        item = _jav_slim(r, r)
        item["actresses"] = actress_map.get(r["id"], [])
        item["studio"] = studio_map.get(r["studio_id"], "")
        item["series"] = series_map.get(r["series_id"], "")
        items.append(item)
    return json_ok({"items": items, "total": total, "page": page, "page_size": page_size,
                    "has_more": offset + len(rows) < total})


@router.get("/jav/{jid}")
def jav_detail(req):
    jid = int(req.params["jid"])
    d = db.db()
    j = d.query_one(
        "SELECT j.*, s.name AS studio, s.id AS studio_id, se.name AS series, se.id AS series_id"
        " FROM jav j LEFT JOIN studios s ON s.id=j.studio_id LEFT JOIN series se ON se.id=j.series_id"
        " WHERE j.id=?", (jid,))
    if not j:
        raise ApiError(404, "JAV 不存在")
    v = d.query_one("SELECT * FROM videos WHERE id=?", (j["video_id"],)) or {}
    j["actresses"] = d.query(
        "SELECT a.id, a.name, a.avatar_path FROM actresses a"
        " JOIN jav_actresses ja ON ja.actress_id=a.id WHERE ja.jav_id=?", (jid,))
    j["genres"] = [r["name"] for r in d.query(
        "SELECT g.name FROM genres g JOIN jav_genres jg ON jg.genre_id=g.id WHERE jg.jav_id=?", (jid,))]
    j["cover_url"] = f"/api/videos/{j['video_id']}/cover" if j["cover_path"] else ""
    # 同系列/同女优推荐
    related = []
    if j.get("studio_id"):
        related = d.query(
            "SELECT j2.id, j2.code, j2.title, j2.video_id, j2.cover_path FROM jav j2"
            " WHERE j2.id!=? AND (j2.studio_id=? OR j2.id IN"
            " (SELECT jav_id FROM jav_actresses WHERE actress_id IN"
            "  (SELECT actress_id FROM jav_actresses WHERE jav_id=?)))"
            " ORDER BY j2.release_date DESC LIMIT 12",
            (jid, j["studio_id"] or -1, jid))
        for r in related:
            r["cover_url"] = f"/api/videos/{r['video_id']}/cover" if r["cover_path"] else ""
    return json_ok({"jav": j, "video": v, "related": related})


@router.patch("/jav/{jid}")
def update_jav(req):
    jid = int(req.params["jid"])
    body = req.json
    fields, vals = [], []
    for k in ("title", "cn_title", "bought", "score", "release_date", "director"):
        if k in body:
            fields.append(f"{k}=?")
            vals.append(body[k])
    if fields:
        fields.append("updated_at=?")
        vals.extend([util.now(), jid])
        db.db().execute(f"UPDATE jav SET {', '.join(fields)} WHERE id=?", vals)
    return json_ok()


@router.post("/jav/{jid}/rescrape")
def jav_rescrape(req):
    from ..services import scraper
    scraper.rescrape_jav(int(req.params["jid"]))
    return json_ok({"message": "已加入刮削队列"})


@router.delete("/jav/{jid}")
def jav_delete(req):
    """解除 JAV 关联（保留视频记录）。"""
    jid = int(req.params["jid"])
    db.db().execute("DELETE FROM jav WHERE id=?", (jid,))
    return json_ok()
