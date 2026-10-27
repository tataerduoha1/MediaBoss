"""MediaBoss 全局配置：config.toml 加载 + 数据目录路径管理（纯标准库）。"""
import os
import sys
import tomllib

APP_NAME = "MediaBoss"
VERSION = "1.5.0"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_PORT = 8656


class Config:
    """启动级配置（来自 config.toml），运行期可变配置存放在数据库中。"""

    def __init__(self):
        self.port = DEFAULT_PORT
        self.host = ""  # 默认监听所有接口（IPv4+IPv6），局域网手机/平板可直接访问；改为 127.0.0.1 可仅本机访问
        self.data_dir = os.path.join(BASE_DIR, "data")
        self._load_toml()

        self.db_path = os.path.join(self.data_dir, "mediaboss.db")
        self.cover_dir = os.path.join(self.data_dir, "covers")
        self.thumb_dir = os.path.join(self.data_dir, "thumbs")
        self.sprite_dir = os.path.join(self.data_dir, "sprites")
        self.shot_dir = os.path.join(self.data_dir, "screenshots")
        self.bin_dir = os.path.join(self.data_dir, "bin")
        self.log_dir = os.path.join(self.data_dir, "logs")
        self.cache_dir = os.path.join(self.data_dir, "cache")
        self.web_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")

    def _load_toml(self):
        path = os.path.join(BASE_DIR, "config.toml")
        if not os.path.exists(path):
            return
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except Exception:
            return
        app = data.get("app", {})
        self.port = int(app.get("port", self.port))
        self.host = str(app.get("host", self.host))
        dd = app.get("data_dir")
        if dd:
            self.data_dir = os.path.abspath(os.path.expanduser(dd))

    def ensure_dirs(self):
        for d in (self.data_dir, self.cover_dir, self.thumb_dir, self.sprite_dir,
                  self.shot_dir, self.bin_dir, self.log_dir, self.cache_dir):
            os.makedirs(d, exist_ok=True)


_config = None


def init_config() -> Config:
    global _config
    _config = Config()
    _config.ensure_dirs()
    return _config


def cfg() -> Config:
    if _config is None:
        return init_config()
    return _config
