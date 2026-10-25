"""缩略图与预览图（雪碧图）生成队列：ffmpeg 后台批量处理。"""
import os
import queue
import threading

from .. import config, db, util
from . import ffmpegtool

_started = False
_q: queue.Queue = queue.Queue()
_workers: list[threading.Thread] = []
_stop = threading.Event()


def _thumb_path(video_id: int) -> str:
    return os.path.join(config.cfg().thumb_dir, f"v{video_id}.jpg")


def _sprite_path(video_id: int) -> str:
    return os.path.join(config.cfg().sprite_dir, f"v{video_id}.jpg")


def thumb_url(video_id: int) -> str:
    return f"/api/videos/{video_id}/thumbnail"


def sprite_url(video_id: int) -> str:
    return f"/api/videos/{video_id}/sprite"


def find_thumb(video_id: int) -> str | None:
    p = _thumb_path(video_id)
    return p if os.path.isfile(p) else None


def find_sprite(video_id: int) -> str | None:
    p = _sprite_path(video_id)
    return p if os.path.isfile(p) else None


def custom_poster(video_id: int) -> str | None:
    """A2 海报自选：用户指定的自定义海报（优先于抓帧缩略图）。"""
    p = os.path.join(config.cfg().thumb_dir, "custom", f"v{video_id}.jpg")
    return p if os.path.isfile(p) else None


def enqueue(video_id: int):
    """将视频加入缩略图生成队列（幂等）。"""
    row = db.db().query_one("SELECT thumb_status FROM videos WHERE id=?", (video_id,))
    if row and row["thumb_status"] == 0:
        _q.put(video_id)


def enqueue_pending():
    """启动时将所有待处理视频入队。"""
    rows = db.db().query("SELECT id FROM videos WHERE thumb_status=0")
    for r in rows:
        _q.put(r["id"])
    if rows:
        util.logger().info("缩略图队列: %d 个待处理", len(rows))


def start():
    global _started
    if _started:
        return
    _started = True
    n = max(1, int(db.get_setting("thumb_workers", "2") or 2))
    for i in range(n):
        t = threading.Thread(target=_worker, name=f"thumb-{i}", daemon=True)
        t.start()
        _workers.append(t)


def stop():
    _stop.set()


def _make_poster(path: str, duration: float, out: str) -> bool:
    at = max(1.0, duration * 0.1) if duration > 0 else 1.0
    at = min(at, 180.0)
    ok, _ = ffmpegtool.run_ffmpeg(
        ["-ss", f"{at:.2f}", "-i", path, "-frames:v", "1", "-vf", "scale=640:-2",
         "-q:v", "4", out], timeout=120)
    return ok and os.path.isfile(out)


def _make_sprite(path: str, duration: float, out: str) -> bool:
    if duration <= 3:
        return False
    tiles = 100
    fps = tiles / duration
    ok, _ = ffmpegtool.run_ffmpeg(
        ["-i", path, "-vf", f"fps={fps:.6f},scale=160:-2,tile=10x10", "-frames:v", "1",
         out], timeout=300)
    return ok and os.path.isfile(out)


def _worker():
    while not _stop.is_set():
        try:
            video_id = _q.get(timeout=1.0)
        except queue.Empty:
            continue
        try:
            _process(video_id)
        except Exception:  # noqa: BLE001
            util.logger().exception("缩略图处理异常 video=%s", video_id)
        finally:
            _q.task_done()


def _process(video_id: int):
    if not ffmpegtool.detect_ffmpeg():
        return  # 无 ffmpeg 时保持 pending，待安装后由 enqueue_pending 处理
    v = db.db().query_one("SELECT * FROM videos WHERE id=?", (video_id,))
    if not v:
        return
    path = v["path"]
    if not os.path.isfile(path):
        db.db().execute("UPDATE videos SET thumb_status=3 WHERE id=?", (video_id,))
        return
    duration = v["duration"] or 0
    final = _thumb_path(video_id)
    if os.path.isfile(final):
        ok = True  # 海报已存在（如清除雪碧图后的重建），跳过重复生成
    else:
        ok = _make_poster(path, duration, final + ".tmp.jpg")
        if ok:
            os.replace(final + ".tmp.jpg", final)
    if ok:
        if db.get_setting("sprite_enabled", "1") == "1" and duration > 0 and not os.path.isfile(_sprite_path(video_id)):
            _make_sprite(path, duration, _sprite_path(video_id))
        db.db().execute("UPDATE videos SET thumb_status=1 WHERE id=?", (video_id,))
    else:
        db.db().execute("UPDATE videos SET thumb_status=2 WHERE id=?", (video_id,))
        util.logger().warning("缩略图生成失败: %s", path)


def queue_size() -> int:
    return _q.qsize()
