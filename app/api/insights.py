"""观影统计 API：年度报告(B1)、热力日历(B2)、女优合作网络(B5)。

数据源：play_log 播放流水（每次开始播放记录一条；v1.2.0 起累积，
升级前的历史由 watch_history 播种，仅含最近一次观看）。
"""
import time

from .. import db
from ..httpd import json_ok, router


def _year_range(year: int) -> tuple[float, float]:
    start = time.mktime(time.strptime(f"{year}-01-01", "%Y-%m-%d"))
    end = time.mktime(time.strptime(f"{year + 1}-01-01", "%Y-%m-%d"))
    return start, end


def _base(extra_joins: str = "") -> str:
    """播放流水统计的公共 FROM+WHERE；额外 JOIN 必须位于 WHERE 之前。"""
    return ("FROM play_log p JOIN videos v ON v.id=p.video_id LEFT JOIN jav j ON j.video_id=v.id "
            f"{extra_joins} WHERE p.started_at>=? AND p.started_at<?")


@router.get("/stats/annual")
def annual(req):
    year = int(req.query.get("year", 0) or time.localtime().tm_year)
    start, end = _year_range(year)
    d = db.db()
    base = _base()
    row = d.query_one(
        f"SELECT COUNT(*) plays, COALESCE(SUM(p.seconds),0) secs, COUNT(DISTINCT v.id) videos {base}",
        (start, end))
    # 阶梯数据：按月
    monthly = d.query(
        f"SELECT CAST(strftime('%m', p.started_at, 'unixepoch', 'localtime') AS INTEGER) m,"
        f" COUNT(*) plays, COALESCE(SUM(p.seconds),0) secs {base}"
        " GROUP BY m ORDER BY m", (start, end))
    months = [{"m": i, "plays": 0, "secs": 0} for i in range(1, 13)]
    for r in monthly:
        months[r["m"] - 1] = {"m": r["m"], "plays": r["plays"], "secs": r["secs"]}
    top_videos = d.query(
        f"SELECT v.id, j.code, j.cn_title, j.title, v.title AS vtitle, COUNT(*) plays"
        f" {base} GROUP BY v.id ORDER BY plays DESC LIMIT 10", (start, end))
    top_actresses = d.query(
        f"SELECT a.id, a.name, COUNT(*) plays {_base('JOIN jav_actresses ja ON ja.jav_id=j.id JOIN actresses a ON a.id=ja.actress_id')}"
        " GROUP BY a.id ORDER BY plays DESC LIMIT 12", (start, end))
    top_genres = d.query(
        f"SELECT g.name, COUNT(*) plays {_base('JOIN jav_genres jg ON jg.jav_id=j.id JOIN genres g ON g.id=jg.genre_id')}"
        " GROUP BY g.id ORDER BY plays DESC LIMIT 10", (start, end))
    top_studios = d.query(
        f"SELECT s.id, s.name, COUNT(*) plays {_base('JOIN studios s ON s.id=j.studio_id')}"
        " GROUP BY s.id ORDER BY plays DESC LIMIT 8", (start, end))
    # 活跃天数 / 最疯狂的一天
    days = d.query(
        f"SELECT date(p.started_at, 'unixepoch', 'localtime') day, COUNT(*) plays,"
        f" COALESCE(SUM(p.seconds),0) secs {base}"
        " GROUP BY day ORDER BY plays DESC LIMIT 1", (start, end))
    active_days = d.scalar(
        f"SELECT COUNT(DISTINCT date(p.started_at, 'unixepoch', 'localtime')) {base}",
        (start, end))
    best = days[0] if days else {"day": "", "plays": 0, "secs": 0}
    return json_ok({
        "year": year,
        "plays": row["plays"], "total_secs": row["secs"], "total_h": round(row["secs"] / 3600, 1),
        "videos": row["videos"], "active_days": active_days,
        "avg_per_day": round(row["plays"] / max(1, active_days), 1),
        "best_day": best,
        "months": months, "top_videos": top_videos,
        "top_actresses": top_actresses, "top_genres": top_genres, "top_studios": top_studios,
    })


@router.get("/stats/heatmap")
def heatmap(req):
    year = int(req.query.get("year", 0) or time.localtime().tm_year)
    start, end = _year_range(year)
    d = db.db()
    rows = d.query(
        "SELECT date(p.started_at, 'unixepoch', 'localtime') day, COUNT(*) plays"
        " FROM play_log p WHERE p.started_at>=? AND p.started_at<?"
        " GROUP BY day", (start, end))
    by_day = {r["day"]: r["plays"] for r in rows}
    # 生成全年逐日序列（含星期几，供前端渲染 GitHub 风格打卡墙）
    day = time.mktime((year, 1, 1, 0, 0, 0, 0, 0, -1))
    first_wd = time.localtime(day).tm_wday
    days = []
    while True:
        lt = time.localtime(day)
        if lt.tm_year != year:
            break
        key = time.strftime("%Y-%m-%d", lt)
        days.append({"date": key, "plays": by_day.get(key, 0), "wday": lt.tm_wday})
        day += 86400
    return json_ok({"year": year, "first_wday": first_wd, "days": days})


@router.get("/stats/network")
def network(req):
    """女优合作网络：节点 = 有合作的女优，边 = 共同出演次数。"""
    min_weight = max(1, int(req.query.get("min", "2")))
    limit = min(120, max(10, int(req.query.get("limit", "48"))))
    d = db.db()
    edges = d.query(
        "SELECT ja1.actress_id AS src, ja2.actress_id AS dst, COUNT(*) AS weight"
        " FROM jav_actresses ja1 JOIN jav_actresses ja2"
        "   ON ja1.jav_id=ja2.jav_id AND ja1.actress_id<ja2.actress_id"
        " GROUP BY src, dst HAVING weight>=? ORDER BY weight DESC LIMIT ?", (min_weight, limit))
    node_ids = sorted({e["src"] for e in edges} | {e["dst"] for e in edges})
    if not node_ids:
        return json_ok({"nodes": [], "edges": []})
    marks = ",".join("?" for _ in node_ids)
    nodes = d.query(
        f"SELECT id, name, video_count FROM actresses WHERE id IN ({marks})", node_ids)
    return json_ok({"nodes": nodes, "edges": edges,
                    "min_weight": min_weight, "limit": limit})
