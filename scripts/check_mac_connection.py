"""Temporary Mac-to-Acer HTTP check, separate from the production operator UI.

Choose Acer's private interface address explicitly, then run:
    python scripts/check_mac_connection.py --bind 192.168.137.1

No camera, file serving, commands, settings, or firewall changes are involved.
The random URL is printed only to the console. Connection logs contain only
source IP and UTC time; the default log directory is the ignored test_reports/.
"""
import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
from pathlib import Path
import secrets
import socket
import threading
import time


TITLE = "Mac→Acer 接続テスト"
PAGE = ("<!doctype html><html lang='ja'><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{TITLE}</title><body><h1>{TITLE}</h1>"
        "<p>このページが表示されれば、Mac のブラウザーから Acer への HTTP 疎通を確認できました。</p>"
        "<p>接続確認専用です。本番操作 UI の認証やカメラ操作を検証するものではありません。</p>"
        "<p>カメラ・シーンの操作、ファイル配信、コマンド実行、設定変更は行いません。</p>"
        "<p>テスト用サーバーは指定時間で自動終了します。</p></body></html>").encode("utf-8")
PRIVATE_NETWORKS = tuple(ipaddress.ip_network(network) for network in
                         ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8"))


def bind_address(value):
    try:
        address = ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError as exc:
        raise argparse.ArgumentTypeError("Acer の明示的な private/loopback IPv4 を指定してください") from exc
    if not any(address in network for network in PRIVATE_NETWORKS):
        raise argparse.ArgumentTypeError("RFC1918/loopback IPv4 のみ使用可能です。0.0.0.0・公開 IP は禁止です")
    return str(address)


def bounded_integer(value, minimum, maximum):
    try:
        result = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("整数を指定してください") from exc
    if not minimum <= result <= maximum:
        raise argparse.ArgumentTypeError(f"{minimum}〜{maximum} の整数を指定してください")
    return result


class ProbeServer(ThreadingHTTPServer):
    allow_reuse_address = False
    daemon_threads = True
    block_on_close = False

    def __init__(self, address, handler):
        self.event_lock = threading.Lock()
        self.stopping = False
        self.log_failed = False
        super().__init__(address, handler)

    def server_bind(self):
        # Exclusive bind is the port check. Never reuse or stop another listener.
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def handle_error(self, request, client_address):
        # Do not expose tracebacks, request headers, URLs, or local filenames.
        pass


class ProbeHandler(BaseHTTPRequestHandler):
    def setup(self):
        self.request.settimeout(2.0)
        super().setup()

    def log_message(self, format, *args):
        pass

    def send_empty(self, code):
        self.send_response_only(code)
        if code == 405:
            self.send_header("Allow", "GET")
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

    def send_error(self, code, message=None, explain=None):
        # Unsupported methods and malformed requests never get a diagnostic page.
        self.send_empty(405 if code == 501 else code)

    def do_GET(self):
        if self.path != self.server.probe_path:
            self.send_empty(404)
            return
        code = 200
        with self.server.event_lock:
            if self.server.stopping or time.monotonic() >= self.server.deadline:
                code = 503
            else:
                record = {"source_ip": self.client_address[0],
                          "time_utc": datetime.now(timezone.utc).isoformat()}
                try:
                    self.server.connection_log.write(json.dumps(record) + "\n")
                    self.server.connection_log.flush()
                except OSError:
                    self.server.log_failed = True
                    code = 503
        if code != 200:
            self.send_empty(code)
            return
        self.send_response_only(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(PAGE)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(PAGE)
        self.close_connection = True


def main(argv=None):
    parser = argparse.ArgumentParser(description=TITLE + "（本番操作 UI の認証とは別の疎通確認）")
    parser.add_argument("--bind", required=True, type=bind_address,
                        help="Acer 側に実際に割り当てられた RFC1918/loopback IPv4。自動推測しません")
    parser.add_argument("--port", type=lambda v: bounded_integer(v, 1, 65535), default=8767,
                        help="待受ポート（既定: 8767）。競合時は起動せず終了します")
    parser.add_argument("--duration-seconds", type=lambda v: bounded_integer(v, 1, 3600), default=600,
                        help="自動終了までの秒数（1〜3600、既定: 600＝10分）")
    parser.add_argument("--log", type=Path,
                        help="接続記録の新規 JSONL（既定: test_reports 内）。既存ファイルは上書きしません")
    args = parser.parse_args(argv)
    log_path = args.log
    if log_path is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
        log_path = Path(__file__).resolve().parents[1] / "test_reports" / f"mac_connection_{stamp}.jsonl"
    server = None
    connection_log = None
    result = 0
    reason = "時間制限"
    try:
        server = ProbeServer((args.bind, args.port), ProbeHandler)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        connection_log = log_path.open("x", encoding="utf-8")
        server.connection_log = connection_log
        server.probe_path = "/" + secrets.token_urlsafe(24)
        server.deadline = time.monotonic() + args.duration_seconds
        print(TITLE + "：本番操作 UI の認証とは別の、接続確認専用です。", flush=True)
        print(f"URL: http://{args.bind}:{args.port}{server.probe_path}", flush=True)
        print(f"接続記録: {log_path.resolve()}", flush=True)
        print(f"{args.duration_seconds} 秒後に自動終了します。Ctrl+C でも終了できます。", flush=True)
        while time.monotonic() < server.deadline:
            if server.log_failed:
                result, reason = 1, "接続記録の書込み失敗"
                break
            server.timeout = min(0.25, max(0.001, server.deadline - time.monotonic()))
            server.handle_request()
    except KeyboardInterrupt:
        reason = "中断"
    except OSError as exc:
        result, reason = 1, "待受または記録ファイルの作成失敗"
        print(f"接続テストを開始・継続できません（OS error {exc.errno}）。"
              "ポートの競合・指定 IP・新規ログの保存先を確認してください。", flush=True)
    finally:
        if server is not None:
            with server.event_lock:
                server.stopping = True
            server.server_close()
        if connection_log is not None:
            connection_log.close()
        print(f"接続テスト終了: {reason}", flush=True)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
