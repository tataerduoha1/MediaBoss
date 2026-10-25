"""JavBus 刮削源：HTML 正则解析（详情页直取，失败时走搜索页）。"""
import re
import urllib.parse

from ... import util
from .base import Metadata, Provider

LABELS = {
    "id": r"识别码|識別碼|ID",
    "date": r"发售日期|發售日期|発売日|Release Date",
    "length": r"长度|長度|長さ|Length",
    "director": r"导演|導演|監督|Director",
    "studio": r"制作商|製作商|製作|スタジオ|Studio",
    "label": r"发行商|發行商|發行|レーベル|Label",
    "series": r"系列|系列",
}


def _text(html: str) -> str:
    html = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", "", html)
    return re.sub(r"<[^>]+>", "", html)


class JavBusProvider(Provider):
    name = "javbus"
    base = "https://www.javbus.com"

    def lookup(self, code: str) -> Metadata | None:
        html = self._fetch(f"{self.base}/{code}")
        if html and (f">{code}<" in html.upper() or code.upper() in html.upper()[:4000]):
            md = self.parse_detail(html, code)
            if md and md.title:
                return md
        # 搜索页兜底
        html = self._fetch(f"{self.base}/search/{code}&type=1&parent=ce")
        if not html:
            return None
        m = re.search(r'<a class="movie-box" href="([^"]+/([A-Z0-9\-]+))"[\s\S]{0,400}?</a>', html)
        if not m:
            return None
        detail_url = m.group(1)
        html = self._fetch(detail_url)
        if not html:
            return None
        return self.parse_detail(html, code)

    def _fetch(self, url: str) -> str | None:
        data = util.http_get(url, timeout=15, proxy=self.proxy, retries=1)
        if not data:
            return None
        try:
            return data.decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            return None

    def parse_detail(self, html: str, code: str) -> Metadata | None:
        md = Metadata(code=code)
        m = re.search(r"<h3>(?:<a[^>]*>)?([^<]+)</a></h3>", html) or re.search(r"<title>([^<]+)</title>", html)
        if m:
            md.title = re.sub(r"\s*-\s*JavBus.*$", "", m.group(1)).strip()
        m = re.search(r'<a class="bigImage" href="([^"]+)"', html) or re.search(r'<img[^>]+class="[^"]*bigImage[^"]*"[^>]+src="([^"]+)"', html)
        if m:
            md.cover_url = urllib.parse.urljoin(self.base, m.group(1))
        # 信息块
        container = re.search(r'<div class="col-md-3 info">([\s\S]*?)</div>\s*</div>', html)
        block = container.group(1) if container else html
        for key, label in LABELS.items():
            m = re.search(rf'<p><span class="header">(?:{label})[:：]?</span>([\s\S]*?)(?:</p>|<p>)', block)
            if not m:
                continue
            seg = m.group(1)
            if key == "id":
                md.code = _text(seg).strip() or code
            elif key == "date":
                d = re.search(r"\d{4}-\d{2}-\d{2}", seg)
                md.release_date = d.group(0) if d else ""
            elif key == "length":
                n = re.search(r"\d+", _text(seg))
                md.duration_sec = int(n.group(0)) * 60 if n else 0
            elif key in ("director", "studio", "series"):
                a = re.search(r"<a[^>]*>([^<]+)</a>", seg)
                val = (a.group(1) if a else _text(seg)).strip()
                if key == "director":
                    md.director = val
                elif key == "studio":
                    md.studio = val
                else:
                    md.series = val
        # 演员与头像。新版页面结构：
        #   <a href="/star/x"><img src="/pics/actress/x.jpg" title="名"></a>
        #   <div class="star-name"><a title="名">名</a></div>
        # 只认 /star/ 链接与 star-name 区，绝不扫全页 img（样片图 title 是影片标题，会污染演员库）
        seen: set[str] = set()
        for m in re.finditer(r'<a[^>]+href="[^"]*/star/[^"]*"[^>]*>\s*<img[^>]+src="([^"]*)"[^>]*title="([^"]*)"', html):
            name = m.group(2).strip()
            if name and name not in seen:
                seen.add(name)
                md.actresses.append({"name": name, "avatar_url": urllib.parse.urljoin(self.base, m.group(1))})
        for m in re.finditer(r'<div class="star-name"><a[^>]*>([^<]+)</a>', html):
            name = m.group(1).strip()
            if name and name not in seen:
                seen.add(name)
                md.actresses.append({"name": name, "avatar_url": ""})
        # 类别：<span class="genre"><label><input ...><a href="/genre/x">名</a></label></span>
        genres: list[str] = []
        for m in re.finditer(r'<span class="genre"[^>]*><label>(?:<input[^>]*>)?<a[^>]*href="[^"]*/genre/[^"]*"[^>]*>([^<]+)</a>', html):
            g = m.group(1).strip()
            if g and g not in genres:
                genres.append(g)
        md.genres = genres
        md.site = self.base
        return md if md.title else None
