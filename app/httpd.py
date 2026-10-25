"""微型 HTTP 框架：路由、JSON 请求/响应、Cookie 会话、静态文件、Range 流媒体。"""
import hashlib
import json
import mimetypes
import os
import re
import secrets
import shutil
import socket
import time
import urllib.parse
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config, db

_session_cookie = "mb_session"


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class Request:
    def __init__(self, handler: BaseHTTPRequestHandler, path_params: dict):
        self.h = handler
        self.method = handler.command
        parsed = urllib.parse.urlsplit(handler.path)
        self.path = urllib.parse.unquote(parsed.path)
        self.raw_query = parsed.query
        self.params = path_params
        self._query = None
        self._body = None
        self._json = None
        self._cookies = None

    @property
    def query(self) -> dict:
        if self._query is None:
            self._query = {k: v[0] for k, v in urllib.parse.parse_qs(self.raw_query, keep_blank_values=True).items()}
        return self._query

    @property
    def body(self) -> bytes:
        if self._body is None:
            length = int(self.h.headers.get("Content-Length") or 0)
            self._body = self.h.rfile.read(length) if length > 0 else b""
        return self._body

    @property
    def json(self) -> dict:
        if self._json is None:
            try:
                self._json = json.loads(self.body.decode("utf-8")) if self.body else {}
            except (ValueError, UnicodeDecodeError):
                raise ApiError(400, "请求体不是合法 JSON")
        return self._json

    @property
    def cookies(self) -> dict:
        if self._cookies is None:
            c = SimpleCookie(self.h.headers.get("Cookie") or "")
            self._cookies = {k: v.value for k, v in c.items()}
        return self._cookies

    def header(self, name: str, default: str = "") -> str:
        return self.h.headers.get(name, default)

    @property
    def remote(self) -> str:
        return self.h.client_address[0]

    def is_localhost(self) -> bool:
        return self.remote in ("127.0.0.1", "::1", "localhost")


class Response:
    def __init__(self, status=200, body: bytes = b"", content_type="application/json; charset=utf-8",
                 headers: dict | None = None):
        self.status = status
        self.body = body
        self.content_type = content_type
        self.headers = headers or {}
        self.file_path = None
        self.stream_spec = None  # (file_path, range_start, range_end)
        self.cookie = None       # (key, value, max_age)


def json_ok(data=None, **extra) -> Response:
    payload = {"ok": True}
    if data is not None:
        payload["data"] = data
    payload.update(extra)
    return Response(200, json.dumps(payload, ensure_ascii=False).encode("utf-8"))


def json_err(status: int, message: str) -> Response:
    return Response(status, json.dumps({"ok": False, "error": message}, ensure_ascii=False).encode("utf-8"))


def set_cookie(resp: Response, key: str, value: str, max_age: int) -> Response:
    resp.cookie = (key, value, max_age)
    return resp


class Router:
    def __init__(self):
        self.routes: list[tuple[str, re.Pattern, callable]] = []

    def add(self, method: str, pattern: str, fn):
        regex = re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", pattern)
        self.routes.append((method, re.compile(f"^{regex}$"), fn))

    def get(self, pattern):
        def deco(fn):
            self.add("GET", pattern, fn)
            return fn
        return deco

    def post(self, pattern):
        def deco(fn):
            self.add("POST", pattern, fn)
            return fn
        return deco

    def patch(self, pattern):
        def deco(fn):
            self.add("PATCH", pattern, fn)
            return fn
        return deco

    def put(self, pattern):
        def deco(fn):
            self.add("PUT", pattern, fn)
            return fn
        return deco

    def delete(self, pattern):
        def deco(fn):
            self.add("DELETE", pattern, fn)
            return fn
        return deco

    def match(self, method: str, path: str):
        allowed = set()
        for m, rx, fn in self.routes:
            match = rx.match(path)
            if match:
                if m == method or (m == "GET" and method == "HEAD"):
                    return fn, match.groupdict()
                allowed.add(m)
        if allowed:
            return None, allowed  # 405
        return None, None  # 404


router = Router()

# 注册各 API 模块（在导入时装饰路由）
from .api import auth, data, directories, downloads, entities, jav, settings_api, system, tasks, updates, videos  # noqa: E402,F401


def handle_api(req: Request) -> Response:
    fn, groups = router.match(req.method, req.path[len("/api"):])
    if fn is None:
        if isinstance(groups, set):
            return json_err(405, "Method Not Allowed")
        return json_err(404, "接口不存在")
    if groups:
        req.params = groups
    return fn(req)


def _auth_ok(req: Request) -> bool:
    """会话 Cookie 或 API 令牌（Bearer / ?token=）任一通过即可。"""
    sid = req.cookies.get(_session_cookie)
    if sid:
        row = db.db().query_one("SELECT expires FROM sessions WHERE token=?", (sid,))
        if row and row["expires"] > time.time():
            return True
    token = req.header("Authorization", "").removeprefix("Bearer ").strip() or req.query.get("token", "")
    if token:
        row = db.db().query_one("SELECT id FROM api_tokens WHERE token=?", (token,))
        if row:
            db.db().execute("UPDATE api_tokens SET last_used=? WHERE id=?", (time.time(), row["id"]))
            return True
    return False


