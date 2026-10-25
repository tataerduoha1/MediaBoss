"""目录扫描服务：周期扫描、视频指纹（移动重命名不丢数据）、元数据探测、JAV 关联。"""
import hashlib
import os
import threading
import time

from .. import config, db, util
from . import ffmpegtool, javcode, thumbs

FINGERPRINT_HEAD = 128 * 1024
FINGERPRINT_TAIL = 64 * 1024

_started = False
_stop = threading.Event()
_wake = threading.Event()
_scan_lock = threading.Lock()

_state = {
    "scanning": False,
    "last_scan": 0.0,
    "last_scan_files": 0,
    "last_scan_new": 0,
    "last_scan_removed": 0,
    "last_scan_ms": 0,
    "next_scan": 0.0,
}
_state_lock = threading.Lock()


def status() -> dict:
    with _state_lock:
        s = dict(_state)
    s["queue_thumb"] = thumbs.queue_size()
    return s


def wake():
    """立即触发一次扫描。"""
    _wake.set()


def start():
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_loop, name="scanner", daemon=True).start()


def stop():
    _stop.set()
    _wake.set()


def _loop():
    while not _stop.is_set():
        interval_min = float(db.get_setting("scan_interval_min", "1") or 1)
        auto = db.get_setting("auto_scan", "1") == "1"
        delay = max(interval_min * 60.0, 5.0) if auto else 3600.0
        with _state_lock:
            _state["next_scan"] = time.time() + delay
        _wake.wait(timeout=delay)
        if _stop.is_set():
            return
        _wake.clear()
        if auto or _manual_requested():
            try:
                scan_now()
            except Exception:  # noqa: BLE001
                util.logger().exception("扫描任务异常")


_manual_flag = False


def _manual_requested() -> bool:
    global _manual_flag
    if _manual_flag:
        _manual_flag = False
        return True
    return False


def request_manual():
    global _manual_flag
    _manual_flag = True
    wake()


def fingerprint(path: str, size: int) -> str:
    """size + 头 128KB + 尾 64KB 内容哈希，文件改名/移动不改变指纹。"""
    h = hashlib.sha1()
    h.update(str(size).encode())
    try:
        with open(path, "rb") as f:
            h.update(f.read(FINGERPRINT_HEAD))
            if size > FINGERPRINT_HEAD:
                f.seek(max(0, size - FINGERPRINT_TAIL))
                h.update(f.read(FINGERPRINT_TAIL))
    except OSError:
        h.update(str(os.path.getmtime(path)).encode())
    return h.hexdigest()


def scan_now() -> dict:
    with _scan_lock:
        t0 = time.time()
        with _state_lock:
            if _state["scanning"]:
                return {"skipped": True}
            _state["scanning"] = True
        try:
            result = _scan()
        finally:
            with _state_lock:
                _state["scanning"] = False
                _state["last_scan"] = time.time()
                _state["last_scan_ms"] = int((time.time() - t0) * 1000)
        return result


