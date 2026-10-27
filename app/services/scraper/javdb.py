"""JavDB 刮削源（备选）：详情字段较少时兜底。"""
import re
import urllib.parse

from ... import util
from .base import Metadata, Provider, base_of


class JavDBProvider(Provider):
    name = "javdb"
    base = "https://javdb.com"

    def lookup(self, code: str) -> Metadata | None:
        # 域名可配置（设置项 javdb_base 或「源域名列表」）：留空用默认
        base = base_of("javdb", self.base)
        data = util.http_get(f"{base}/search?q={code}&f=all", timeout=15,
                             proxy=self.proxy, retries=1,
                             headers={"Cookie": "locale=zh_CN"})
        if not data:
            return None
        html = data.decode("utf-8", "replace")
        m = re.search(r'<a class="box" href="(/v/[^"]+)"[\s\S]{0,600}?<strong[^>]*>\s*([A-Z0-9\-]+)\s*</strong>', html)
        if not m:
            return None
        detail_url = base + m.group(1)
        data = util.http_get(detail_url, timeout=15, proxy=self.proxy, retries=1,
                             headers={"Cookie": "locale=zh_CN"})
        if not data:
            return None
        html = data.decode("utf-8", "replace")
        md = Metadata(code=code)
        t = re.search(r"<title>([^<]+)</title>", html)
        if t:
            md.title = re.sub(r"\s*-\s*JavDB.*$", "", t.group(1)).strip()
        c = re.search(r'<img[^>]+class="video-cover"[^>]+src="([^"]+)"', html) or \
            re.search(r'<img[^>]+src="([^"]+)"[^>]+class="video-cover"', html)
        if c:
            md.cover_url = urllib.parse.urljoin(base, c.group(1))
        panel = re.search(r'<nav class="panel[\s\S]*?</nav>', html)
        block = panel.group(0) if panel else html

        def field_value(label_re: str) -> str:
            m = re.search(rf'<strong class="current-text">\s*{label_re}\s*:?\s*</strong>\s*<span[^>]*>([\s\S]*?)</span>', block)
            if m:
                return re.sub(r"<[^>]+>", "", m.group(1)).strip()
            m = re.search(rf'{label_re}[:：]\s*</td>\s*<td[^>]*>([\s\S]*?)</td>', block)
            return re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else ""

        d = re.search(r"\d{4}-\d{2}-\d{2}", field_value("日期|Date|Released"))
        if d:
            md.release_date = d.group(0)
        md.studio = field_value("片商|Maker|Studio")
        md.series = field_value("系列|Series")
        n = re.search(r"\d+", field_value("時長|时长|Duration"))
        if n:
            md.duration_sec = int(n.group(0)) * 60
        s = re.search(r"(\d+(?:\.\d+)?)分", block)
        if s:
            md.score = float(s.group(1))
        actors_zone = re.search(r"(?:女優|演员|Actor[s]?)[\s\S]*?(<[\s\S]*?)(?:類別|类别|Category|</nav>)", block)
        if actors_zone:
            for am in re.finditer(r'<a[^>]*href="/actors/[^"]*"[^>]*>([^<]+)</a>', actors_zone.group(1)):
                md.actresses.append({"name": am.group(1).strip(), "avatar_url": ""})
        if md.title:
            md.site = self.base
            return md
        return None
