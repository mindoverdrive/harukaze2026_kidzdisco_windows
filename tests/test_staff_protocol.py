"""Real localhost messages, synthetic owned process; no camera/GPU required."""
import json
import socket
import unittest
from unittest import mock
from scene_control import SceneLaunchControl, SceneControlError


class StaffProtocolTests(unittest.TestCase):
    def setUp(self):
        self.control = SceneLaunchControl(ready_timeout=1, ack_timeout=1, frame_timeout=2)
        self.addCleanup(self.control.close)
        self.peer = socket.create_connection(('127.0.0.1', self.control.port))
        self.addCleanup(self.peer.close)
        self.proc = mock.Mock(pid=123, returncode=None)
        self.proc.poll.return_value = None

    def send(self, event, **values):
        data = {'event': event, 'pid': 123, 'launch_id': self.control.launch_id, **values}
        self.peer.sendall(json.dumps(data).encode()+b'\n')

    def ready(self):
        self.send('READY')
        self.assertEqual(self.control.poll(self.proc), 'READY')

    def test_ready_delivered_after_deadline_is_rejected(self):
        self.control.created_at -= 3
        self.send('READY')
        with self.assertRaisesRegex(SceneControlError, 'READY timeout'):
            self.control.poll(self.proc)

    def test_ack_delivered_after_deadline_is_rejected(self):
        self.ready()
        self.control.start()
        self.control.started_at -= 1.5
        self.send('START_ACK')
        with self.assertRaisesRegex(SceneControlError, 'START_ACK timeout'):
            self.control.poll(self.proc)

    def test_missing_ack_expires(self):
        self.ready()
        self.control.start()
        self.control.started_at -= 1.5
        with self.assertRaisesRegex(SceneControlError, 'START_ACK timeout'):
            self.control.poll(self.proc)

    def test_missing_frame_expires_after_ack(self):
        self.ready()
        self.control.start()
        self.send('START_ACK')
        self.control.poll(self.proc)
        self.control.started_at -= 3
        with self.assertRaisesRegex(SceneControlError, 'FIRST_FRAME timeout'):
            self.control.poll(self.proc)

    def test_duplicate_ready_fails_closed(self):
        self.ready()
        self.send('READY')
        with self.assertRaises(SceneControlError):
            self.control.poll(self.proc)
        self.assertIsNone(self.control.first_frame)

    def test_first_frame_without_ack_is_rejected(self):
        self.ready()
        self.control.start()
        self.send('FIRST_FRAME', frame_id=1)
        with self.assertRaises(SceneControlError):
            self.control.poll(self.proc)

    def test_old_identity_or_changed_pid_never_promotes(self):
        self.ready()
        self.control.start()
        self.send('START_ACK', launch_id='old-launch')
        with self.assertRaises(SceneControlError):
            self.control.poll(self.proc)

    def test_ordered_combined_ack_and_frame_is_accepted(self):
        self.ready()
        self.control.start()
        self.send('START_ACK')
        self.send('FIRST_FRAME', frame_id=4, shm_name='shared')
        self.assertEqual(self.control.poll(self.proc), 'FIRST_FRAME')

    def test_duplicate_first_frame_never_creates_second_promotion(self):
        self.ready()
        self.control.start()
        self.send('START_ACK')
        self.send('FIRST_FRAME', frame_id=4)
        self.send('FIRST_FRAME', frame_id=4)
        with self.assertRaises(SceneControlError):
            self.control.poll(self.proc)
        self.assertEqual(self.control.state, 'FAILED')

    def test_late_first_frame_is_rejected(self):
        self.ready()
        self.control.start()
        self.send('START_ACK')
        self.control.poll(self.proc)
        self.control.started_at -= 3
        self.send('FIRST_FRAME', frame_id=4)
        with self.assertRaisesRegex(SceneControlError, 'FIRST_FRAME timeout'):
            self.control.poll(self.proc)

    def test_changed_pid_is_rejected(self):
        self.ready()
        self.control.start()
        self.send('START_ACK', pid=124)
        with self.assertRaisesRegex(SceneControlError, 'identity changed'):
            self.control.poll(self.proc)


if __name__ == '__main__':
    unittest.main()
