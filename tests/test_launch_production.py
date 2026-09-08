import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts import launch_production as launcher


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'test_reports').mkdir()
        self.kernel = mock.MagicMock()
        self.kernel.CreateMutexW.return_value = 123
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        for name, value in [('ROOT', self.root), ('check', mock.Mock())]:
            self.stack.enter_context(mock.patch.object(launcher, name, value))
        self.stack.enter_context(mock.patch.object(launcher.sys, 'argv', ['launcher']))
        self.stack.enter_context(mock.patch.object(launcher.ctypes, 'WinDLL', return_value=self.kernel, create=True))
        self.last_error = self.stack.enter_context(mock.patch.object(launcher.ctypes, 'get_last_error', return_value=0, create=True))
        self.socket = self.stack.enter_context(mock.patch.object(launcher.socket, 'socket'))
        self.socket.return_value.__enter__.return_value.connect_ex.return_value = 1
        self.spawn = self.stack.enter_context(mock.patch.object(launcher.subprocess, 'Popen'))
        self.spawn.return_value.poll.return_value = None
        self.browser = self.stack.enter_context(mock.patch.object(launcher.webbrowser, 'open'))

    def test_check_only_does_not_start_or_open(self):
        with mock.patch.object(launcher.sys, 'argv', ['launcher', '--check-only']):
            launcher.main()
        self.spawn.assert_not_called()
        self.browser.assert_not_called()

    def test_existing_panel_is_reused(self):
        self.socket.return_value.__enter__.return_value.connect_ex.return_value = 0
        with mock.patch.object(launcher, 'find_panel', return_value='http://127.0.0.1:8766/#token=test'):
            launcher.main()
        self.spawn.assert_not_called()
        self.browser.assert_called_once()
        self.kernel.CloseHandle.assert_called_once_with(123)

    def test_unknown_port_owner_is_left_untouched(self):
        self.socket.return_value.__enter__.return_value.connect_ex.return_value = 0
        with mock.patch.object(launcher, 'find_panel', return_value=None):
            with self.assertRaisesRegex(RuntimeError, 'already in use'):
                launcher.main()
        self.spawn.assert_not_called()
        self.browser.assert_not_called()

    def test_concurrent_launch_does_not_spawn(self):
        self.last_error.return_value = 183
        launcher.main()
        self.spawn.assert_not_called()
        self.kernel.CloseHandle.assert_called_once_with(123)

    def test_new_launch_uses_existing_entry_and_waits_ready(self):
        with mock.patch.object(launcher, 'find_panel', return_value='http://127.0.0.1:8766/#token=test'), mock.patch.object(launcher, 'status', return_value={'scene': {'current':'scene', 'busy':False, 'covered':False}}):
            launcher.main()
        args, kwargs = self.spawn.call_args
        self.assertEqual(args[0], [launcher.sys.executable, '-u', str(self.root/'scripts/start_operator.py')])
        self.assertEqual(kwargs['creationflags'], launcher.subprocess.CREATE_NO_WINDOW)
        self.assertEqual(kwargs['cwd'], self.root)
        self.browser.assert_called_once()

    def test_early_exit_reports_log(self):
        self.spawn.return_value.poll.return_value = 1
        with self.assertRaisesRegex(RuntimeError, 'process exited'):
            launcher.main()
        self.kernel.CloseHandle.assert_called_once_with(123)

    def test_timeout_does_not_kill_existing_process(self):
        with mock.patch.object(launcher.time, 'monotonic', side_effect=[0, 91]):
            with self.assertRaisesRegex(RuntimeError, '90 seconds'):
                launcher.main()
        self.spawn.return_value.terminate.assert_not_called()
        self.spawn.return_value.kill.assert_not_called()

    def test_stale_token_skipped_for_live_token(self):
        paths = [self.root/'stale.log', self.root/'live.log']
        for path, token in zip(paths, ['stale', 'live']):
            path.write_text('http://127.0.0.1:8766/#token='+token)
        with mock.patch.object(launcher, 'status', side_effect=[OSError('unauthorized'), {'scene':{}}]):
            self.assertEqual(launcher.find_panel(paths), 'http://127.0.0.1:8766/#token=live')


if __name__ == '__main__':
    unittest.main()
