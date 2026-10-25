"""SQLite 数据层：线程本地连接、迁移、通用查询辅助。"""
import os
import sqlite3
import threading
import time

from . import config

MIGRATIONS = [
    # 1: 初始 schema
    """
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS directories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        path TEXT NOT NULL UNIQUE,
        enabled INTEGER NOT NULL DEFAULT 1,
        mode TEXT NOT NULL DEFAULT 'auto',
        created_at REAL NOT NULL
    );
    CREATE TABLE IF NOT EXISTS videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fingerprint TEXT NOT NULL UNIQUE,
        path TEXT NOT NULL UNIQUE,
        dir_id INTEGER,
        filename TEXT NOT NULL,
        ext TEXT NOT NULL,
        size INTEGER NOT NULL DEFAULT 0,
        mtime REAL NOT NULL DEFAULT 0,
        duration REAL NOT NULL DEFAULT 0,
        width INTEGER NOT NULL DEFAULT 0,
        height INTEGER NOT NULL DEFAULT 0,
        bitrate INTEGER NOT NULL DEFAULT 0,
        codec TEXT NOT NULL DEFAULT '',
        title TEXT NOT NULL DEFAULT '',
        play_count INTEGER NOT NULL DEFAULT 0,
        last_played_at REAL NOT NULL DEFAULT 0,
        resume_position REAL NOT NULL DEFAULT 0,
        watched INTEGER NOT NULL DEFAULT 0,
        rating INTEGER NOT NULL DEFAULT 0,
        favorite INTEGER NOT NULL DEFAULT 0,
        thumb_status INTEGER NOT NULL DEFAULT 0,
        scrape_status INTEGER NOT NULL DEFAULT 0,
        scrape_attempts INTEGER NOT NULL DEFAULT 0,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_videos_created ON videos(created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_videos_title ON videos(title);
    CREATE TABLE IF NOT EXISTS tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE
    );
    CREATE TABLE IF NOT EXISTS video_tags (
        video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
        tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
        UNIQUE(video_id, tag_id)
    );
    CREATE TABLE IF NOT EXISTS jav (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id INTEGER NOT NULL UNIQUE REFERENCES videos(id) ON DELETE CASCADE,
        code TEXT NOT NULL UNIQUE,
        title TEXT NOT NULL DEFAULT '',
        cn_title TEXT NOT NULL DEFAULT '',
        cover_path TEXT NOT NULL DEFAULT '',
        cover_url TEXT NOT NULL DEFAULT '',
        release_date TEXT NOT NULL DEFAULT '',
        duration_sec INTEGER NOT NULL DEFAULT 0,
        director TEXT NOT NULL DEFAULT '',
        studio_id INTEGER,
        series_id INTEGER,
        score REAL NOT NULL DEFAULT 0,
        bought INTEGER NOT NULL DEFAULT 0,
        updated_at REAL NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_jav_code ON jav(code);
    CREATE TABLE IF NOT EXISTS actresses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        avatar_path TEXT NOT NULL DEFAULT '',
        birth TEXT NOT NULL DEFAULT '',
        height TEXT NOT NULL DEFAULT '',
        info_json TEXT NOT NULL DEFAULT '',
        video_count INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS jav_actresses (
        jav_id INTEGER NOT NULL REFERENCES jav(id) ON DELETE CASCADE,
        actress_id INTEGER NOT NULL REFERENCES actresses(id) ON DELETE CASCADE,
        UNIQUE(jav_id, actress_id)
    );
    CREATE TABLE IF NOT EXISTS genres (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        video_count INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS jav_genres (
        jav_id INTEGER NOT NULL REFERENCES jav(id) ON DELETE CASCADE,
        genre_id INTEGER NOT NULL REFERENCES genres(id) ON DELETE CASCADE,
        UNIQUE(jav_id, genre_id)
    );
    CREATE TABLE IF NOT EXISTS studios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        video_count INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS series (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        video_count INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS watch_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
        started_at REAL NOT NULL,
        seconds REAL NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_history_started ON watch_history(started_at DESC);
    CREATE TABLE IF NOT EXISTS bookmarks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
        time_sec REAL NOT NULL,
        image_path TEXT NOT NULL DEFAULT '',
        note TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL
    );
    CREATE TABLE IF NOT EXISTS downloads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url TEXT NOT NULL,
        name TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'pending',
        provider TEXT NOT NULL DEFAULT 'clouddrive2',
        progress REAL NOT NULL DEFAULT 0,
        size INTEGER NOT NULL DEFAULT 0,
        downloaded INTEGER NOT NULL DEFAULT 0,
        speed TEXT NOT NULL DEFAULT '',
        msg TEXT NOT NULL DEFAULT '',
        remote_id TEXT NOT NULL DEFAULT '',
        save_dir TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        expires REAL NOT NULL
    );
    CREATE TABLE IF NOT EXISTS api_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        token TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL,
        last_used REAL NOT NULL DEFAULT 0
    );
    """,
    # 2: 刮削重试冷却 + 性能索引 + 放宽默认扫描间隔
    """
    ALTER TABLE videos ADD COLUMN next_retry_at REAL NOT NULL DEFAULT 0;
    CREATE INDEX IF NOT EXISTS idx_videos_scrape ON videos(scrape_status, next_retry_at);
    CREATE INDEX IF NOT EXISTS idx_videos_dir ON videos(dir_id);
    CREATE INDEX IF NOT EXISTS idx_ja_jav ON jav_actresses(jav_id);
    CREATE INDEX IF NOT EXISTS idx_ja_act ON jav_actresses(actress_id);
    CREATE INDEX IF NOT EXISTS idx_jg_jav ON jav_genres(jav_id);
    CREATE INDEX IF NOT EXISTS idx_jg_genre ON jav_genres(genre_id);
    CREATE INDEX IF NOT EXISTS idx_history_video ON watch_history(video_id);
    CREATE INDEX IF NOT EXISTS idx_bookmarks_video ON bookmarks(video_id);
    INSERT INTO settings(key, value) VALUES('scan_interval_min', '5')
        ON CONFLICT(key) DO UPDATE SET value='5' WHERE CAST(settings.value AS INTEGER) < 5;
    """,
    # 3: 观看历史去重（每个视频只保留一条，取最近观看）+ video_id 唯一索引支持 upsert
    """
    DELETE FROM watch_history WHERE id NOT IN (SELECT MAX(id) FROM watch_history GROUP BY video_id);
    DROP INDEX IF EXISTS idx_history_video;
    CREATE UNIQUE INDEX IF NOT EXISTS idx_history_video_uniq ON watch_history(video_id);
    """,
    # 4: 片单/合集 + 播放流水（年度报告/热力日历数据源；由 watch_history 现有记录播种）
    """
    CREATE TABLE IF NOT EXISTS collections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        cover_video_id INTEGER,
        sort INTEGER NOT NULL DEFAULT 0,
        created_at REAL NOT NULL
    );
    CREATE TABLE IF NOT EXISTS collection_items (
        collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
        video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
        added_at REAL NOT NULL,
        UNIQUE(collection_id, video_id)
    );
    CREATE TABLE IF NOT EXISTS play_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
        started_at REAL NOT NULL,
        seconds REAL NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_playlog_started ON play_log(started_at);
    CREATE INDEX IF NOT EXISTS idx_playlog_video ON play_log(video_id);
    CREATE INDEX IF NOT EXISTS idx_coll_items_coll ON collection_items(collection_id);
    INSERT INTO play_log(video_id, started_at, seconds)
        SELECT video_id, started_at, seconds FROM watch_history WHERE video_id NOT IN
        (SELECT video_id FROM play_log);
    """,
]