PUBLIC_PATHS = {"/api/auth/login", "/api/auth/status", "/api/system/ping"}


def serve_static(req: Request) -> Response:
    web_dir = config.cfg().web_dir
    rel = req.path.lstrip("/") or "index.html"
    if rel.startswith("api/"):
        return json_err(404, "not found")
    full = os.path.normpath(os.path.join(web_dir, rel))
    if not full.startswith(web_dir):
        return json_err(403, "forbidden")
    if not os.path.isfile(full):
        full = os.path.join(web_dir, "index.html")  # SPA fallback
    ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
    if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
        ctype += "; charset=utf-8"
    with open(full, "rb") as f:
        body = f.read()
    etag = hashlib.md5(body).hexdigest()[:16]
    inm = req.header("If-None-Match")
    # HTML 一律 no-store：杜绝浏览器复用旧入口（旧入口引用过期资源链会导致白屏）
    # JS/CSS 用 no-cache + ETag 再验证：代码更新立即生效；图片/视频等二进制长缓存
    if ctype.startswith("text/html"):
        cc = "no-store"
    elif "javascript" in ctype or ctype.startswith("text/css"):
        cc = "no-cache"
    else:
        cc = "public, max-age=86400"
    headers = {"ETag": etag, "Cache-Control": cc}
    if inm == etag:
        return Response(304, b"", headers=headers)
    return Response(200, body, ctype, headers)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "MediaBoss"

    def log_message(self, fmt, *args):  # 静默默认日志
        pass

    def handle(self):  # 客户端中途断开时静默，避免刷屏
        try:
            super().handle()
        except (ConnectionResetError, ConnectionAbortedError, TimeoutError):
            self.close_connection = True

    def _dispatch(self):
        try:
            path = urllib.parse.urlsplit(self.path).path
            req = Request(self, {})
            if path == "/api" or path.startswith("/api/"):
                if path not in PUBLIC_PATHS and not _auth_ok(req) and path != "/api/auth/logout":
                    return self._send(json_err(401, "未登录"))
                return self._send(handle_api(req))
            # 静态资源不做鉴权（登录页本身也是静态文件）
            return self._send(serve_static(req))
        except ApiError as e:
            return self._send(json_err(e.status, e.message))
        except BrokenPipeError:
            return
        except Exception as e:  # noqa: BLE001
            from . import util
            util.logger().exception("请求处理异常: %s", self.path)
            try:
                return self._send(json_err(500, f"服务器内部错误: {e}"))
            except Exception:  # noqa: BLE001
                return

    def _send(self, resp: Response):
        if resp.file_path:
            with open(resp.file_path, "rb") as f:
                resp.body = f.read()
        if resp.stream_spec:
            return self._send_stream(resp)
        self.send_response(resp.status)
        self.send_header("Content-Type", resp.content_type)
        self.send_header("Content-Length", str(len(resp.body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in resp.headers.items():
            self.send_header(k, v)
        if resp.cookie:
            k, v, max_age = resp.cookie
            self.send_header("Set-Cookie", f"{k}={v}; Path=/; Max-Age={max_age}; HttpOnly; SameSite=Lax")
        self.end_headers()
        if self.command != "HEAD" and resp.body:
            self.wfile.write(resp.body)

    def _send_stream(self, resp: Response):
        file_path, start, end = resp.stream_spec
        size = os.path.getsize(file_path)
        length = end - start + 1
        self.send_response(206 if start > 0 or end < size - 1 else 200)
        self.send_header("Content-Type", resp.content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        if start > 0 or end < size - 1:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        for k, v in resp.headers.items():
            self.send_header(k, v)
        self.end_headers()
        with open(file_path, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(1024 * 512, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    return  # 客户端主动断开（切页/关闭播放器/浏览器取消 Range），属正常行为
                remaining -= len(chunk)

    def do_GET(self):
        self._dispatch()

    def do_HEAD(self):
        self._dispatch()

    def do_POST(self):
        self._dispatch()

    def do_PATCH(self):
        self._dispatch()

    def do_PUT(self):
        self._dispatch()

    def do_DELETE(self):
        self._dispatch()


class DualStackServer(ThreadingHTTPServer):
    """双栈监听（IPv4 + IPv6），局域网设备（手机/平板）可直接访问。"""

    address_family = socket.AF_INET6

    def server_bind(self):
        try:
            self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        except OSError:
            pass
        super().server_bind()


def create_server() -> ThreadingHTTPServer:
    c = config.cfg()
    if c.host in ("", "::", "0.0.0.0"):
        try:
            srv: ThreadingHTTPServer = DualStackServer(("::", c.port), Handler)
            srv.daemon_threads = True
            return srv
        except OSError:  # 系统 IPv6 不可用时回退 IPv4 全接口
            pass
    server = ThreadingHTTPServer((c.host or "0.0.0.0", c.port), Handler)
    server.daemon_threads = True
    return server
