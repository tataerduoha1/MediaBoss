"""更新任务 API：全量/增量更新、实时进度、取消。"""
from ..httpd import ApiError, json_ok, router
from ..services import scanner, scraper, thumbs


@router.post("/updates/start")
def start(req):
    body = req.json
    mode = str(body.get("mode", "incremental"))
    if mode not in ("incremental", "full"):
        raise ApiError(400, "mode 必须是 incremental 或 full")
    try:
        r = scraper.start_update(mode, rebuild_thumbs=bool(body.get("rebuild_thumbs")))
    except RuntimeError as e:
        raise ApiError(409, str(e))
    return json_ok(r)


@router.get("/updates/progress")
def progress(req):
    return json_ok({
        "update": scraper.progress(),
        "scan": scanner.status(),
        "thumb_queue": thumbs.queue_size(),
    })


@router.post("/updates/cancel")
def cancel(req):
    r = scraper.cancel_update()
    if not r.get("ok"):
        raise ApiError(400, r.get("error", "没有进行中的任务"))
    return json_ok(r)
