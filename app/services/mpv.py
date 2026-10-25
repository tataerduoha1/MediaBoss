"""mpv 播放器集成：本机唤起 mpv 播放指定视频（支持断点续播）。"""
import os
import subprocess

from .. import db
from . import ffmpegtool


def launch(video_path: str, start_at: float = 0.0, title: str = "") -> dict:
    mpv = ffmpegtool.detect_mpv()
    if not mpv:
        return {"ok": False, "error": "未找到 mpv，请在设置中配置 mpv 路径"}
    args = [mpv]
    if start_at > 3:
        args += [f"--start={int(start_at)}"]
    args += [
        f"--force-media-title={title}" if title else "--force-media-title=MediaBoss",
        "--save-position-on-quit",
        os.path.normpath(video_path),
    ]
    try:
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        subprocess.Popen(args, creationflags=flags if os.name == "nt" else flags,
                         close_fds=True)
        return {"ok": True}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
