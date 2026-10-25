"""下载子系统：CloudDrive2 离线下载对接（磁力 → 云端任务 → 本地目录）。"""
import base64
import hashlib
import json
import threading
import time

from .. import db, util

_started = False
_stop = threading.Event()
_cd2_token = {"value": None, "expires": 0.0}


def status() -> dict:
    configured = bool(db.get_setting("cd2_url"))
    return {"configured": configured, "running": _started}


def _url(path: str) -> str:
    base = db.get_setting("cd2_url").rstrip("/")
    return base + path


def _login() -> str | None:
    """CD2 JSON-RPC 登录，缓存 token。"""
    if _cd2_token["value"] and _cd2_token["expires"] > time.time():
        return _cd2_token["value"]
    url, user, pwd = db.get_setting("cd2_url"), db.get_setting("cd2_user"), db.get_setting("cd2_pass")
    if not url:
        return None
    if not (user or pwd):
        data = util.http_post_json(_url("/json/v1"), {"method": "ConfigList", "params": {}})
        # 免登录模式直接使用
        _cd2_token["value"] = ""
        _cd2_token["expires"] = time.time() + 1800
        return ""
    md5pwd = hashlib.md5(pwd.encode()).hexdigest() if pwd else ""
    data = util.http_post_json(_url("/json/v1"), {
        "method": "WebLogin", "params": {"username": user, "password": md5pwd}})
    if not data or data.get("ret") != 0:
        util.logger().warning("CloudDrive2 登录失败: %s", data)
        return None
    token = (data.get("value") or {}).get("accesstoken", "")
    _cd2_token["value"] = token
    _cd2_token["expires"] = time.time() + 1800
    return token


def add_magnet(url: str, save_dir: str = "") -> dict:
    """提交磁力/URL 到 CloudDrive2 离线下载。"""
    if not db.get_setting("cd2_url"):
        return {"ok": False, "error": "尚未配置 CloudDrive2，请到 下载设置 中配置"}
    token = _login()
    if token is None:
        return {"ok": False, "error": "CloudDrive2 登录失败，请检查账号配置"}
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    save_dir = save_dir or db.get_setting("download_dir") or "/"
    params = {"Urls": [url], "path": save_dir, "NoDownload": False}
    data = util.http_post_json(_url("/json/v1"),
                               {"method": "AddOfflineTask", "params": params}, headers=headers)
    if not data or data.get("ret") != 0:
        msg = (data or {}).get("error", "未知错误")
        return {"ok": False, "error": f"CD2 返回错误: {msg}"}
    name = url if not url.startswith("magnet:") else f"磁力任务 {time.strftime('%m-%d %H:%M')}"
    db.db().execute(
        "INSERT INTO downloads(url, name, status, provider, save_dir, created_at) VALUES(?,?,?,?,?,?)",
        (url, name, "downloading", "clouddrive2", save_dir, time.time()))
    return {"ok": True}


def refresh_tasks() -> int:
    """同步 CD2 任务进度到本地下载表。"""
    if not db.get_setting("cd2_url"):
        return 0
    token = _login()
    if token is None:
        return 0
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    data = util.http_post_json(_url("/json/v1"), {"method": "OfflineTaskList", "params": {}},
                               headers=headers)
    if not data or data.get("ret") != 0:
        return 0
    tasks = data.get("value") or []
    d = db.db()
    local = {r["url"]: r for r in d.query("SELECT * FROM downloads WHERE provider='clouddrive2' AND status IN ('downloading','pending')")}
    n = 0
    for t in tasks:
        url = t.get("url", "")
        progress = float(t.get("Progress", 0)) * 100
        status_str = t.get("StatusText", "")
        done = progress >= 100 or "完成" in status_str or "finished" in status_str.lower()
        speed = f"{t.get('FileDownloadSpeed', 0):.0f} B/s" if not done else ""
        if url in local:
            d.execute(
                "UPDATE downloads SET progress=?, status=?, downloaded=?, size=?, speed=?, updated_at=? WHERE id=?",
                (min(progress, 100), "done" if done else "downloading",
                 int(t.get("FileDownloadedSize", 0)), int(t.get("FileSize", 0)),
                 speed, time.time(), local[url]["id"]))
        else:
            name = url if not url.startswith("magnet:") else f"CD2 任务 {time.strftime('%m-%d %H:%M')}"
            d.execute(
                "INSERT INTO downloads(url, name, status, provider, progress, size, downloaded, save_dir, created_at, updated_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?)",
                (url, name, "done" if done else "downloading", "clouddrive2",
                 min(progress, 100), int(t.get("FileSize", 0)), int(t.get("FileDownloadedSize", 0)),
                 t.get("Path", ""), time.time(), time.time()))
        n += 1
    return n


def _loop():
    while not _stop.is_set():
        try:
            refresh_tasks()
        except Exception:  # noqa: BLE001
            util.logger().exception("下载任务同步异常")
        _stop.wait(timeout=10.0)


def start():
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_loop, name="downloader", daemon=True).start()


def stop():
    _stop.set()
