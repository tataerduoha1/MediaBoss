"""DMM/FANZA 刮削源：数据最全（日文），需成人验证 cookie；信息表按日文字段解析。"""
import html
import re
import urllib.parse

from ... import util
from .base import Metadata, Provider, base_of

_H = {"Cookie": "age_check_done=1"}


def _strip(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def _cell(table: str, label: str) -> str:
    """在信息表里按日文标签取相邻单元格文本。"""
    m = re.search(rf"<th[^>]*>\s*{label}[\s\S]{{0,10}}?</th>\s*<td[^>]*>([\s\S]*?)</td>", table)
    return _strip(m.group(1)) if m else ""


class DmmProvider(Provider):
    name = "dmm"
    base = "https://www.dmm.co.jp"

    def lookup(self, code: str) -> Metadata | None:
        # 域名可配置（设置项 dmm_base 或「源域名列表」）
        base = base_of("dmm", self.base)
        q = urllib.parse.quote(code)
        data = util.http_get(f"{base}/search/=/searchstr={q}/", timeout=20, proxy=self.proxy,
                             retries=1, headers=_H)
        if not data:
            return None
        html_txt = data.decode("utf-8", "replace")
        # 搜索结果第一个数字内容详情链接（digital/videoa 或 mono/dvd）
        m = re.search(r'href="(https?://[^"]*?(?:digital/videoa|mono/dvd|digital/amateur)/-/detail/=/cid=[^"/]+/?)"',
                      html_txt)
        if not m:
            return None
        data = util.http_get(m.group(1), timeout=20, proxy=self.proxy, retries=1, headers=_H)
        if not data:
            return None
        html_txt = data.decode("utf-8", "replace")

        md = Metadata(code=code)
        t = re.search(r'<h1[^>]+id="title"[^>]*>([\s\S]*?)</h1>', html_txt)
        if t:
            md.title = _strip(t.group(1))
        table_m = re.search(r'<table class="mg-b20"[\s\S]*?</table>', html_txt)
        table = table_m.group(0) if table_m else html_txt
        date = _cell(table, "(?:商品|配信)?(?:発売|發售)日") or _cell(table, "配信開始日")
        if date:
            md.release_date = date.replace("/", "-")[:10]
        mins = _cell(table, "収録時間")
        if mins:
            mm = re.search(r"(\d+)", mins)
            if mm:
                md.duration_sec = int(mm.group(1)) * 60
        md.director = _cell(table, "監督") or ""
        md.studio = _cell(table, "メーカー|制造商|製作商") or ""
        md.series = _cell(table, "シリーズ|系列") or ""
        # 女优 / 类别：article=actress / article=genre 链接
        for a, target in ((r"actress", "actresses"), (r"genre", "genres")):
            names = []
            for x in re.findall(rf'<a[^>]+href="[^"]*article={a}[^"]*"[^>]*>([\s\S]*?)</a>', table):
                n = _strip(x)
                if n and n not in names:
                    names.append(n)
            if target == "actresses":
                md.actresses = [type("A", (), {"name": n, "avatar_url": ""})(n) for n in names[:10]]
            else:
                md.genres = names
        c = re.search(r'<a name="package-image"[^>]*>\s*<img[^>]+src="([^"]+)"', html_txt) or \
            re.search(r'<img[^>]+src="([^"]*?/ps\.jpg[^"]*)"', html_txt)
        if c:
            # 小图换大图（ps.jpg/pt.jpg → pl.jpg）
            md.cover_url = re.sub(r"/p[st]\.jpg", "/pl.jpg", c.group(1))
        if not md.title:
            return None
        md.site = base
        return md
