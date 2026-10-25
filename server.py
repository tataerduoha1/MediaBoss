"""MediaBoss 服务入口：初始化配置/数据库/后台任务，启动 HTTP 服务。"""
import argparse
import signal
import sys
import threading

from app import config, db, util
from app.httpd import create_server


def main():
    parser = argparse.ArgumentParser(description="MediaBoss - 本地视频/JAV 管理一站式解决方案")
    parser.add_argument("-port", type=int, default=None, help="监听端口")
    parser.add_argument("-host", default=None, help="监听地址 (0.0.0.0 允许局域网访问)")
    parser.add_argument("--data-dir", default=None, help="数据目录")
    parser.add_argument("--no-browser", action="store_true", help="启动时不打开浏览器")
    args = parser.parse_args()

    cfg = config.init_config()
    if args.port:
        cfg.port = args.port
    if args.host:
        cfg.host = args.host
    if args.data_dir:
        cfg.data_dir = args.data_dir
        cfg.db_path = f"{cfg.data_dir}/mediaboss.db"
    cfg.ensure_dirs()

    util.logger().info("%s v%s 启动中...", config.APP_NAME, config.VERSION)
    db.init_db()

    # 首次启动写入默认密码散列
    from app.api import auth as _auth
    _auth._ensure_password()

    # 后台服务
    from app.services import downloads, scanner, scraper, thumbs
    thumbs.start()
    scanner.start()
    if db.get_setting("scrape_enabled", "1") == "1":
        scraper.start()
    downloads.start()

    server = create_server()
    url = f"http://{'127.0.0.1' if cfg.host in ('0.0.0.0', '') else cfg.host}:{cfg.port}"
    util.logger().info("服务已启动: %s", url)

    stop_event = threading.Event()

    def _stop(signum, frame):
        util.logger().info("收到退出信号，正在关闭...")
        stop_event.set()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    threading.Thread(target=server.serve_forever, name="http", daemon=True).start()

    # Windows 下自动打开浏览器
    if sys.platform == "win32" and not args.no_browser:
        import webbrowser
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    try:
        while not stop_event.is_set():
            stop_event.wait(1.0)
    finally:
        server.shutdown()
        scanner.stop()
        scraper.stop()
        thumbs.stop()
        downloads.stop()
        util.logger().info("MediaBoss 已退出")


if __name__ == "__main__":
    main()
