"""标题翻译（Google translate gtx 免费接口，尽力而为，批量限速）。"""
import threading
import time
import urllib.parse

from ... import db, util

_batch_lock = threading.Lock()


def translate_text(text: str, target: str = "zh-CN") -> str:
    q = urllib.parse.quote(text[:1500])
    url = (f"https://translate.googleapis.com/translate_a/single?client=gtx"
           f"&sl=auto&tl={target}&dt=t&q={q}")
    data = util.http_get(url, timeout=10, proxy=db.get_setting("proxy"), retries=1)
    if not data:
        return ""
    try:
        import json
        arr = json.loads(data.decode("utf-8", "replace"))
        out = "".join(seg[0] for seg in arr[0] if seg and seg[0])
        return out.strip()
    except Exception:  # noqa: BLE001
        return ""


def translate_jav_title(jav_id: int, title: str) -> str:
    cn = translate_text(title)
    if cn:
        db.db().execute("UPDATE jav SET cn_title=? WHERE id=?", (cn, jav_id))
    return cn


def enrich_translations(limit: int = 20):
    """补全缺失的中文标题（每批限量，避免请求过快）。"""
    if db.get_setting("translate_enabled", "1") != "1":
        return
    rows = db.db().query(
        "SELECT id, title FROM jav WHERE cn_title='' AND title!='' LIMIT ?", (limit,))
    with _batch_lock:
        for r in rows:
            translate_jav_title(r["id"], r["title"])
            time.sleep(0.6)
