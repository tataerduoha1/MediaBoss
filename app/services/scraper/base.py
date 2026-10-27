"""刮削 provider 基础定义。"""
from dataclasses import dataclass, field


@dataclass
class Actress:
    name: str
    avatar_url: str = ""


@dataclass
class Metadata:
    code: str = ""
    title: str = ""
    cover_url: str = ""
    release_date: str = ""
    duration_sec: int = 0
    director: str = ""
    studio: str = ""
    series: str = ""
    score: float = 0.0
    site: str = ""  # 数据来源站点 base URL，下载图片时用作 Referer 防盗链
    actresses: list = field(default_factory=list)
    genres: list = field(default_factory=list)


class Provider:
    """刮削源基类：lookup(code) 返回 Metadata 或 None（未命中/失败）。"""
    name = "base"

    def __init__(self, proxy: str = ""):
        self.proxy = proxy

    def lookup(self, code: str) -> Metadata | None:  # pragma: no cover
        raise NotImplementedError


def base_of(name: str, default: str) -> str:
    """源域名统一解析：离散 {name}_base 设置 > scrape_domains 列表（name=domain 逗号分隔）> 默认。
    兼容从聊天/文档复制粘贴带进来的 Markdown 反引号。"""
    from ... import db
    v = (db.get_setting(f"{name}_base", "") or "").strip().strip("`").strip().rstrip("/")
    if v:
        return v
    for part in (db.get_setting("scrape_domains", "") or "").split(","):
        k, _, val = part.partition("=")
        if k.strip().strip("`") == name and val.strip():
            return val.strip().strip("`").strip().rstrip("/")
    return default
