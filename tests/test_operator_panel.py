import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.modules.setdefault("cv2", mock.MagicMock())
import cv2
from camera_controls import CameraControlMailbox, save_controls, validate_controls
from operator_panel import OperatorPanel


class FakeCapture:
    def __init__(self):
        self.values = {15: -5, 27: 100}
        self.writer_threads = []
        self.ignore_zoom = None

    def get(self, prop):
        return self.values.get(prop, -1)

    def set(self, prop, value):
        self.writer_threads.append(threading.get_ident())
        if prop != 27 or value != self.ignore_zoom:
            self.values[prop] = value
        return True


class OperatorPanelTests(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.multiple(cv2, CAP_PROP_EXPOSURE=15, CAP_PROP_ZOOM=27)
        patch.start()
        self.addCleanup(patch.stop)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.config_path = Path(self.directory.name) / "kids.json"
        self.original = {"PRODUCTION_SCENES": ["finger_colorfull_dots_acer.py"], "keep": {"nested": True}}
        self.config_path.write_text(json.dumps(self.original), encoding="utf-8")
        self.mailbox = CameraControlMailbox()
        self.cap = FakeCapture()

    def test_submit_never_calls_camera_and_capture_owner_applies_it(self):
        sequence = self.mailbox.submit({"exposure": -6, "zoom": 120})
        self.assertEqual(self.cap.writer_threads, [])
        with self.assertRaises(RuntimeError):
            self.mailbox.submit({"zoom": 130})
        worker = threading.Thread(target=self.mailbox.apply_pending, args=(self.cap,))
        worker.start()
        worker.join(timeout=1)
        state = self.mailbox.snapshot()
        self.assertEqual(state["status"], "applied")
        self.assertEqual(state["sequence"], sequence)
        self.assertEqual(state["actual"], {"exposure": -6.0, "zoom": 120.0})
        self.assertEqual(set(self.cap.writer_threads), {worker.ident})
        self.mailbox.close()
        with self.assertRaises(RuntimeError):
            self.mailbox.submit({"zoom": 100})

    def test_rejected_readback_rolls_back_values_and_cannot_be_saved(self):
        self.cap.ignore_zoom = 120
        sequence = self.mailbox.submit({"exposure": -6, "zoom": 120})
        self.mailbox.apply_pending(self.cap)
        self.assertEqual(self.cap.values, {15: -5, 27: 100})
        self.assertEqual(self.mailbox.snapshot()["status"], "failed")
        with self.assertRaises(RuntimeError):
            save_controls(self.config_path, self.mailbox, sequence)
        self.assertEqual(json.loads(self.config_path.read_text()), self.original)

    def test_save_requires_latest_confirmed_values_and_preserves_other_settings(self):
        sequence = self.mailbox.submit({"exposure": -6})
        with self.assertRaises(RuntimeError):
            save_controls(self.config_path, self.mailbox, sequence)
        self.mailbox.apply_pending(self.cap)
        save_controls(self.config_path, self.mailbox, sequence)
        saved = json.loads(self.config_path.read_text())
        self.assertEqual(saved, {**self.original, "CAMERA_EXPOSURE": -6})
        self.mailbox.submit({"zoom": 120})
        with self.assertRaises(RuntimeError):
            save_controls(self.config_path, self.mailbox, sequence)
        self.assertEqual(list(self.config_path.parent.glob("*.tmp")), [])

    def test_save_rejects_sequence_replaced_during_file_preparation(self):
        sequence = self.mailbox.submit({"exposure": -6})
        self.mailbox.apply_pending(self.cap)
        write_text = Path.write_text

        def prepare_then_apply(path, *args, **kwargs):
            result = write_text(path, *args, **kwargs)
            if path.suffix == ".tmp":
                self.mailbox.submit({"exposure": -7})
                self.mailbox.apply_pending(self.cap)
            return result

        with mock.patch.object(Path, "write_text", prepare_then_apply):
            with self.assertRaises(RuntimeError):
                save_controls(self.config_path, self.mailbox, sequence)
        self.assertEqual(json.loads(self.config_path.read_text()), self.original)
        self.assertEqual(self.mailbox.snapshot()["actual"]["exposure"], -7)
        self.assertEqual(list(self.config_path.parent.glob("*.tmp")), [])

    def test_new_apply_and_save_cannot_be_overwritten_by_inflight_save(self):
        sequence = self.mailbox.submit({"exposure": -6})
        self.mailbox.apply_pending(self.cap)
        replacing = threading.Event()
        release_replace = threading.Event()
        new_started = threading.Event()
        new_finished = threading.Event()
        errors = []
        from camera_controls import os as controls_os
        replace = controls_os.replace

        def pause_old_replace(source, destination):
            if threading.current_thread().name == "old-save":
                replacing.set()
                if not release_replace.wait(timeout=3):
                    raise RuntimeError("test did not release the old save")
            return replace(source, destination)

        def old_save():
            try:
                save_controls(self.config_path, self.mailbox, sequence)
            except Exception as exc:
                errors.append(exc)

        def new_apply_and_save():
            new_started.set()
            try:
                newer = self.mailbox.submit({"exposure": -7})
                self.mailbox.apply_pending(self.cap)
                save_controls(self.config_path, self.mailbox, newer)
            except Exception as exc:
                errors.append(exc)
            finally:
                new_finished.set()

        older = threading.Thread(target=old_save, name="old-save")
        newer = threading.Thread(target=new_apply_and_save, name="new-save")
        with mock.patch.object(controls_os, "replace", pause_old_replace):
            older.start()
            try:
                self.assertTrue(replacing.wait(timeout=1))
                newer.start()
                self.assertTrue(new_started.wait(timeout=1))
                new_finished.wait(timeout=0.2)
            finally:
                release_replace.set()
                older.join(timeout=2)
                if newer.ident is not None:
                    newer.join(timeout=2)
        self.assertFalse(older.is_alive())
        self.assertFalse(newer.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(json.loads(self.config_path.read_text())["CAMERA_EXPOSURE"], -7)
        self.assertEqual(self.mailbox.snapshot()["actual"]["exposure"], -7)
        self.assertEqual(list(self.config_path.parent.glob("*.tmp")), [])

    def test_nan_rollback_readback_is_reported_as_unconfirmed(self):
        class RollbackNaNCapture(FakeCapture):
            rollback_started = False

            def set(self, prop, value):
                result = super().set(prop, value)
                if prop == 27 and value == 100:
                    self.rollback_started = True
                return result

            def get(self, prop):
                if prop == 27 and self.rollback_started:
                    return float("nan")
                return super().get(prop)

        cap = RollbackNaNCapture()
        cap.ignore_zoom = 120
        sequence = self.mailbox.submit({"exposure": -6, "zoom": 120})
        self.mailbox.apply_pending(cap)
        state = self.mailbox.snapshot()
        self.assertEqual(state["status"], "failed")
        self.assertIn("元の値の復元を確認できません: zoom", state["error"])
        self.assertIsNone(state["actual"]["zoom"])
        with self.assertRaises(RuntimeError):
            save_controls(self.config_path, self.mailbox, sequence)

    def test_bad_values_and_unrelated_config_keys_are_rejected(self):
        for values in ({}, [], {"scene": "unreviewed.py"}, {"exposure": True}, {"exposure": float("nan")},
                       {"exposure": -5.5}, {"exposure": -14}, {"zoom": 99}, {"zoom": 501}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                validate_controls(values)

    def panel(self):
        relay = SimpleNamespace(controls=self.mailbox, frame_id=5, last_error=None)
        with mock.patch("builtins.print"):
            panel = OperatorPanel(relay, self.config_path, port=0).start()
        self.addCleanup(panel.close)
        return panel

    def request(self, panel, path, data=None, authorized=True):
        headers = {"Content-Type": "application/json"}
        if authorized:
            headers["Authorization"] = "Bearer " + panel.token
        request = Request(f"http://127.0.0.1:{panel.port}{path}", headers=headers,
                          data=json.dumps(data).encode() if data is not None else None)
        try:
            with urlopen(request, timeout=2) as response:
                return response.status, json.loads(response.read())
        except HTTPError as exc:
            with exc:
                return exc.code, json.loads(exc.read())

    def test_real_http_auth_apply_confirm_save_and_action_queue(self):
        panel = self.panel()
        self.assertEqual(self.request(panel, "/api/status", authorized=False)[0], 401)
        self.assertEqual(self.request(panel, "/api/camera", {"zoom": 150}, authorized=False)[0], 401)
        self.assertEqual(self.cap.writer_threads, [])
        code, command = self.request(panel, "/api/camera", {"zoom": 150})
        self.assertEqual(code, 202)
        self.assertEqual(self.request(panel, "/api/save", command)[0], 409)
        self.mailbox.apply_pending(self.cap)
        self.assertEqual(self.request(panel, "/api/status")[1]["camera"]["actual"]["zoom"], 150)
        self.assertEqual(self.request(panel, "/api/save", command)[0], 200)
        self.assertEqual(json.loads(self.config_path.read_text())["CAMERA_ZOOM"], 150)
        self.assertEqual(self.request(panel, "/api/camera", {"file": "bad.py"})[0], 400)
        self.assertEqual(self.request(panel, "/api/save", {"sequence": True})[0], 400)
        self.assertEqual(self.request(panel, "/api/action", {"action": "next"})[0], 202)
        self.assertEqual(self.request(panel, "/api/action", {"action": "quit"})[0], 409)
        self.assertEqual(panel.consume_action(), "next")
        self.assertIsNone(panel.consume_action())
        self.assertTrue(panel.close())
        self.assertFalse(panel.thread.is_alive())

    def test_panel_requires_specific_local_network_or_loopback_address(self):
        for address in ("0.0.0.0", "8.8.8.8", "::", "not-an-ip"):
            with self.subTest(address=address), self.assertRaises(ValueError):
                OperatorPanel(None, self.config_path, host=address)


if __name__ == "__main__":
    unittest.main()
