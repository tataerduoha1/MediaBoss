"""ffmpeg / ffprobe / mpv 探测与 ffmpeg 自动下载（可选）。"""
import os
import shutil
import subprocess
import threading

from .. import config, db, util

_lock = threading.Lock()
_ffmpeg_path = None
_probe_done = False


def _candidates(setting: str, name: str) -> list[str]:
    out = []
    if setting:
        out.append(setting)
        out.append(os.path.join(setting, name + ".exe" if os.name == "nt" else name))
    bin_dir = config.cfg().bin_dir
    out.append(os.path.join(bin_dir, "ffmpeg", name + (".exe" if os.name == "nt" else "")))
    out.append(name)  # PATH
    return out


def _which(cands: list[str], name: str = "") -> str | None:
    for c in cands:
        if os.path.isfile(c):
            return c
    for c in cands:
        w = shutil.which(c)
        if w:
            return w
    # 兜底：在 data/bin 下递归查找（兼容解压出的嵌套目录）
    if name:
        suffix = ".exe" if os.name == "nt" else ""
        bin_dir = config.cfg().bin_dir
        for root, _dirs, files in os.walk(bin_dir):
            if name + suffix in files:
                return os.path.join(root, name + suffix)
    return None


def detect_ffmpeg(force: bool = False) -> str | None:
    """探测 ffmpeg 可执行文件路径，结果缓存。"""
    global _ffmpeg_path, _probe_done
    with _lock:
        if _probe_done and not force:
            return _ffmpeg_path or None
        setting = db.get_setting("ffmpeg_path")
        _ffmpeg_path = _which(_candidates(setting, "ffmpeg"), "ffmpeg")
        _probe_done = True
        return _ffmpeg_path


def detect_ffprobe() -> str | None:
    setting = db.get_setting("ffmpeg_path")
    return _which(_candidates(setting, "ffprobe"), "ffprobe")


def detect_mpv() -> str | None:
    setting = db.get_setting("mpv_path")
    cands = []
    if setting:
        cands.append(setting)
        cands.append(os.path.join(setting, "mpv.exe" if os.name == "nt" else "mpv"))
    for extra in (r"C:\Program Files\mpv\mpv.exe", r"C:\Program Files (x86)\mpv\mpv.exe",
                  os.path.expanduser(r"~\scoop\apps\mpv\current\mpv.exe"),
                  r"C:\Program Files\mpv.io\shaders\..\mpv.exe"):
        cands.append(extra)
    cands.append("mpv")
    return _which(cands)


def ffprobe_info(path: str) -> dict:
    """调用 ffprobe 获取视频时长/分辨率/编码信息，失败返回 {}。"""
    ff = detect_ffprobe()
    if not ff:
        return {}
    try:
        out = subprocess.run(
            [ff, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", path],
            capture_output=True, timeout=60,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        import json as _json
        data = _json.loads(out.stdout.decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        return {}
    fmt = data.get("format", {})
    info = {
        "duration": float(fmt.get("duration") or 0),
        "bitrate": int(fmt.get("bit_rate") or 0),
        "width": 0, "height": 0, "codec": "",
    }
    for st in data.get("streams", []):
        if st.get("codec_type") == "video" and not info["width"]:
            info["width"] = int(st.get("width") or 0)
            info["height"] = int(st.get("height") or 0)
            info["codec"] = st.get("codec_name") or ""
    return info


def ffmpeg_status() -> dict:
    p = detect_ffmpeg()
    ver = ""
    if p:
        try:
            out = subprocess.run([p, "-version"], capture_output=True, timeout=10,
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            first = out.stdout.decode("utf-8", "replace").splitlines()
            ver = first[0].split()[2] if first else ""
        except Exception:  # noqa: BLE001
            pass
    return {"available": bool(p), "path": p or "", "version": ver}


def mpv_status() -> dict:
    p = detect_mpv()
    return {"available": bool(p), "path": p or ""}


def run_ffmpeg(args: list[str], timeout: float = 600) -> tuple[bool, str]:
    p = detect_ffmpeg()
    if not p:
        return False, "ffmpeg 不可用"
    try:
        out = subprocess.run([p, "-y", *args], capture_output=True, timeout=timeout,
                             creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        ok = out.returncode == 0
        msg = out.stderr.decode("utf-8", "replace")[-800:] if not ok else ""
        return ok, msg
    except Exception as e:  # noqa: BLE001
        return False, str(e)


FFMPEG_URLS = {
    "windows": [
        "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
        "https://gh-proxy.com/https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-win64-gpl.zip",
    ],
    "linux": [
        "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz",
    ],
    "darwin": [
        "https://evermeet.cx/ffmpeg/getrelease/zip",
    ],
}


def _download(url: str, dest: str, timeout: int = 90) -> None:
    """带超时与代理的流式下载。"""
    import urllib.request
    proxy = db.get_setting("proxy")
    handlers = [urllib.request.ProxyHandler({"http": proxy, "https": proxy}) if proxy else urllib.request.ProxyHandler({})]
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 MediaBoss"})
    with opener.open(req, timeout=timeout) as resp, open(dest, "wb") as f:
        while True:
            chunk = resp.read(1024 * 256)
            if not chunk:
                break
            f.write(chunk)


def download_ffmpeg() -> dict:
    """按顺序尝试多个源下载并解压 ffmpeg 到 data/bin（阻塞调用）。"""
    import platform
    import zipfile
    import tarfile

    url_key = "windows" if os.name == "nt" else (
        "darwin" if platform.system() == "Darwin" else "linux")
    urls = FFMPEG_URLS[url_key]
    dest_dir = config.cfg().bin_dir
    os.makedirs(dest_dir, exist_ok=True)
    last_err = None
    for url in urls:
        archive = os.path.join(dest_dir, "ffmpeg_download." + ("zip" if ".zip" in url else "tar.xz"))
        try:
            util.logger().info("开始下载 ffmpeg: %s", url)
            _download(url, archive)
            if archive.endswith(".zip"):
                with zipfile.ZipFile(archive) as z:
                    z.extractall(dest_dir)
            else:
                with tarfile.open(archive) as t:
                    t.extractall(dest_dir)
            try:
                os.remove(archive)
            except OSError:
                pass
            global _probe_done
            _probe_done = False
            p = detect_ffmpeg(force=True)
            if p:
                return {"ok": True, "path": p}
            last_err = "解压后未找到 ffmpeg 可执行文件"
        except Exception as e:  # noqa: BLE001
            util.logger().exception("ffmpeg 下载失败: %s", url)
            last_err = str(e)
    return {"ok": False, "error": last_err or "所有下载源均失败"}
