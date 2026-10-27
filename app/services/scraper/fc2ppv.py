"""FC2-PPV 专用刮削源（fc2ppvdb）：只处理 FC2-PPV-xxxxxxx 番号，og 标签解析。"""
import html
import re
import urllib.parse

from ... import util
from .base import Metadata, Provider, base_of


def _strip(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


class Fc2PpvProvider(Provider):
    name = "fc2"
    base = "https://fc2ppvdb.com"

    def lookup(self, code: str) -> Metadata | None:
        m = re.search(r"(\d{6,10})$", code)
        if not m:
            return None  # 非 FC2 番号直接跳过，不占请求
        # 域名可配置（设置项 fc2_base 或「源域名列表」）
        base = base_of("fc2", self.base)
        num = m.group(1)
        data = util.http_get(f"{base}/articles/{num}", timeout=15, proxy=self.proxy, retries=1)
        if not data:
            return None
        html_txt = data.decode("utf-8", "replace")

        def og(prop: str) -> str:
            mm = re.search(rf'<meta[^>]+property="og:{prop}"[^>]+content="([^"]*)"', html_txt) or \
                 re.search(rf'<meta[^>]+content="([^"]*)"[^>]+property="og:{prop}"', html_txt)
            return html.unescape(mm.group(1)).strip() if mm else ""

        md = Metadata(code=code)
        title = re.sub(rf"^FC2[\s_-]*PPV[\s_-]*{num}\s*", "", og("title"), flags=re.IGNORECASE).strip()
        md.title = title or og("title")
        md.cover_url = og("image") or ""
        t = re.search(r'<time[^>]+datetime="([\d-]+)', html_txt)
        if t:
            md.release_date = t.group(1)[:10]
        # 女优：站内 actress 链接的文本
        names = []
        for a in re.findall(r'<a[^>]+href="[^"]*actress[^"]*"[^>]*>([\s\S]*?)</a>', html_txt):
            n = _strip(a)
            if n and n not in names:
                names.append(n)
        md.actresses = [type("A", (), {"name": n, "avatar_url": ""})(n) for n in names[:8]]
        if not md.title:
            return None
        md.site = base
        return md
