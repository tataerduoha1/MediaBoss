"""下载 API：磁力提交、任务列表/删除。"""
import time

from .. import db
from ..httpd import ApiError, json_ok, router
from ..services import downloads


@router.get("/downloads")
def list_downloads(req):
    rows = db.db().query("SELECT * FROM downloads ORDER BY created_at DESC LIMIT 200")
    return json_ok(rows)


@router.post("/downloads/magnet")
def submit_magnet(req):
    url = str(req.json.get("url", "")).strip()
    if not url:
        raise ApiError(400, "缺少磁力链接或 URL")
    save_dir = str(req.json.get("save_dir", ""))
    r = downloads.add_magnet(url, save_dir)
    if not r.get("ok"):
        raise ApiError(400, r.get("error", "提交失败"))
    return json_ok(r)


@router.post("/downloads/refresh")
def refresh(req):
    n = downloads.refresh_tasks()
    return json_ok({"synced": n})


@router.delete("/downloads/{did}")
def delete_download(req):
    db.db().execute("DELETE FROM downloads WHERE id=?", (int(req.params["did"]),))
    return json_ok()


@router.post("/downloads/{did}/clear")
def clear_done(req):
    db.db().execute("DELETE FROM downloads WHERE status='done'")
    return json_ok()
