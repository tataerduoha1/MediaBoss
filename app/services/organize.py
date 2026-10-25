"""目录整理：按模板重命名/移动视频文件（预览 + 应用两步，保证安全）。"""
import os
import re

from .. import db, util


def _render(template: str, ctx: dict) -> str:
    out = template
    for k, v in ctx.items():
        out = out.replace("{" + k + "}", str(v))
    return util.safe_filename(out)


def preview(video_ids: list[int] | None = None) -> dict:
    """生成整理计划（不执行）。仅处理 JAV 模式下已成功刮削的视频。"""
    d = db.db()
    template = db.get_setting("organize_template", "{code} {title}")
    if video_ids:
        marks = ",".join("?" for _ in video_ids)
        rows = d.query(
            f"SELECT v.id, v.path, v.ext, j.code, j.title FROM videos v JOIN jav j ON j.video_id=v.id"
            f" WHERE v.id IN ({marks}) AND v.scrape_status=1", video_ids)
    else:
        rows = d.query(
            "SELECT v.id, v.path, v.ext, j.code, j.title FROM videos v JOIN jav j ON j.video_id=v.id"
            " WHERE v.scrape_status=1")
    plan = []
    for r in rows:
        ctx = {
            "code": r["code"], "title": r["title"] or r["code"],
            "date": "", "ext": r["ext"].lstrip("."),
        }
        new_name = _render(template, ctx) + r["ext"]
        parent = os.path.dirname(r["path"])
        new_path = util.norm_path(os.path.join(parent, new_name))
        if new_path != r["path"]:
            plan.append({"video_id": r["id"], "old_path": r["path"], "new_path": new_path})
    return {"template": template, "items": plan}


def apply(plan: list[dict]) -> dict:
    """执行整理计划：重命名文件并同步数据库路径。"""
    ok = failed = 0
    errors = []
    d = db.db()
    for item in plan:
        old, new = item["old_path"], item["new_path"]
        try:
            if not os.path.isfile(old):
                raise FileNotFoundError(old)
            if os.path.exists(new):
                raise FileExistsError(new)
            os.makedirs(os.path.dirname(new), exist_ok=True)
            os.rename(old, new)
            d.execute("UPDATE videos SET path=?, filename=?, updated_at=? WHERE id=?",
                      (new, os.path.basename(new), util.now(), item["video_id"]))
            ok += 1
        except Exception as e:  # noqa: BLE001
            failed += 1
            errors.append({"video_id": item["video_id"], "error": str(e)})
    return {"ok": ok, "failed": failed, "errors": errors[:20]}
