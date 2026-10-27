"""JAV 刮削服务：任务队列、provider 编排、封面下载、入库、全量/增量更新任务。"""
import os
import queue
import re
import threading
import time
import urllib.parse

from ... import config, db, util
from .. import javcode
from .base import Metadata, Provider
from .javbus import JavBusProvider
from .javdb import JavDBProvider
from .javlib import JavLibProvider
from .dmm import DmmProvider
from .fc2ppv import Fc2PpvProvider
from .missav import MissAvProvider

PROVIDERS = {
    "javbus": JavBusProvider, "javdb": JavDBProvider,
    "javlib": JavLibProvider, "dmm": DmmProvider,
    "fc2": Fc2PpvProvider, "missav": MissAvProvider,
}

_started = False
_q: queue.Queue = queue.Queue()
_stop = threading.Event()
_scraping_lock = threading.Lock()
_queued: set[int] = set()  # 已在队列中的视频 id，防止 scanner 周期性入队造成重复

_stats = {"done": 0, "failed": 0, "last_code": "", "running": False}

# 更新任务（全量/增量）进度，全局单例
_job = {
    "mode": "",            # incremental / full / 手动单个刮削时为空
    "total": 0, "done": 0, "success": 0, "failed": 0, "skipped": 0,
    "started_at": 0.0, "finished_at": 0.0,
    "running": False, "cancel": False,
    "current": "",         # 当前正在刮削的番号
    "errors": [],          # 最近失败 [{code, video_id, at}]
}

# 标题翻译队列（单 worker，避免全量更新时线程爆炸）
_tq: queue.Queue = queue.Queue()


def status() -> dict:
    with _scraping_lock:
        return {"queue": _q.qsize(), **_stats, **_job_snapshot()}


def _job_snapshot() -> dict:
    j = dict(_job)
    now = time.time()
    j["elapsed"] = round((j["finished_at"] or now) - j["started_at"], 1) if j["started_at"] else 0
    if j["running"] and j["done"] > 0:
        j["eta"] = round((now - j["started_at"]) / j["done"] * max(0, j["total"] - j["done"]), 1)
    else:
        j["eta"] = 0
    j["errors"] = j["errors"][-20:]
    return j


def enqueue(video_id: int) -> bool:
    """入队（带重试冷却检查）。返回是否真正入队。"""
    v = db.db().query_one(
        "SELECT scrape_status, scrape_attempts, next_retry_at FROM videos WHERE id=?", (video_id,))
    if not v:
        return False
    # 失败(2)或尝试超限的不自动重试，等待手动/全量更新；0 状态需冷却期满
    if v["scrape_status"] == 0 and v["scrape_attempts"] < 3 and v["next_retry_at"] <= time.time():
        with _scraping_lock:
            dup = video_id in _queued
            if not dup:
                _queued.add(video_id)
        if not dup:
            _q.put(video_id)
            return True
    return False


def rescrape_jav(jav_id: int):
    """手动刮削：重置状态并入队。"""
    row = db.db().query_one("SELECT video_id FROM jav WHERE id=?", (jav_id,))
    if row:
        db.db().execute(
            "UPDATE videos SET scrape_status=0, scrape_attempts=0, next_retry_at=0 WHERE id=?",
            (row["video_id"],))
        enqueue(row["video_id"])


def rescrape_video(video_id: int):
    db.db().execute(
        "UPDATE videos SET scrape_status=0, scrape_attempts=0, next_retry_at=0 WHERE id=?", (video_id,))
    enqueue(video_id)


# ---------- 全量 / 增量更新任务 ----------

