"""MissAV 刮削源：详情页 og 标签 + JSON-LD（时长/日期/女优）解析。"""
import html
import json
import re
import urllib.parse

from ... import util
from .base import Metadata, Provider, base_of


def _strip(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def _iso_dur(s: str) -> int:
    """PT1H2M3S / PT30M → 秒。"""
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s or "")
    if not m:
        return 0
    h, mi, se = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + se


class MissAvProvider(Provider):
    name = "missav"
    base = "https://missav.com"

    def lookup(self, code: str) -> Metadata | None:
        # 域名可配置（设置项 missav_base 或「源域名列表」）
        base = base_of("missav", self.base)
        url = f"{base}/{urllib.parse.quote(code.lower())}"
        data = util.http_get(url, timeout=15, proxy=self.proxy, retries=1)
        if not data:
            return None
        html_txt = data.decode("utf-8", "replace")

        def og(prop: str) -> str:
            mm = re.search(rf'<meta[^>]+property="og:{prop}"[^>]+content="([^"]*)"', html_txt) or \
                 re.search(rf'<meta[^>]+content="([^"]*)"[^>]+property="og:{prop}"', html_txt)
            return html.unescape(mm.group(1)).strip() if mm else ""

        md = Metadata(code=code)
        title = re.sub(r"\s*[-–]\s*MissAV.*$", "", og("title"), flags=re.IGNORECASE).strip()
        md.title = title or og("title")
        md.cover_url = og("image") or ""
        # JSON-LD：duration / datePublished / actor
        for block in re.findall(r'<script type="application/ld\+json">([\s\S]*?)</script>', html_txt):
            try:
                obj = json.loads(block.strip())
            except Exception:  # noqa: BLE001
                continue
            items = obj if isinstance(obj, list) else [obj]
            for it in items:
                if not isinstance(it, dict):
                    continue
                if not md.duration_sec and it.get("duration"):
                    md.duration_sec = _iso_dur(it["duration"])
                if not md.release_date and it.get("datePublished"):
                    md.release_date = str(it["datePublished"])[:10]
                actors = it.get("actor") or []
                if isinstance(actors, dict):
                    actors = [actors]
                for a in actors:
                    n = _strip(a.get("name", "")) if isinstance(a, dict) else _strip(str(a))
                    if n and not any(x.name == n for x in md.actresses):
                        md.actresses.append(type("A", (), {"name": n, "avatar_url": ""})(n))
        # 女优兜底：站内 actresses 链接
        if not md.actresses:
            names = [_strip(x) for x in re.findall(r'<a[^>]+href="[^"]*actresses[^"]*"[^>]*>([\s\S]*?)</a>', html_txt)]
            md.actresses = [type("A", (), {"name": n, "avatar_url": ""})(n)
                            for n in dict.fromkeys(filter(None, names))][:8]
        if not md.title:
            return None
        md.site = base
        return md
