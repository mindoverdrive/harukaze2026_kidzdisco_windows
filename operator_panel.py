"""Small authenticated browser panel for the Manager's camera command mailbox."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
from pathlib import Path
import queue
import secrets
import threading
from urllib.parse import urlsplit

from camera_controls import CONTROL_SPECS, save_controls


class OperatorPanel:
    def __init__(self, relay, config_path, host="127.0.0.1", port=8766):
        address = ipaddress.ip_address(host)
        if address.version != 4 or address.is_unspecified or not (address.is_private or address.is_loopback):
            raise ValueError("操作UIにはAcerのPAN/LANまたは127.0.0.1のIPv4を指定してください")
        self.relay = relay
        self.config_path = Path(config_path)
        self.token = secrets.token_urlsafe(24)
        self.actions = queue.Queue(maxsize=1)
        self.html = Path(__file__).with_suffix(".html").read_bytes()
        self.server = self.thread = None
        self.host, self.port = host, port

    def start(self):
        panel = self

        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                super().setup()
                self.connection.settimeout(3)

            def log_message(self, *_args):
                pass

            def reply(self, status, payload, content_type="application/json; charset=utf-8"):
                body = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'")
                self.end_headers()
                self.wfile.write(body)

            def authorized(self):
                provided = self.headers.get("Authorization", "")
                return secrets.compare_digest(provided, "Bearer " + panel.token)

            def do_GET(self):
                path = urlsplit(self.path).path
                if path == "/":
                    self.reply(200, panel.html, "text/html; charset=utf-8")
                elif path == "/api/status" and self.authorized():
                    self.reply(200, {"camera": panel.relay.controls.snapshot(), "specs": CONTROL_SPECS,
                                     "config": panel.config_path.name, "camera_frame_id": panel.relay.frame_id,
                                     "camera_error": panel.relay.last_error})
                else:
                    self.reply(401 if path.startswith("/api/") else 404, {"error": "起動時の操作URLで開いてください"})

            def do_POST(self):
                if not self.authorized():
                    self.reply(401, {"error": "起動時の操作URLで開いてください"})
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 2048:
                        raise ValueError("リクエストサイズが不正です")
                    if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                        raise ValueError("JSONを指定してください")
                    data = json.loads(self.rfile.read(length))
                    if not isinstance(data, dict):
                        raise ValueError("JSONオブジェクトを指定してください")
                    if self.path == "/api/camera":
                        sequence = panel.relay.controls.submit(data)
                        self.reply(202, {"sequence": sequence})
                    elif self.path == "/api/save" and set(data) == {"sequence"}:
                        if type(data["sequence"]) is not int or data["sequence"] <= 0:
                            raise ValueError("適用済みの設定番号を指定してください")
                        saved = save_controls(panel.config_path, panel.relay.controls, data["sequence"])
                        self.reply(200, {"saved": saved})
                    elif self.path == "/api/action" and data in ({"action": "next"}, {"action": "quit"}):
                        panel.actions.put_nowait(data["action"])
                        self.reply(202, {"action": data["action"]})
                    else:
                        self.reply(404, {"error": "対象の操作がありません"})
                except (ValueError, UnicodeError) as exc:
                    self.reply(400, {"error": str(exc)})
                except (RuntimeError, queue.Full) as exc:
                    self.reply(409, {"error": str(exc) or "前の操作を処理中です"})
                except OSError as exc:
                    self.reply(500, {"error": f"保存できません: {exc}"})

        class Server(ThreadingHTTPServer):
            daemon_threads = True
            slots = threading.BoundedSemaphore(8)

            def process_request(self, request, client_address):
                if not self.slots.acquire(blocking=False):
                    self.shutdown_request(request)
                    return
                try:
                    super().process_request(request, client_address)
                except BaseException:
                    self.slots.release()
                    raise

            def process_request_thread(self, request, client_address):
                try:
                    super().process_request_thread(request, client_address)
                finally:
                    self.slots.release()

        self.server = Server((self.host, self.port), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
        try:
            self.thread.start()
        except BaseException:
            self.server.server_close()
            raise
        print(f"[Operator] http://{self.host}:{self.port}/#token={self.token}")
        return self

    def consume_action(self):
        try:
            return self.actions.get_nowait()
        except queue.Empty:
            return None

    def close(self):
        if self.server is not None:
            if self.thread is not None and self.thread.is_alive():
                self.server.shutdown()
                self.thread.join(timeout=2)
            self.server.server_close()
        return self.thread is None or not self.thread.is_alive()
