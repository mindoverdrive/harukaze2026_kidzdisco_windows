import socket
import unittest
from unittest import mock

from scene_control import JsonChannel, SceneControlError
from transition_manager import TransitionManager


class TransitionManagerTests(unittest.TestCase):
    def setUp(self):
        self.process = mock.Mock(pid=1234)
        self.process.poll.return_value = None
        self.spawn = mock.Mock(return_value=self.process)
        self.stop = mock.Mock(return_value=True)
        self.events = []
        self.manager = TransitionManager(self.spawn, self.stop, (-1920, 0, 1920, 1080),
                                         on_event=self.events.append)
        self.addCleanup(self.manager.close)

    def connect(self):
        self.assertTrue(self.manager.begin())
        argv = self.spawn.call_args.args[0]
        port = int(argv[argv.index("--control-port") + 1])
        self.peer = JsonChannel(socket.create_connection(("127.0.0.1", port), timeout=1))
        self.addCleanup(self.peer.close)
        self.send("READY", pid=self.process.pid)
        messages = self.peer.receive()
        self.assertEqual(messages[-1]["command"], "COVER")

    def send(self, event, **fields):
        payload = {"event": event, "token": self.manager.token, "cycle": self.manager.cycle, **fields}
        self.peer.send(payload)
        self.manager.poll()

    def uncover(self):
        self.send("COVERED")
        self.assertTrue(self.manager.reveal())
        self.peer.receive()
        self.send("REVEALED")

    def test_lazy_single_process_and_acknowledged_full_cycle(self):
        self.spawn.assert_not_called()
        self.assertFalse(self.manager.busy)
        self.connect()
        self.assertFalse(self.manager.covered)
        self.assertTrue(self.manager.busy)
        self.assertFalse(self.manager.begin())
        self.assertFalse(self.manager.reveal())
        self.send("COVERED")
        self.assertTrue(self.manager.covered)
        with mock.patch("transition_manager.time.monotonic", return_value=10**12):
            self.manager.poll()
        self.assertIsNone(self.manager.error)
        self.assertTrue(self.manager.covered)
        self.assertTrue(self.manager.reveal())
        self.assertTrue(self.manager.covered)
        self.assertTrue(self.manager.busy)
        self.assertFalse(self.manager.reveal())
        self.peer.receive()
        self.send("REVEALED")
        self.assertFalse(self.manager.busy)
        self.assertFalse(self.manager.covered)
        self.assertIs(self.manager.process, self.process)
        self.assertTrue(self.manager.begin())
        self.assertEqual(self.manager.cycle, 2)
        self.spawn.assert_called_once()

    def test_actions_only_when_stable_and_current_cycle(self):
        self.connect()
        self.send("ACTION", action="next")
        self.assertIsNone(self.manager.consume_action())
        self.uncover()
        self.send("ACTION", action="next")
        self.send("ACTION", action="back")
        self.assertEqual(self.manager.consume_action(), "next")
        self.assertIsNone(self.manager.consume_action())
        self.send("ACTION", action="back")
        self.assertTrue(self.manager.begin())
        self.assertIsNone(self.manager.consume_action())
        self.peer.receive()
        self.uncover()
        self.send("ACTION", action="next", cycle=1)
        self.assertIsNone(self.manager.consume_action())
        self.send("ACTION", action="back")
        self.assertEqual(self.manager.consume_action(), "back")

    def test_cover_and_reveal_timeouts_do_not_claim_an_uncovered_scene(self):
        self.connect()
        self.send("COVERED")
        self.assertTrue(self.manager.reveal())
        self.manager._deadline = 0
        self.manager.poll()
        self.assertIn("revealing timeout", self.manager.error)
        self.assertTrue(self.manager.covered)
        self.assertTrue(self.manager.busy)
        self.assertFalse(self.manager.reveal())
        self.assertFalse(self.manager.begin())
        self.stop.assert_not_called()

    def test_missing_ready_has_a_deadline(self):
        self.assertTrue(self.manager.begin())
        self.manager._deadline = 0
        self.manager.poll()
        self.assertIn("starting timeout", self.manager.error)
        self.assertFalse(self.manager.covered)

    def test_missing_covered_ack_has_a_deadline(self):
        self.connect()
        self.manager._deadline = 0
        self.manager.poll()
        self.assertIn("covering timeout", self.manager.error)
        self.assertFalse(self.manager.covered)

    def test_wrong_identity_fails_closed_and_cannot_produce_actions(self):
        self.connect()
        self.send("COVERED")
        self.send("REVEALED", token="wrong")
        self.assertIn("token mismatch", self.manager.error)
        self.assertTrue(self.manager.covered)
        self.assertIsNone(self.manager.consume_action())
        self.assertEqual(self.peer.receive()[-1]["command"], "FAIL_CLOSED")

    def test_unexpected_exit_and_disconnect_are_observed(self):
        self.connect()
        self.send("COVERED")
        self.process.poll.return_value = 1
        self.manager.poll()
        self.assertIn("exited", self.manager.error)
        self.assertTrue(self.manager.covered)

    def test_emergency_cover_is_acknowledged_even_after_a_timeout(self):
        self.connect()
        self.manager._deadline = 0
        self.manager.poll()
        self.send("COVERED", emergency=True)
        self.assertTrue(self.manager.covered)
        self.assertTrue(self.manager.busy)
        self.assertIsNotNone(self.manager.error)

    def test_failed_stop_retains_ownership_for_retry(self):
        self.connect()
        self.stop.return_value = False
        self.assertFalse(self.manager.close())
        self.assertIs(self.manager.process, self.process)
        self.stop.return_value = True
        self.assertTrue(self.manager.close())
        self.assertIsNone(self.manager.process)

    def test_diagnostic_failure_does_not_interrupt_cleanup(self):
        self.manager.on_event = mock.Mock(side_effect=RuntimeError("diagnostic"))
        self.connect()
        self.assertTrue(self.manager.close())
        self.stop.assert_called_with(self.process, "transition_overlay", reason="overlay_shutdown")

    def test_ready_adopts_a_verified_venv_child_pid(self):
        self.assertTrue(self.manager.begin())
        self.manager._channel = mock.Mock()
        job = mock.Mock()
        job.adopt_scene_pid.return_value = True
        with mock.patch("transition_manager.get_scene_job", return_value=job):
            self.manager._receive({"event": "READY", "token": self.manager.token, "pid": 5678})
        job.adopt_scene_pid.assert_called_once_with(5678)
        self.assertEqual(self.manager.child_pid, 5678)
        self.assertEqual(self.process._scene_pid, 5678)
        self.assertFalse(self.manager.covered)

    def test_ready_rejects_an_unowned_or_noninteger_pid(self):
        self.assertTrue(self.manager.begin())
        self.manager._channel = mock.Mock()
        job = mock.Mock()
        job.adopt_scene_pid.return_value = False
        for pid in (5678, True, 0, "1234"):
            with self.subTest(pid=pid), mock.patch("transition_manager.get_scene_job", return_value=job):
                with self.assertRaises(SceneControlError):
                    self.manager._receive({"event": "READY", "token": self.manager.token, "pid": pid})


if __name__ == "__main__":
    unittest.main()