def _scan() -> dict:
    d = db.db()
    dirs = d.query("SELECT * FROM directories WHERE enabled=1")
    disk_files: dict[str, dict] = {}
    for directory in dirs:
        root = directory["path"]
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [x for x in dirnames if not x.startswith(".")]
            for name in filenames:
                if name.startswith(".") or not util.is_video_file(name):
                    continue
                full = util.norm_path(os.path.join(dirpath, name))
                try:
                    st = os.stat(full)
                except OSError:
                    continue
                disk_files[full] = {"size": st.st_size, "mtime": st.st_mtime, "dir_id": directory["id"]}

    total = len(disk_files)
    added = removed = 0

    # 入库 / 更新 / 识别移动
    by_path = {r["path"]: r for r in d.query("SELECT id, path, size, mtime, fingerprint FROM videos")}
    by_fp = {r["fingerprint"]: r for r in d.query("SELECT id, path, size, fingerprint FROM videos")}
    known_paths = set(by_path)

    for path, meta in disk_files.items():
        row = by_path.get(path)
        if row:
            if row["size"] != meta["size"] or abs(row["mtime"] - meta["mtime"]) > 1:
                fp = fingerprint(path, meta["size"])
                d.execute(
                    "UPDATE videos SET size=?, mtime=?, fingerprint=?, updated_at=? WHERE id=?",
                    (meta["size"], meta["mtime"], fp, time.time(), row["id"]))
            continue
        # 新路径：先看指纹是否命中（移动/重命名场景）
        fp = fingerprint(path, meta["size"])
        moved = by_fp.get(fp)
        now = time.time()
        if moved:
            d.execute("UPDATE videos SET path=?, dir_id=?, size=?, mtime=?, updated_at=? WHERE id=?",
                      (path, meta["dir_id"], meta["size"], meta["mtime"], now, moved["id"]))
            # 清理缩略图缓存键不变（按 video id），无需重建
        else:
            filename = os.path.basename(path)
            ext = os.path.splitext(filename)[1].lower()
            cur = d.execute(
                "INSERT INTO videos(fingerprint, path, dir_id, filename, ext, size, mtime, title,"
                " created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (fp, path, meta["dir_id"], filename, ext, meta["size"], meta["mtime"],
                 os.path.splitext(filename)[0], now, now))
            vid = cur.lastrowid
            added += 1
            _after_insert(vid, path, meta["size"])

    # 删除已不存在的文件记录
    for path in known_paths - set(disk_files):
        d.execute("DELETE FROM videos WHERE path=?", (path,))
        removed += 1

    _sync_jav_counts()

    # 存量未刮削完成的视频重新入队（enqueue 内部有去重、attempts 与冷却限制）
    if db.get_setting("jav_mode", "1") == "1" and db.get_setting("scrape_enabled", "1") == "1":
        from . import scraper
        for r in d.query("SELECT id FROM videos WHERE scrape_status=0 AND scrape_attempts<3"
                         " AND next_retry_at<=?", (time.time(),)):
            scraper.enqueue(r["id"])

    with _state_lock:
        _state["last_scan_files"] = total
        _state["last_scan_new"] = added
        _state["last_scan_removed"] = removed
    util.logger().info("扫描完成: 共 %d 个视频, 新增 %d, 移除 %d, 耗时 %dms",
                       total, added, removed, _state["last_scan_ms"])
    return {"total": total, "added": added, "removed": removed}


def _after_insert(vid: int, path: str, size: int):
    """新视频入库后：探测元数据、识别番号、入缩略图与刮削队列。"""
    d = db.db()
    jav_mode = db.get_setting("jav_mode", "1") == "1"

    info = ffmpegtool.ffprobe_info(path) if size < 2**40 else {}
    updates = {}
    if info:
        updates.update({k: info[k] for k in ("duration", "width", "height", "bitrate", "codec")})
    sets = ", ".join(f"{k}=?" for k in updates)
    if sets:
        d.execute(f"UPDATE videos SET {sets} WHERE id=?", (*updates.values(), vid))

    thumbs.enqueue(vid)

    if jav_mode:
        code = javcode.primary_code(os.path.basename(path))
        if code:
            exists = d.query_one("SELECT id FROM jav WHERE code=?", (code,))
            if exists:
                # 同番号多文件：保留首个关联，后续文件作为普通视频
                return
            d.execute(
                "INSERT INTO jav(video_id, code, title, cover_url, duration_sec, updated_at)"
                " VALUES(?,?,?,?,?,?)",
                (vid, code, "", "", int(info.get("duration") or 0), time.time()))
            d.execute("UPDATE videos SET scrape_status=0 WHERE id=?", (vid,))
            from . import scraper
            scraper.enqueue(vid)


def _sync_jav_counts():
    """刷新女优/厂商/系列/标签的计数与孤儿清理。"""
    d = db.db()
    d.execute("UPDATE actresses SET video_count=(SELECT COUNT(*) FROM jav_actresses WHERE actress_id=actresses.id)")
    d.execute("UPDATE studios SET video_count=(SELECT COUNT(*) FROM jav WHERE studio_id=studios.id)")
    d.execute("UPDATE series SET video_count=(SELECT COUNT(*) FROM jav WHERE series_id=series.id)")
    d.execute("UPDATE genres SET video_count=(SELECT COUNT(*) FROM jav_genres WHERE genre_id=genres.id)")
    d.execute("DELETE FROM studios WHERE id NOT IN (SELECT DISTINCT studio_id FROM jav WHERE studio_id IS NOT NULL)")
    d.execute("DELETE FROM series WHERE id NOT IN (SELECT DISTINCT series_id FROM jav WHERE series_id IS NOT NULL)")