def start_update(mode: str, rebuild_thumbs: bool = False) -> dict:
    """启动更新任务。

    增量: 先扫描目录发现新增/变更，然后只重试 未刮削(0) 与 失败(2) 的视频；
          已成功(1) 的不重复请求外网；无番号/重复番号(3) 跳过。
    全量: 扫描目录后重置所有视频的刮削状态并全部重新刮削（覆盖本地已刮削的元数据）。
    """
    with _scraping_lock:
        if _job["running"]:
            raise RuntimeError("已有更新任务正在进行中")
        _job.update({"mode": mode, "total": 0, "done": 0, "success": 0, "failed": 0,
                     "skipped": 0, "started_at": time.time(), "finished_at": 0.0,
                     "running": True, "cancel": False, "current": "", "errors": []})
    try:
        from .. import scanner
        scanner.scan_now()  # 先同步扫描，发现新增/移动的文件
    except Exception:  # noqa: BLE001
        util.logger().exception("更新任务前置扫描失败")

    d = db.db()
    rebuild_thumbs and _reset_thumbs()
    if mode == "full":
        d.execute("UPDATE videos SET scrape_status=0, scrape_attempts=0, next_retry_at=0")
        rows = d.query("SELECT id FROM videos ORDER BY id")
    else:  # incremental
        d.execute("UPDATE videos SET scrape_attempts=0, next_retry_at=0 WHERE scrape_status IN (0,2)")
        rows = d.query("SELECT id FROM videos WHERE scrape_status IN (0,2) ORDER BY id")

    n = 0
    for r in rows:
        with _scraping_lock:
            dup = r["id"] in _queued
            if not dup:
                _queued.add(r["id"])
        if not dup:
            _q.put(r["id"])
            n += 1
    with _scraping_lock:
        _job["total"] = n
    util.logger().info("更新任务启动: 模式=%s, 目标 %d 个视频", mode, n)
    return progress()


def _reset_thumbs():
    """重建缩略图：全部标记为待处理并重新入队。"""
    d = db.db()
    d.execute("UPDATE videos SET thumb_status=0")
    from .. import thumbs
    thumbs.enqueue_pending()


def cancel_update() -> dict:
    with _scraping_lock:
        if not _job["running"]:
            return {"ok": False, "error": "没有进行中的任务"}
        _job["cancel"] = True
    drained = 0
    while True:
        try:
            vid = _q.get_nowait()
        except queue.Empty:
            break
        with _scraping_lock:
            _queued.discard(vid)
        _q.task_done()
        drained += 1
    with _scraping_lock:
        _job["running"] = False
        _job["finished_at"] = time.time()
    util.logger().info("更新任务已取消, 移除队列 %d 项", drained)
    return {"ok": True, "drained": drained}


def progress() -> dict:
    with _scraping_lock:
        return {"job": _job_snapshot(), "queue": _q.qsize()}


def _job_tick(success: bool, code: str, video_id: int, err: str = ""):
    with _scraping_lock:
        if not _job["running"]:
            return
        _job["done"] += 1
        if success:
            _job["success"] += 1
        else:
            _job["failed"] += 1
            if err or code:
                _job["errors"].append({"code": code or "(未知番号)", "video_id": video_id,
                                       "err": err[:120], "at": time.time()})
        _job["current"] = ""
        if _job["total"] > 0 and _job["done"] >= _job["total"]:
            _job["running"] = False
            _job["finished_at"] = time.time()
            util.logger().info("更新任务完成: 成功 %d, 失败 %d, 跳过 %d, 耗时 %.0fs",
                               _job["success"], _job["failed"], _job["skipped"],
                               _job["finished_at"] - _job["started_at"])


def _job_skip(video_id: int):
    with _scraping_lock:
        if not _job["running"]:
            return
        _job["done"] += 1
        _job["skipped"] += 1
        if _job["total"] > 0 and _job["done"] >= _job["total"]:
            _job["running"] = False
            _job["finished_at"] = time.time()


def start():
    global _started
    if _started:
        return
    _started = True
    for i in range(2):
        threading.Thread(target=_worker, name=f"scraper-{i}", daemon=True).start()
    threading.Thread(target=_translate_worker, name="translate", daemon=True).start()


def stop():
    _stop.set()


def _worker():
    while not _stop.is_set():
        try:
            video_id = _q.get(timeout=1.0)
        except queue.Empty:
            continue
        try:
            with _scraping_lock:
                _queued.discard(video_id)
            _process(video_id)
        except Exception as e:  # noqa: BLE001
            util.logger().exception("刮削异常 video=%s", video_id)
            with _scraping_lock:
                if _job["running"]:
                    _job["done"] += 1
                    _job["failed"] += 1
                    _job["errors"].append({"code": "", "video_id": video_id,
                                           "err": str(e)[:120], "at": time.time()})
        finally:
            _q.task_done()


