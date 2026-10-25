"""目录管理 API。"""
import os
import time

from .. import db, util
from ..httpd import ApiError, json_ok, router
from ..services import scanner


@router.get("/directories")
def list_dirs(req):
    rows = db.db().query(
        "SELECT d.*, (SELECT COUNT(*) FROM videos v WHERE v.dir_id=d.id) AS video_count,"
        " (SELECT COUNT(*) FROM jav j JOIN videos v2 ON v2.id=j.video_id WHERE v2.dir_id=d.id) AS jav_count"
        " FROM directories d ORDER BY d.id")
    return json_ok(rows)


@router.post("/directories")
def add_dir(req):
    path = util.norm_path(str(req.json.get("path", "")).strip())
    if not os.path.isdir(path):
        raise ApiError(400, f"目录不存在: {path}")
    cur = db.db().execute("INSERT OR IGNORE INTO directories(path, created_at) VALUES(?,?)",
                          (path, time.time()))
    if cur.lastrowid == 0:
        raise ApiError(409, "目录已存在")
    scanner.request_manual()
    return json_ok({"id": cur.lastrowid, "path": path})


@router.patch("/directories/{did}")
def update_dir(req):
    did = int(req.params["did"])
    body = req.json
    fields, vals = [], []
    if "enabled" in body:
        fields.append("enabled=?")
        vals.append(1 if body["enabled"] else 0)
    if "mode" in body:
        fields.append("mode=?")
        vals.append(str(body["mode"]))
    if "path" in body:
        p = util.norm_path(str(body["path"]).strip())
        if not os.path.isdir(p):
            raise ApiError(400, f"目录不存在: {p}")
        fields.append("path=?")
        vals.append(p)
    if fields:
        vals.append(did)
        db.db().execute(f"UPDATE directories SET {', '.join(fields)} WHERE id=?", vals)
    return json_ok()


@router.delete("/directories/{did}")
def delete_dir(req):
    did = int(req.params["did"])
    d = db.db()
    d.execute("DELETE FROM videos WHERE dir_id=?", (did,))
    d.execute("DELETE FROM directories WHERE id=?", (did,))
    scanner.wake()
    return json_ok()


@router.post("/directories/scan")
def manual_scan(req):
    scanner.request_manual()
    return json_ok({"message": "已触发手动扫描"})
