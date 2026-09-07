import itertools
import os
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

import transition_overlay as overlay


class OverlayHarness:
    """Run the real overlay loop without a native window, detector or socket."""

    def __init__(self, *, batches=(), failed_send=None):
        self.batches = iter(batches)
        self.failed_send = failed_send
        self.disconnected = False
        self.disconnect_flip = None
        self.flips = []
        self.last_fill = None
        self.ticks = 0
        self.sent = []
        self.channel = mock.Mock(eof=False)
        self.channel.receive.side_effect = self.receive
        self.channel.send.side_effect = self.send
        self.screen = mock.Mock()
        self.screen.get_size.return_value = (100, 100)
        self.screen.get_rect.return_value = (0, 0, 100, 100)
        self.screen.fill.side_effect = self.fill
        self.clock = mock.Mock()
        self.clock.tick.side_effect = self.tick
        self.pygame = SimpleNamespace(
            NOFRAME=1, HIDDEN=2, QUIT=3, init=mock.Mock(), quit=mock.Mock(),
            event=SimpleNamespace(get=mock.Mock(return_value=[])),
            draw=mock.Mock(),
            time=SimpleNamespace(Clock=mock.Mock(return_value=self.clock)),
            display=SimpleNamespace(
                set_mode=mock.Mock(return_value=self.screen), set_caption=mock.Mock(),
                flip=mock.Mock(side_effect=self.flip),
            ),
        )
        self.worker = mock.Mock()
        self.worker.snapshot.return_value = ((None, ()), None)
        self.worker.camera_snapshot.return_value = (None, None)

    def disconnect(self):
        self.disconnected = True
        self.disconnect_flip = len(self.flips)

    def receive(self):
        if self.disconnected:
            raise AssertionError("A disconnected control channel must not be polled again")
        batch = next(self.batches, [{"command": "CLOSE", "token": "token"}])
        if batch == "eof":
            self.disconnect()
            self.channel.eof = True
            return []
        if isinstance(batch, OSError):
            self.disconnect()
            raise batch
        if batch == "close_with_eof":
            self.channel.eof = True
            return [{"command": "CLOSE", "token": "token"}]
        return batch

    def send(self, message):
        if self.disconnected:
            raise AssertionError("A disconnected control channel must not be sent to again")
        self.sent.append(message["event"])
        if message["event"] == self.failed_send:
            self.disconnect()
            raise BrokenPipeError("injected send disconnect")

    def fill(self, color):
        self.last_fill = color

    def flip(self):
        self.flips.append(self.last_fill)

    def tick(self, _fps):
        self.ticks += 1
        if self.disconnected:
            # Resource cleanup must wait for the owning Manager to stop this process.
            self.pygame.quit.assert_not_called()
            self.worker.close.assert_not_called()
            self.channel.close.assert_not_called()
            if len(self.flips) - self.disconnect_flip >= 3:
                raise KeyboardInterrupt("owned Manager stop")
        if self.ticks >= 12:
            raise AssertionError("Overlay did not reach the expected bounded test stop")

    def run(self):
        stamps = itertools.count(0.0, 2.0)
        with (
            mock.patch.dict(sys.modules, {"pygame": self.pygame}),
            mock.patch.dict(os.environ),
            mock.patch("stage_display.configure_audience_dpi"),
            mock.patch.object(overlay, "configure_overlay_window"),
            mock.patch.object(overlay, "DetectionWorker", return_value=self.worker),
            mock.patch.object(overlay, "NavigationStyle"),
            mock.patch("transition_logo.CurtainLogo"),
            mock.patch("transition_particles.ParticleCurtain"),
            mock.patch.object(overlay, "OverlayOpacity"),
            mock.patch.object(overlay.socket, "create_connection"),
            mock.patch.object(overlay, "JsonChannel", return_value=self.channel),
            mock.patch.object(overlay.signal, "signal"),
            mock.patch.object(overlay.time, "monotonic", side_effect=lambda: next(stamps)),
        ):
            overlay.run_overlay(1234, "token", (0, 0, 100, 100))


def command(name):
    return [{"command": name, "cycle": 1, "token": "token"}]


class TransitionDisconnectTests(unittest.TestCase):
    def assert_covered_until_owned_stop(self, harness):
        with self.assertRaisesRegex(KeyboardInterrupt, "owned Manager stop"):
            harness.run()
        frames = harness.flips[harness.disconnect_flip:]
        self.assertGreaterEqual(len(frames), 3)
        self.assertEqual(set(frames), {overlay.COVER_COLOR})
        harness.worker.close.assert_called_once()
        harness.pygame.quit.assert_called_once()
        harness.channel.close.assert_called_once()

    def test_eof_keeps_cover_in_idle_covered_and_revealing_states(self):
        for prefix in ([], [command("COVER"), []], [command("COVER"), [], command("REVEAL")]):
            with self.subTest(prefix=prefix):
                harness = OverlayHarness(batches=[*prefix, "eof"])
                self.assert_covered_until_owned_stop(harness)
                self.assertEqual(harness.channel.receive.call_count, len(prefix) + 1)

    def test_receive_error_keeps_cover_without_more_network_io(self):
        harness = OverlayHarness(batches=[command("COVER"), [], ConnectionResetError("injected reset")])
        self.assert_covered_until_owned_stop(harness)
        self.assertEqual(harness.sent, ["READY", "COVERED"])
        self.assertEqual(harness.channel.receive.call_count, 3)

    def test_ready_send_failure_still_presents_cover_until_owned_stop(self):
        harness = OverlayHarness(failed_send="READY")
        self.assert_covered_until_owned_stop(harness)
        self.assertEqual(harness.sent, ["READY"])
        harness.channel.receive.assert_not_called()

    def test_covered_ack_send_failure_keeps_cover_without_retrying(self):
        harness = OverlayHarness(batches=[command("COVER"), []], failed_send="COVERED")
        self.assert_covered_until_owned_stop(harness)
        self.assertEqual(harness.sent, ["READY", "COVERED"])

    def test_revealed_ack_send_failure_immediately_restores_full_cover(self):
        harness = OverlayHarness(
            batches=[command("COVER"), [], command("REVEAL"), []], failed_send="REVEALED"
        )
        self.assert_covered_until_owned_stop(harness)
        self.assertEqual(harness.sent, ["READY", "COVERED", "REVEALED"])

    def test_authenticated_close_keeps_normal_cleanup_including_final_eof(self):
        for close in (command("CLOSE"), "close_with_eof"):
            with self.subTest(close=close):
                harness = OverlayHarness(batches=[command("COVER"), [], close])
                harness.run()
                self.assertFalse(harness.disconnected)
                harness.worker.close.assert_called_once()
                harness.pygame.quit.assert_called_once()
                harness.channel.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
