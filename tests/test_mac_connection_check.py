from datetime import datetime
import http.client
import json
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
from unittest import mock
from urllib.parse import urlsplit

from scripts import check_mac_connection as check


class MacConnectionCheckTests(unittest.TestCase):
    def test_bind_requires_explicit_rfc1918_or_loopback_ipv4(self):
        for address in ("10.0.0.1", "172.16.0.1", "172.31.255.254", "192.168.137.1", "127.0.0.1"):
            with self.subTest(address=address):
                self.assertEqual(check.bind_address(address), address)
        for address in ("0.0.0.0", "8.8.8.8", "169.254.1.1", "100.64.0.1", "172.15.0.1",
                        "172.32.0.1", "192.0.2.1", "::1", "localhost", ""):
            with self.subTest(address=address):
                with self.assertRaises(check.argparse.ArgumentTypeError):
                    check.bind_address(address)

    def test_missing_bind_or_invalid_limits_never_create_a_listener(self):
        for arguments in ([], ["--bind", "0.0.0.0"],
                          ["--bind", "127.0.0.1", "--port", "0"],
                          ["--bind", "127.0.0.1", "--port", "65536"],
                          ["--bind", "127.0.0.1", "--duration-seconds", "0"],
                          ["--bind", "127.0.0.1", "--duration-seconds", "3601"]):
            with self.subTest(arguments=arguments), mock.patch.object(check, "ProbeServer") as server:
                with mock.patch("sys.stderr"), self.assertRaises(SystemExit) as raised:
                    check.main(arguments)
                self.assertEqual(raised.exception.code, 2)
                server.assert_not_called()

    def test_real_get_only_random_page_and_private_log_then_automatic_port_release(self):
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "connections.jsonl"
            with socket.socket() as reservation:
                reservation.bind(("127.0.0.1", 0))
                port = reservation.getsockname()[1]
            ready = threading.Event()
            urls, results, errors = [], [], []

            def output(*values, **kwargs):
                line = " ".join(str(value) for value in values)
                if line.startswith("URL: "):
                    urls.append(line[5:])
                    ready.set()

            def run():
                try:
                    results.append(check.main(["--bind", "127.0.0.1", "--port", str(port),
                                               "--duration-seconds", "2", "--log", str(log_path)]))
                except BaseException as exc:
                    errors.append(exc)
                    ready.set()

            started = time.monotonic()
            with mock.patch("builtins.print", side_effect=output):
                thread = threading.Thread(target=run, daemon=True)
                thread.start()
                try:
                    self.assertTrue(ready.wait(timeout=3))
                    self.assertEqual(errors, [])
                    self.assertEqual(len(urls), 1)
                    path = urlsplit(urls[0]).path
                    self.assertGreaterEqual(len(path), 33)

                    def request(method, requested_path):
                        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
                        try:
                            connection.request(method, requested_path,
                                               headers={"User-Agent": "must-not-be-logged"})
                            response = connection.getresponse()
                            return response.status, dict(response.getheaders()), response.read()
                        finally:
                            connection.close()

                    status, headers, body = request("GET", path)
                    self.assertEqual(status, 200)
                    self.assertEqual(body, check.PAGE)
                    self.assertEqual(headers["Cache-Control"], "no-store")
                    self.assertNotIn("Server", headers)
                    for wrong_path in ("/", "/files/config.json", path + "?unexpected=1"):
                        with self.subTest(path=wrong_path):
                            status, _, body = request("GET", wrong_path)
                            self.assertEqual((status, body), (404, b""))
                    for method in ("POST", "HEAD", "OPTIONS", "BREW"):
                        with self.subTest(method=method):
                            status, headers, body = request(method, path)
                            self.assertEqual((status, body), (405, b""))
                            self.assertEqual(headers["Allow"], "GET")
                finally:
                    thread.join(timeout=4)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(results, [0])
            self.assertLess(time.monotonic() - started, 4)
            records = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(records), 1)
            self.assertEqual(set(records[0]), {"source_ip", "time_utc"})
            self.assertEqual(records[0]["source_ip"], "127.0.0.1")
            self.assertIsNotNone(datetime.fromisoformat(records[0]["time_utc"]).tzinfo)
            self.assertNotIn(path, log_path.read_text(encoding="utf-8"))
            with check.ProbeServer(("127.0.0.1", port), check.ProbeHandler):
                pass

    def test_existing_port_is_rejected_without_disturbing_listener(self):
        with tempfile.TemporaryDirectory() as directory, socket.socket() as listener:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            listener.settimeout(2)
            address, port = listener.getsockname()
            log_path = Path(directory) / "connections.jsonl"
            with mock.patch("builtins.print"):
                result = check.main(["--bind", address, "--port", str(port),
                                     "--duration-seconds", "1", "--log", str(log_path)])
            self.assertEqual(result, 1)
            self.assertFalse(log_path.exists())
            with socket.create_connection((address, port), timeout=2):
                connection, _ = listener.accept()
                connection.close()

    def test_existing_log_is_not_overwritten_and_listener_is_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "existing.jsonl"
            log_path.write_text("existing record\n", encoding="utf-8")
            with socket.socket() as reservation:
                reservation.bind(("127.0.0.1", 0))
                port = reservation.getsockname()[1]
            with mock.patch("builtins.print"):
                result = check.main(["--bind", "127.0.0.1", "--port", str(port),
                                     "--duration-seconds", "1", "--log", str(log_path)])
            self.assertEqual(result, 1)
            self.assertEqual(log_path.read_text(encoding="utf-8"), "existing record\n")
            with check.ProbeServer(("127.0.0.1", port), check.ProbeHandler):
                pass


if __name__ == "__main__":
    unittest.main()
