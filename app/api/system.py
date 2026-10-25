"""系统 API：信息/统计/ffmpeg 安装。"""
import os
import platform
import sys

from .. import config, db, util
from ..httpd import ApiError, json_ok, router
from ..services import ffmpegtool


@router.get("/system/ping")
def ping(req):
    return json_ok({"pong": True, "version": config.VERSION})


@router.get("/system/info")
def info(req):
    d = db.db()
    db_size = 0
    try:
        db_size = os.path.getsize(config.cfg().db_path) if os.path.isfile(config.cfg().db_path) else 0
    except OSError:
        pass
    return json_ok({
        "app": config.APP_NAME, "version": config.VERSION,
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "db_size": db_size,
        "ffmpeg": ffmpegtool.ffmpeg_status(),
        "mpv": ffmpegtool.mpv_status(),
        "lan_access": db.get_setting("lan_access", "0") == "1",
        "host": util.local_ip(),
        "port": config.cfg().port,
    })


@router.post("/system/ffmpeg/install")
def install_ffmpeg(req):
    r = ffmpegtool.download_ffmpeg()
    if r.get("ok"):
        # 安装后重试缩略图队列
        from ..services import thumbs
        thumbs.enqueue_pending()
        return json_ok(r)
    raise ApiError(500, f"ffmpeg 安装失败: {r.get('error', '')}")


@router.post("/system/detect")
def detect_tools(req):
    from ..services import thumbs
    ffmpegtool.detect_ffmpeg(force=True)
    thumbs.enqueue_pending()
    return json_ok({"ffmpeg": ffmpegtool.ffmpeg_status(), "mpv": ffmpegtool.mpv_status()})
