"""Launcher orchestration checks; real renderer evidence is in the runtime probe."""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools import matahari_face_mesh_check as launcher


class FaceMeshCheckLauncherTests(unittest.TestCase):
    def test_stop_request_write_failure_starts_deadline_and_keeps_owner(self):
        process, job = mock.Mock(), mock.Mock()
        state = {'process': process, 'job': job, 'session': Path('unused-verification-session'),
                 'stopping': None, 'stop_request_error': None}
        with mock.patch.object(launcher.time, 'monotonic', return_value=42.0), \
                mock.patch.object(Path, 'touch', side_effect=PermissionError('request denied')):
            error = launcher.begin_gui_stop(state)
        self.assertIn('request denied', error)
        self.assertEqual(state['stopping'], 42.0)
        self.assertIs(state['process'], process)
        self.assertIs(state['job'], job)

    def test_forced_stop_log_failure_still_stops_owned_worker_and_retries(self):
        process, job, output = mock.Mock(), mock.Mock(), mock.Mock()
        state = {'process': process, 'job': job, 'output': output,
                 'session': Path('unused-verification-session'), 'forced_stop_logged': False,
                 'stop_log_error': None}
        with mock.patch.object(launcher, 'write_json', side_effect=OSError('disk full')) as write, \
                mock.patch.object(launcher, 'finish_owned_child', side_effect=[(False, 'retry'), (True, None)]) as finish:
            self.assertEqual(launcher.finish_gui_worker(state, forced=True), (False, 'retry'))
            self.assertIs(state['process'], process)
            self.assertIs(state['job'], job)
            self.assertIs(state['output'], output)
            self.assertEqual(launcher.finish_gui_worker(state, forced=True), (True, None))
        self.assertEqual(write.call_count, 1)
        self.assertEqual(finish.call_count, 2)
        finish.assert_called_with(process, output, 'face-check worker', 'verification_worker_end')
        self.assertTrue(state['forced_stop_logged'])
        self.assertIn('disk full', state['stop_log_error'])

    def test_owned_job_close_failure_retains_handle_and_log_for_retry(self):
        process = mock.Mock(pid=123, poll=mock.Mock(return_value=0))
        job = mock.Mock(is_alive=mock.Mock(return_value=False), wait=mock.Mock(return_value=True))
        job.close.side_effect = [OSError('close failed'), None]
        process._scene_job = job
        output = mock.Mock()
        closed, error = launcher.finish_owned_child(process, output, 'verification', 'test_cleanup')
        self.assertFalse(closed)
        self.assertIn('close failed', error)
        self.assertIs(process._scene_job, job)
        output.close.assert_not_called()
        closed, error = launcher.finish_owned_child(process, output, 'verification', 'test_cleanup')
        self.assertTrue(closed)
        self.assertIsNone(error)
        self.assertEqual(job.close.call_count, 2)
        output.close.assert_called_once()

    def test_unconfirmed_process_stop_never_closes_log(self):
        import manager
        process, output = mock.Mock(), mock.Mock()
        with mock.patch.object(manager.SceneManager, '_kill_process', return_value=False) as stop:
            closed, error = launcher.finish_owned_child(process, output, 'verification', 'test_cleanup')
        self.assertFalse(closed)
        self.assertTrue(error)
        stop.assert_called_once_with(process, 'verification', reason='test_cleanup')
        output.close.assert_not_called()

    def test_log_close_failure_is_retried_after_owned_stop(self):
        import manager
        process, output = mock.Mock(), mock.Mock()
        output.close.side_effect = [OSError('log close failed'), None]
        with mock.patch.object(manager.SceneManager, '_kill_process', return_value=True):
            self.assertFalse(launcher.finish_owned_child(process, output, 'verification', 'test_cleanup')[0])
            self.assertTrue(launcher.finish_owned_child(process, output, 'verification', 'test_cleanup')[0])
        self.assertEqual(output.close.call_count, 2)

    def test_poll_reschedules_after_cleanup_exception(self):
        window = mock.Mock(winfo_exists=mock.Mock(return_value=True))
        callback, error_handler = mock.Mock(), mock.Mock()
        failure = OSError('cleanup failed')
        launcher.poll_with_retry(window, callback, mock.Mock(side_effect=failure), error_handler)
        error_handler.assert_called_once_with(failure)
        window.after.assert_called_once_with(250, callback)

    def test_poll_reschedules_even_if_error_reporting_raises(self):
        window = mock.Mock(winfo_exists=mock.Mock(return_value=True))
        callback = mock.Mock()
        with self.assertRaisesRegex(RuntimeError, 'report failed'):
            launcher.poll_with_retry(window, callback, mock.Mock(side_effect=OSError('cleanup failed')),
                                     mock.Mock(side_effect=RuntimeError('report failed')))
        window.after.assert_called_once_with(250, callback)

    def run_session(self, *, scene_code=0, relay_start_error=None,
                    manager_cleanup=True, logs_closed=True, camera_activity=None):
        import manager
        import runtime_diagnostics
        import shared_camera
        import stage_display

        instances = {}

        class Relay:
            def __init__(self, *args, **kwargs):
                self.width, self.height, self.fps = 960, 540, 30
                self.frame_id = 1
                self.thread = mock.Mock(is_alive=mock.Mock(return_value=True))
                self.last_error = None
                self.close = mock.Mock(return_value=True)
                instances['relay'] = self

            def start(self):
                if relay_start_error:
                    raise relay_start_error
                return self

            def export_env(self):
                return {'HARUKAZE_SHARED_CAMERA_REQUIRED': '1', 'HARUKAZE_CAMERA_SHM': 'isolated-input'}

        class Scene:
            def __init__(self, **kwargs):
                self.arguments = kwargs
                self.completed_promotions = 0
                self.fatal_error = self.last_switch_error = None
                self.running_process = mock.Mock(poll=mock.Mock(return_value=scene_code))
                self.cleanup = mock.Mock(return_value=manager_cleanup)
                self.ticks = 0
                instances['scene'] = self

            def request_scene(self, action):
                self.action = action
                return True

            def tick(self):
                self.completed_promotions = 1
                self.ticks += 1

            def is_scene_running(self):
                return False  # A normal close or crash immediately after promotion.

        diagnostics = mock.Mock()
        diagnostics.close.return_value = logs_closed
        instances['diagnostics'] = diagnostics
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as scope:
            directory = Path(temporary)
            settings = {'mode': 'camera' if camera_activity is not None else 'synthetic',
                        'monitor': {'name': r'\\.\DISPLAY1', 'x': 0, 'y': 0,
                                    'width': 1920, 'height': 1080, 'is_primary': True},
                        'duration': 0, 'camera_index': 0, 'camera_name': 'ACER HD User Facing'}
            (directory / 'settings.json').write_text(json.dumps(settings), encoding='utf-8')
            scope.enter_context(mock.patch.object(launcher, 'code_version', return_value={'test': True}))
            scope.enter_context(mock.patch.object(stage_display, 'configure_audience_dpi'))
            scope.enter_context(mock.patch.object(shared_camera, 'SharedCameraRelay', Relay))
            scope.enter_context(mock.patch.object(shared_camera, 'SESSION_INFO_PATH', 'unchanged-session-path'))
            scope.enter_context(mock.patch.object(manager, 'SceneManager', Scene))
            scope.enter_context(mock.patch.object(manager, 'CONFIG', dict(manager.CONFIG)))
            scope.enter_context(mock.patch.object(runtime_diagnostics, 'RuntimeDiagnostics', return_value=diagnostics))
            scope.enter_context(mock.patch.object(launcher, 'camera_activity', return_value=camera_activity))
            # Guard both enumeration and the physical capture boundary in synthetic mode.
            enumerator = scope.enter_context(mock.patch.object(shared_camera, 'enumerate_camera_devices', side_effect=AssertionError('Unexpected enumeration')))
            code = launcher.run_session(directory)
            result = json.loads((directory / 'result.json').read_text(encoding='utf-8'))
            config = json.loads((directory / 'isolated-config.json').read_text(encoding='utf-8'))
            enumerator.assert_not_called()
        return code, result, config, instances

    def test_normal_close_returns_success_through_manager_and_existing_entrypoint(self):
        code, result, config, owned = self.run_session()
        self.assertEqual(code, 0)
        self.assertEqual(result['exit_reason'], 'scene_closed')
        self.assertTrue(result['cleanup_ok'])
        scene = owned['scene']
        self.assertEqual(scene.action, 'next')
        self.assertEqual(scene.arguments['scenes'], [str(launcher.ROOT / 'face_morph_acer.py')])
        self.assertEqual(scene.arguments['camera_env']['MATAHARI_FACE_INPUT'], 'synthetic_landmarks')
        self.assertEqual(scene.arguments['camera_env']['HARUKAZE_CAMERA_SHM'], 'isolated-input')
        self.assertFalse(config['TRANSITION_ENABLED'])
        self.assertFalse(config['CLAP_MONITOR_ENABLED'])
        owned['scene'].cleanup.assert_called_once()
        owned['relay'].close.assert_called_once()
        owned['diagnostics'].close.assert_called_once()

    def test_abnormal_child_exit_is_failure_with_owned_resources_closed(self):
        code, result, _, owned = self.run_session(scene_code=7)
        self.assertEqual(code, 1)
        self.assertIn('code=7', result['error'])
        self.assertTrue(result['cleanup_ok'])
        owned['scene'].cleanup.assert_called_once()
        owned['relay'].close.assert_called_once()

    def test_failed_relay_start_still_closes_partial_owner(self):
        code, result, _, owned = self.run_session(relay_start_error=RuntimeError('first frame unavailable'))
        self.assertEqual(code, 1)
        self.assertIn('CAMERA_FIRST_FRAME_FAILED', result['error'])
        self.assertNotIn('scene', owned)
        owned['relay'].close.assert_called_once()
        owned['diagnostics'].close.assert_called_once()

    def test_failed_manager_cleanup_cannot_report_success(self):
        code, result, _, owned = self.run_session(manager_cleanup=False)
        self.assertEqual(code, 1)
        self.assertFalse(result['cleanup_ok'])
        owned['relay'].close.assert_called_once()

    def test_failed_log_close_is_nonzero(self):
        code, result, _, _ = self.run_session(logs_closed=False)
        self.assertEqual(code, 1)
        self.assertFalse(result['logs_closed'])

    def test_reported_camera_use_stops_before_camera_owner_allocation(self):
        code, result, _, owned = self.run_session(camera_activity={'apps': ['other-app.exe']})
        self.assertEqual(code, 1)
        self.assertIn('CAMERA_IN_USE', result['error'])
        self.assertNotIn('relay', owned)
        self.assertNotIn('scene', owned)

    def test_clean_environment_removes_prior_stage_and_shared_input_settings(self):
        with mock.patch.dict(os.environ, {'KIDZDISCO_DISPLAY_TARGET': 'audience',
                                        'HARUKAZE_CAMERA_SHM': 'production',
                                        'MATAHARI_FACE_INPUT': 'synthetic_landmarks',
                                        'SDL_VIDEODRIVER': 'dummy', 'PATH': 'keep-path'}):
            clean = launcher.clean_env()
        self.assertNotIn('KIDZDISCO_DISPLAY_TARGET', clean)
        self.assertNotIn('HARUKAZE_CAMERA_SHM', clean)
        self.assertNotIn('MATAHARI_FACE_INPUT', clean)
        self.assertNotIn('SDL_VIDEODRIVER', clean)
        self.assertEqual(clean['PATH'], 'keep-path')


if __name__ == '__main__':
    unittest.main()
