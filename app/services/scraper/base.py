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
