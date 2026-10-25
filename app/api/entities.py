"""实体 API：女优 / 厂商 / 系列 / 类别 / 标签。"""
from .. import db
from ..httpd import ApiError, json_ok, router


def _list_entity(table: str, req, order_default: str = "video_count"):
    q = req.query
    kw = q.get("q", "").strip()
    where, vals = "1=1", []
    if kw:
        where = "name LIKE ?"
        vals = [f"%{kw}%"]
    order = q.get("sort", order_default)
    col = "name" if order == "name" else "video_count"
    direction = "ASC" if order == "name" else "DESC"
    # 只有 actresses 表有 avatar_path 列，其他表带上会报 no such column
    avatar_col = ", avatar_path AS avatar_url" if table == "actresses" else ""
    rows = db.db().query(
        f"SELECT id, name{avatar_col}, video_count FROM {table}"
        f" WHERE {where} ORDER BY {col} {direction}, name LIMIT 500", vals)
    return json_ok(rows)


@router.get("/actresses")
def actresses(req):
    return _list_entity("actresses", req)


@router.get("/actresses/{aid}")
def actress_detail(req):
    aid = int(req.params["aid"])
    a = db.db().query_one("SELECT * FROM actresses WHERE id=?", (aid,))
    if not a:
        raise ApiError(404, "女优不存在")
    return json_ok(a)


@router.patch("/actresses/{aid}")
def actress_update(req):
    aid = int(req.params["aid"])
    body = req.json
    if "avatar_path" in body:
        db.db().execute("UPDATE actresses SET avatar_path=? WHERE id=?", (body["avatar_path"], aid))
    return json_ok()


@router.get("/studios")
def studios(req):
    return _list_entity("studios", req)


@router.get("/series")
def series(req):
    return _list_entity("series", req)


@router.get("/genres")
def genres(req):
    return _list_entity("genres", req)


@router.get("/tags")
def tags(req):
    rows = db.db().query(
        "SELECT t.id, t.name, COUNT(vt.video_id) AS video_count FROM tags t"
        " LEFT JOIN video_tags vt ON vt.tag_id=t.id GROUP BY t.id ORDER BY video_count DESC, name")
    return json_ok(rows)
