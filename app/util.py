"""通用工具：日志、HTTP 客户端（gzip/代理/重试）、文件与格式化辅助。"""
import gzip
import io
import json
import logging
import os
import re
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib

from . import config

_http_state = threading.local()  # 记录同线程最近一次 http_get 状态码

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
]

_logger = None


def logger() -> logging.Logger:
    global _logger
    if _logger is None:
        log_dir = config.cfg().log_dir
        os.makedirs(log_dir, exist_ok=True)
        _logger = logging.getLogger("mediaboss")
        _logger.setLevel(logging.INFO)
        fmt = logging.Formatter("%(asctime)s %(levelname)s [%(threadName)s] %(name)s: %(message)s")
        fh = logging.FileHandler(os.path.join(log_dir, "mediaboss.log"), encoding="utf-8")
        fh.setFormatter(fmt)
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        _logger.addHandler(fh)
        _logger.addHandler(sh)
    return _logger


def now() -> float:
    return time.time()


def http_get(url: str, timeout: float = 15.0, proxy: str = "", headers: dict | None = None,
             retries: int = 2, return_raw: bool = False) -> bytes | None:
    """带 gzip 解压 / 代理 / UA 轮换 / 重试的 GET。失败返回 None。"""
    h = {
        "User-Agent": USER_AGENTS[int(time.time()) % len(USER_AGENTS)],
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "close",
    }
    if headers:
        h.update(headers)
    handlers = []
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    else:
        handlers.append(urllib.request.ProxyHandler({}))
    opener = urllib.request.build_opener(*handlers)
    last_err = None
    _http_state.last_status = 0
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=h)
            with opener.open(req, timeout=timeout) as resp:
                _http_state.last_status = getattr(resp, "status", 200)
                data = resp.read()
                enc = (resp.headers.get("Content-Encoding") or "").lower()
                if "gzip" in enc:
                    data = gzip.decompress(data)
                elif "deflate" in enc:
                    try:
                        data = zlib.decompress(data)
                    except zlib.error:
                        data = zlib.decompress(data, -zlib.MAX_WBITS)
                return data if return_raw else data
        except urllib.error.HTTPError as e:
            last_err = e
            _http_state.last_status = e.code
            if 400 <= e.code < 500:
                break  # 4xx 客户端错误（如番号不存在 404）重试无意义
            if attempt < retries:
                time.sleep(1.0 + attempt)
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt < retries:
                time.sleep(1.0 + attempt)
    logger().warning("http_get 失败: %s (%s)", url, last_err)
    return None


def http_last_status() -> int:
    """同线程最近一次 http_get 的 HTTP 状态码（0=未发/网络错误）。"""
    return getattr(_http_state, "last_status", 0)


def http_post_json(url: str, payload: dict, timeout: float = 15.0, proxy: str = "",
                   headers: dict | None = None) -> dict | None:
    """POST JSON 并解析 JSON 响应，失败返回 None。"""
    h = {"Content-Type": "application/json", "User-Agent": USER_AGENTS[0],
         "Accept": "application/json"}
    if headers:
        h.update(headers)
    handlers = []
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    else:
        handlers.append(urllib.request.ProxyHandler({}))
    opener = urllib.request.build_opener(*handlers)
    try:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=h, method="POST")
        with opener.open(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except Exception as e:  # noqa: BLE001
        logger().warning("http_post_json 失败: %s (%s)", url, e)
        return None


def human_size(n: int | float | None) -> str:
    if not n or n <= 0:
        return "-"
    units = ["B", "KB", "MB", "GB", "TB"]
    f = float(n)
    for u in units:
        if f < 1024:
            return f"{f:.1f} {u}" if u != "B" else f"{int(f)} B"
        f /= 1024
    return f"{f:.1f} PB"


def human_duration(sec: float | int | None) -> str:
    if not sec or sec <= 0:
        return "-"
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".wmv", ".mov", ".flv", ".ts", ".webm",
              ".m4v", ".mpg", ".mpeg", ".rmvb", ".rm", ".3gp", ".mts", ".m2ts", ".vob", ".f4v"}


def is_video_file(name: str) -> bool:
    return os.path.splitext(name)[1].lower() in VIDEO_EXTS


NOISE_NAME_RE = re.compile(r"[\x00-\x1f<>:\"/\\|?*]")


def safe_filename(name: str) -> str:
    return NOISE_NAME_RE.sub("_", name).strip(". ")[:120] or "file"


def norm_path(p: str) -> str:
    return os.path.normpath(os.path.abspath(p))


def local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"
