"""认证 API：登录/登出/改密/API 令牌管理。"""
import hashlib
import secrets
import time

from .. import config, db
from ..httpd import Response, json_err, json_ok, set_cookie, router

SESSION_COOKIE = "mb_session"
SESSION_TTL = 30 * 86400


def _hash(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def _ensure_password():
    """首次使用时将默认密码 admin 写入散列。"""
    s = db.all_settings()
    if not s.get("password_hash"):
        salt = secrets.token_hex(8)
        db.set_setting("password_salt", salt)
        db.set_setting("password_hash", _hash(s.get("password", "admin"), salt))
        db.set_setting("password", "")


@router.post("/auth/login")
def login(req):
    _ensure_password()
    password = str(req.json.get("password", ""))
    stored = db.get_setting("password_hash")
    salt = db.get_setting("password_salt")
    if _hash(password, salt) != stored:
        return json_err(401, "密码错误")
    token = secrets.token_hex(24)
    db.db().execute("INSERT INTO sessions(token, expires) VALUES(?,?)", (token, time.time() + SESSION_TTL))
    db.db().execute("DELETE FROM sessions WHERE expires<?", (time.time(),))
    resp = json_ok({"version": config.VERSION})
    return set_cookie(resp, SESSION_COOKIE, token, SESSION_TTL)


@router.post("/auth/logout")
def logout(req):
    sid = req.cookies.get(SESSION_COOKIE)
    if sid:
        db.db().execute("DELETE FROM sessions WHERE token=?", (sid,))
    resp = json_ok()
    return set_cookie(resp, SESSION_COOKIE, "", 0)


@router.get("/auth/status")
def status(req):
    return json_ok({"version": config.VERSION, "app": config.APP_NAME})


@router.post("/auth/password")
def change_password(req):
    old, new = str(req.json.get("old", "")), str(req.json.get("new", ""))
    if len(new) < 4:
        return json_err(400, "新密码至少 4 位")
    _ensure_password()
    salt = db.get_setting("password_salt")
    if _hash(old, salt) != db.get_setting("password_hash"):
        return json_err(403, "原密码错误")
    db.set_setting("password_hash", _hash(new, salt))
    return json_ok()


@router.get("/auth/tokens")
def list_tokens(req):
    return json_ok(db.db().query("SELECT id, token, name, created_at, last_used FROM api_tokens ORDER BY id DESC"))


@router.post("/auth/tokens")
def create_token(req):
    name = str(req.json.get("name", ""))[:40]
    token = secrets.token_hex(16)
    cur = db.db().execute("INSERT INTO api_tokens(token, name, created_at) VALUES(?,?,?)",
                          (token, name, time.time()))
    return json_ok({"id": cur.lastrowid, "token": token, "name": name})


@router.delete("/auth/tokens/{tid}")
def delete_token(req):
    db.db().execute("DELETE FROM api_tokens WHERE id=?", (int(req.params["tid"]),))
    return json_ok()