class DB:
    """线程安全的 SQLite 封装：写操作全局锁，读操作线程本地连接。"""

    def __init__(self, path: str):
        self.path = path
        self._write_lock = threading.RLock()
        self._local = threading.local()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.migrate()

    def _conn(self) -> sqlite3.Connection:
        c = getattr(self._local, "conn", None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=NORMAL")
            c.execute("PRAGMA foreign_keys=ON")
            c.execute("PRAGMA busy_timeout=30000")
            self._local.conn = c
        return c

    def migrate(self):
        c = self._conn()
        c.execute("PRAGMA user_version")
        ver = c.execute("PRAGMA user_version").fetchone()[0]
        with self._write_lock:
            for i, script in enumerate(MIGRATIONS, start=1):
                if i > ver:
                    c.executescript(script)
                    c.execute(f"PRAGMA user_version = {i}")
                    c.commit()

    def execute(self, sql: str, params=()) -> sqlite3.Cursor:
        with self._write_lock:
            c = self._conn()
            for i in range(5):
                try:
                    cur = c.execute(sql, params)
                    c.commit()
                    return cur
                except sqlite3.OperationalError as e:
                    # 多写者并发时 Windows 下偶发锁竞争，退避重试
                    if "locked" not in str(e) or i == 4:
                        raise
                    time.sleep(0.5 * (i + 1))

    def exec_many(self, sql: str, rows) -> None:
        with self._write_lock:
            c = self._conn()
            c.executemany(sql, rows)
            c.commit()

    def query(self, sql: str, params=()) -> list[dict]:
        rows = self._conn().execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def query_one(self, sql: str, params=()) -> dict | None:
        r = self._conn().execute(sql, params).fetchone()
        return dict(r) if r else None

    def scalar(self, sql: str, params=(), default=0):
        r = self._conn().execute(sql, params).fetchone()
        if r is None or r[0] is None:
            return default
        return r[0]

    def close(self):
        c = getattr(self._local, "conn", None)
        if c:
            c.close()
            self._local.conn = None


_db = None


def init_db():
    global _db
    _db = DB(config.cfg().db_path)
    return _db


def db() -> DB:
    return _db


# ---------- settings helpers ----------

DEFAULT_SETTINGS = {
    "password_hash": "",          # sha256(salt+password)
    "password_salt": "mediaboss",
    "password": "admin",          # 明文仅首次初始化使用，随后立即散列
    "scan_interval_min": "5",
    "auto_scan": "1",
    "scrape_retry_cooldown_min": "15",   # 刮削失败后的重试冷却（分钟）
    "theme": "dark",                     # dark / light / auto
    "jav_mode": "1",              # 1=JAV 模式 0=纯视频模式
    "scrape_enabled": "1",
    "scrape_provider_order": "javbus,javdb",
    "translate_enabled": "1",
    "proxy": "",
    "ffmpeg_path": "",
    "mpv_path": "",
    "thumb_workers": "2",
    "sprite_enabled": "1",
    "lan_access": "0",
    "ext_token_enabled": "1",
    "cd2_url": "",
    "cd2_user": "",
    "cd2_pass": "",
    "download_dir": "",
    "organize_template": "{code} {title}",
    "organize_enabled": "0",
    "hide_watched": "0",
    "page_size": "60",
    "accent_color": "",                   # A10 主题强调色，空=默认粉
    "wallpaper": "",                      # A10 背景壁纸 URL/路径，空=纯色
    "lang": "zh",                         # A10 界面语言 zh / en
}


def get_setting(key: str, default: str = "") -> str:
    row = db().query_one("SELECT value FROM settings WHERE key=?", (key,))
    if row is None:
        return DEFAULT_SETTINGS.get(key, default)
    return row["value"]


def set_setting(key: str, value: str) -> None:
    db().execute(
        "INSERT INTO settings(key, value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
    if key in DEFAULT_SETTINGS:
        DEFAULT_SETTINGS[key] = str(value)


def all_settings() -> dict:
    out = dict(DEFAULT_SETTINGS)
    for row in db().query("SELECT key, value FROM settings"):
        out[row["key"]] = row["value"]
    return out
