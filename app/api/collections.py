"""片单/合集 API：CRUD + 条目管理。"""
import time

from .. import db
from ..httpd import ApiError, json_ok, router


def _coll_slim(c: dict, d) -> dict:
    count = d.scalar("SELECT COUNT(*) FROM collection_items WHERE collection_id=?", (c["id"],))
    cover_vid = c["cover_video_id"]
    if not cover_vid:
        cover_vid = d.scalar(
            "SELECT video_id FROM collection_items WHERE collection_id=? ORDER BY added_at DESC LIMIT 1",
            (c["id"],))
    return {"id": c["id"], "name": c["name"], "description": c["description"],
            "count": count, "cover_video_id": cover_vid, "created_at": c["created_at"]}


@router.get("/collections")
def list_collections(req):
    d = db.db()
    rows = d.query("SELECT * FROM collections ORDER BY sort DESC, created_at DESC")
    return json_ok({"items": [_coll_slim(c, d) for c in rows]})


@router.post("/collections")
def create_collection(req):
    name = str(req.json.get("name", "")).strip()[:80]
    if not name:
        raise ApiError(400, "片单名称不能为空")
    cur = db.db().execute(
        "INSERT INTO collections(name, description, created_at) VALUES(?,?,?)",
        (name, str(req.json.get("description", ""))[:300], time.time()))
    return json_ok({"id": cur.lastrowid, "name": name})


@router.patch("/collections/{cid}")
def update_collection(req):
    cid = int(req.params["cid"])
    d = db.db()
    if not d.query_one("SELECT id FROM collections WHERE id=?", (cid,)):
        raise ApiError(404, "片单不存在")
    body = req.json
    fields, vals = [], []
    for k in ("name", "description", "cover_video_id", "sort"):
        if k in body:
            fields.append(f"{k}=?")
            vals.append(body[k])
    if fields:
        vals.append(cid)
        d.execute(f"UPDATE collections SET {', '.join(fields)} WHERE id=?", vals)
    return json_ok()


@router.delete("/collections/{cid}")
def delete_collection(req):
    cid = int(req.params["cid"])
    db.db().execute("DELETE FROM collections WHERE id=?", (cid,))
    return json_ok()


@router.get("/collections/{cid}")
def collection_detail(req):
    cid = int(req.params["cid"])
    d = db.db()
    c = d.query_one("SELECT * FROM collections WHERE id=?", (cid,))
    if not c:
        raise ApiError(404, "片单不存在")
    items = d.query(
        "SELECT v.id AS video_id, j.id AS jid, j.code, j.title, j.cn_title, j.cover_path,"
        " v.duration, v.size, v.watched, v.favorite, ci.added_at"
        " FROM collection_items ci JOIN videos v ON v.id=ci.video_id"
        " LEFT JOIN jav j ON j.video_id=v.id WHERE ci.collection_id=?"
        " ORDER BY ci.added_at DESC", (cid,))
    for it in items:
        it["cover_url"] = f"/api/videos/{it['video_id']}/cover" if it["cover_path"] else ""
        it["thumb_url"] = f"/api/videos/{it['video_id']}/thumbnail"
    return json_ok({"collection": _coll_slim(c, d), "items": items})


@router.post("/collections/{cid}/items")
def add_item(req):
    cid = int(req.params["cid"])
    vid = int(req.json.get("video_id", 0))
    d = db.db()
    if not d.query_one("SELECT id FROM collections WHERE id=?", (cid,)):
        raise ApiError(404, "片单不存在")
    if not d.query_one("SELECT id FROM videos WHERE id=?", (vid,)):
        raise ApiError(404, "视频不存在")
    d.execute(
        "INSERT INTO collection_items(collection_id, video_id, added_at) VALUES(?,?,?)"
        " ON CONFLICT(collection_id, video_id) DO NOTHING", (cid, vid, time.time()))
    return json_ok()


@router.delete("/collections/{cid}/items/{vid}")
def remove_item(req):
    cid, vid = int(req.params["cid"]), int(req.params["vid"])
    db.db().execute("DELETE FROM collection_items WHERE collection_id=? AND video_id=?", (cid, vid))
    return json_ok()


@router.get("/videos/{vid}/collections")
def video_collections(req):
    """查询某视频已加入的片单 id 集合（加入片单弹窗用）。"""
    vid = int(req.params["vid"])
    rows = db.db().query(
        "SELECT collection_id FROM collection_items WHERE video_id=?", (vid,))
    return json_ok({"ids": [r["collection_id"] for r in rows]})
