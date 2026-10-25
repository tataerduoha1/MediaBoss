"""设置 API：分组读写 + 女优头像。"""
import os
import time

from .. import config, db
from ..httpd import ApiError, Response, json_ok, router
from ..services import scanner
from ..services import scraper
from ..services import thumbs

SAFE_KEYS = {
    "scan_interval_min", "auto_scan", "jav_mode", "scrape_enabled",
    "scrape_provider_order", "translate_enabled", "proxy", "ffmpeg_path", "mpv_path",
    "thumb_workers", "sprite_enabled", "lan_access", "cd2_url", "cd2_user", "cd2_pass",
    "download_dir", "organize_template", "hide_watched", "page_size",
    "scrape_retry_cooldown_min", "theme",
}


@router.get("/settings")
def get_settings(req):
    s = db.all_settings()
    for k in ("password_hash", "password_salt", "password"):
        s.pop(k, None)
    return json_ok(s)


@router.put("/settings")
def put_settings(req):
    body = req.json
    changed = []
    for k, v in body.items():
        if k not in SAFE_KEYS:
            continue
        db.set_setting(k, str(v))
        changed.append(k)
    # 特定变更即时生效
    if "thumb_workers" in changed:
        thumbs.start()
    if any(k in changed for k in ("scan_interval_min", "auto_scan")):
        scanner.wake()
    return json_ok({"changed": changed})


@router.post("/settings/rescan")
def rescan(req):
    scanner.request_manual()
    return json_ok()


@router.get("/actresses/{aid}/avatar")
def actress_avatar(req):
    a = db.db().query_one("SELECT avatar_path FROM actresses WHERE id=?", (int(req.params["aid"]),))
    if not a or not a["avatar_path"] or not os.path.isfile(a["avatar_path"]):
        raise ApiError(404, "头像不存在")
    with open(a["avatar_path"], "rb") as f:
        return Response(200, f.read(), "image/jpeg", {"Cache-Control": "public, max-age=86400"})
