"""JavLib 刮削源：HTML 正则解析（搜索命中唯一番号时 302 直达详情页）。"""
import html
import re
import urllib.parse

from ... import util
from .base import Metadata, Provider, base_of


def _strip(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s or "")
    return html.unescape(s).strip()


class JavLibProvider(Provider):
    name = "javlib"
    base = "https://www.javlibrary.com/cn"

    def _fetch(self, url: str) -> str | None:
        data = util.http_get(url, timeout=15, proxy=self.proxy, retries=1)
        return None if not data else data.decode("utf-8", "replace")

    def _field(self, block: str, key: str) -> str:
        m = re.search(rf'<div id="{key}"[^>]*>[\s\S]*?<td[^>]*class="text"[^>]*>([\s\S]*?)</td>', block)
        if not m:
            m = re.search(rf'<div id="{key}"[^>]*>[\s\S]*?<td[^>]*>([\s\S]*?)</td>', block)
        return _strip(m.group(1)) if m else ""

    def lookup(self, code: str) -> Metadata | None:
        # 域名可配置（设置项 javlib_base 或「源域名列表」）：JavLib 常因封锁更换镜像域名
        base = base_of("javlib", self.base)
        html_txt = self._fetch(f"{base}/vl_searchbyid.php?keyword={urllib.parse.quote(code)}")
        if not html_txt:
            return None
        if 'id="video_title"' not in html_txt:
            # 多结果列表页：取第一个详情链接再进
            m = re.search(r'href="\.?/?\?v=([a-z0-9]+)"', html_txt, re.IGNORECASE)
            if not m:
                return None
            html_txt = self._fetch(f"{base}/?v={m.group(1)}")
            if not html_txt or 'id="video_title"' not in html_txt:
                return None
        md = Metadata(code=code)
        t = re.search(r'<div id="video_title"[^>]*>\s*<a[^>]*>([\s\S]*?)</a>', html_txt)
        if t:
            title = _strip(t.group(1))
            # 标题常以番号开头，去掉番号前缀
            md.title = re.sub(rf"^{re.escape(code)}\s*", "", title, flags=re.IGNORECASE).strip() or title
        c = re.search(r'<img id="video_jacket_img"[^>]+src="([^"]+)"', html_txt) or \
            re.search(r'<img[^>]+src="([^"]+)"[^>]+id="video_jacket_img"', html_txt)
        if c:
            md.cover_url = urllib.parse.urljoin(base, c.group(1))
        md.release_date = self._field(html_txt, "video_date")
        mins = re.search(r'<div id="video_length"[^>]*>[\s\S]*?<span class="text">(\d+)</span>', html_txt)
        if mins:
            md.duration_sec = int(mins.group(1)) * 60
        md.director = self._field(html_txt, "video_director")
        md.studio = self._field(html_txt, "video_maker")
        md.series = self._field(html_txt, "video_label")
        score = re.search(r'<span class="score">\(\s*([\d.]+)', html_txt)
        if score:
            md.score = float(score.group(1))
        gblock = re.search(r'<div id="video_genres"[^>]*>([\s\S]*?)</td>', html_txt)
        if gblock:
            md.genres = [_strip(x) for x in re.findall(r"<a[^>]*>([\s\S]*?)</a>", gblock.group(1)) if _strip(x)]
        cblock = re.search(r'<div id="video_cast"[^>]*>([\s\S]*?)</td>', html_txt)
        if cblock:
            md.actresses = [(lambda n: type("A", (), {"name": n, "avatar_url": ""})(n))(_strip(x))
                            for x in re.findall(r"<a[^>]*>([\s\S]*?)</a>", cblock.group(1)) if _strip(x)]
        if not md.title:
            return None
        md.site = base
        return md