def _translate_worker():
    while not _stop.is_set():
        try:
            jav_id, title = _tq.get(timeout=1.0)
        except queue.Empty:
            continue
        try:
            from . import translation
            translation.translate_jav_title(jav_id, title)
        except Exception:  # noqa: BLE001
            pass
        finally:
            _tq.task_done()


def _make_providers() -> list[Provider]:
    order = [p.strip().lower() for p in db.get_setting("scrape_provider_order", "javbus,javdb").split(",") if p.strip()]
    proxy = db.get_setting("proxy")
    out = []
    for name in order:
        cls = PROVIDERS.get(name)
        if cls:
            out.append(cls(proxy=proxy))
        else:
            util.logger().warning("数据源顺序里有无效源名，已跳过: %s", name)
    return out


def _process(video_id: int):
    d = db.db()
    v = d.query_one("SELECT * FROM videos WHERE id=?", (video_id,))
    if not v:
        return
    if v["scrape_status"] == 1:
        _job_tick(True, "", video_id)  # 出队时可能已被手动刮削完成
        return
    code = javcode.primary_code(v["filename"])
    if not code:
        d.execute("UPDATE videos SET scrape_status=3 WHERE id=?", (video_id,))
        _job_skip(video_id)
        return
    jrow = d.query_one("SELECT * FROM jav WHERE video_id=?", (video_id,))
    if not jrow:
        # 同番号多文件：jav.code 唯一，番号已被其他文件占用则本文件不建条目
        if d.query_one("SELECT id FROM jav WHERE code=?", (code,)):
            d.execute("UPDATE videos SET scrape_status=3 WHERE id=?", (video_id,))
            _job_skip(video_id)
            return
        cur = d.execute(
            "INSERT INTO jav(video_id, code, title, duration_sec, updated_at) VALUES(?,?,?,?,?)",
            (video_id, code, "", int(v["duration"] or 0), time.time()))
        jav_id = cur.lastrowid
    else:
        jav_id = jrow["id"]
        code = jrow["code"]

    if not _net_ok():
        return  # 网络不可用保持 pending，冷却后重试

    with _scraping_lock:
        _stats["running"] = True
        if _job["running"]:
            _job["current"] = code
    md = None
    try:
        for p in _make_providers():
            md = p.lookup(code)
            if md:
                # 命中日志：让"用了哪个源"在日志里可见（不打印番号/标题）
                util.logger().info("刮削命中 via %s（video=%d）", p.name, video_id)
                break
    finally:
        with _scraping_lock:
            _stats["running"] = False

    if md and md.title:
        _apply(jav_id, video_id, code, md)
        _stats["done"] += 1
        _stats["last_code"] = code
        _job_tick(True, code, video_id)
    else:
        attempts = v["scrape_attempts"] + 1
        # 番号在源站明确不存在（detail+search 均 404）时不再浪费重试，直接标记未找到
        if attempts >= 3 or util.http_last_status() == 404:
            d.execute("UPDATE videos SET scrape_status=2, scrape_attempts=? WHERE id=?",
                      (attempts, video_id))
        else:
            cooldown = float(db.get_setting("scrape_retry_cooldown_min", "15") or 15) * 60
            d.execute("UPDATE videos SET scrape_status=0, scrape_attempts=?, next_retry_at=? WHERE id=?",
                      (attempts, time.time() + cooldown, video_id))
        _stats["failed"] += 1
        _job_tick(False, code, video_id, err="未找到元数据（404 或站点不可达）")


def _net_ok() -> bool:
    return util.http_get("https://www.baidu.com", timeout=6, retries=0,
                         proxy=db.get_setting("proxy")) is not None


def _apply(jav_id: int, video_id: int, code: str, md: Metadata):
    d = db.db()

    studio_id = _ref_id("studios", md.studio) if md.studio else None
    series_id = _ref_id("series", md.series) if md.series else None

    cover_path = ""
    if md.cover_url:
        cover_path = _download_cover(code, md.cover_url, referer=md.site)

    d.execute(
        "UPDATE jav SET title=?, cover_url=?, cover_path=?, release_date=?, duration_sec=?,"
        " director=?, studio_id=?, series_id=?, score=?, updated_at=? WHERE id=?",
        (md.title, md.cover_url, cover_path, md.release_date,
         md.duration_sec or 0, md.director, studio_id, series_id, md.score, time.time(), jav_id))

    # 演员关联
    d.execute("DELETE FROM jav_actresses WHERE jav_id=?", (jav_id,))
    for a in md.actresses[:12]:
        name = a.get("name", "").strip()
        # 防线：异常长或含番号/影片标题特征的“名字”多半是误抓
        if not name or len(name) > 30 or re.search(r"[A-Z]{2,6}-\d{2,}", name):
            continue
        aid = _ref_id("actresses", name)
        if not d.query_one("SELECT 1 FROM actresses WHERE id=? AND avatar_path!=''", (aid,)):
            avatar = _download_cover(f"star_{aid}", a.get("avatar_url"), referer=md.site) if a.get("avatar_url") else ""
            if avatar:
                d.execute("UPDATE actresses SET avatar_path=? WHERE id=?", (avatar, aid))
        d.execute("INSERT OR IGNORE INTO jav_actresses(jav_id, actress_id) VALUES(?,?)", (jav_id, aid))

    # 类别
    d.execute("DELETE FROM jav_genres WHERE jav_id=?", (jav_id,))
    for g in md.genres[:30]:
        gid = _ref_id("genres", g)
        d.execute("INSERT OR IGNORE INTO jav_genres(jav_id, genre_id) VALUES(?,?)", (jav_id, gid))

    d.execute("UPDATE videos SET scrape_status=1, updated_at=? WHERE id=?", (time.time(), video_id))

    # 标题翻译（入队，单 worker 串行处理，避免线程爆炸）
    if db.get_setting("translate_enabled", "1") == "1":
        _tq.put((jav_id, md.title))

    _sync_counts()


def _ref_id(table: str, name: str) -> int:
    """INSERT OR IGNORE 后必须 SELECT 查回真实 id：
    记录已存在被忽略时 lastrowid 会返回连接上一次插入的旧 rowid（sqlite 陷阱）。"""
    d = db.db()
    d.execute(f"INSERT OR IGNORE INTO {table}(name) VALUES(?)", (name,))
    row = d.query_one(f"SELECT id FROM {table} WHERE name=?", (name,))
    return row["id"] if row else 0


def _download_cover(key: str, url: str, referer: str = "") -> str:
    safe = util.safe_filename(urllib.parse.quote(key, safe=""))[:80]
    ext = ".jpg"
    path = os.path.join(config.cfg().cover_dir, safe + ext)
    if os.path.isfile(path) and os.path.getsize(path) > 1024:
        return path
    # javbus 等站点图片有防盗链：缺 Referer 或 Referer 不带路径会返回 403
    headers = {"Referer": referer.rstrip("/") + "/"} if referer else None
    data = util.http_get(url, timeout=25, proxy=db.get_setting("proxy"), retries=2,
                         return_raw=True, headers=headers)
    if not data or len(data) < 1024:
        return ""
    with open(path, "wb") as f:
        f.write(data)
    return path


def _sync_counts():
    d = db.db()
    d.execute("UPDATE actresses SET video_count=(SELECT COUNT(*) FROM jav_actresses WHERE actress_id=actresses.id)")
    d.execute("UPDATE studios SET video_count=(SELECT COUNT(*) FROM jav WHERE studio_id=studios.id)")
    d.execute("UPDATE series SET video_count=(SELECT COUNT(*) FROM jav WHERE series_id=series.id)")
    d.execute("UPDATE genres SET video_count=(SELECT COUNT(*) FROM jav_genres WHERE genre_id=genres.id)")
