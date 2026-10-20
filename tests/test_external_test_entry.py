"""External test launch policy; synthetic monitors, cameras and processes only."""
import contextlib
import importlib.util
import io
import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest import mock

from stage_display import external_test_config, DisplayConfigurationError

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def monitor(name, primary=False, x=0, y=0, width=1920, height=1080):
    return NS(name=name, is_primary=primary, x=x, y=y, width=width, height=height)


class ExternalDisplayTests(unittest.TestCase):
    def test_changed_names_negative_origin_and_resolution_are_observed(self):
        config = {'DISPLAY_NAME':'stale5','CONTROL_DISPLAY_NAME':'stale1','CAMERA_FPS':30}
        displays = [monitor('current9',True), monitor('current2',x=-3840,y=-200,width=3840,height=2160)]
        result = external_test_config(config,monitors=displays)
        self.assertEqual(result['DISPLAY_NAME'],'current2')
        self.assertEqual(result['CONTROL_DISPLAY_NAME'],'current9')
        self.assertEqual((result['DISPLAY_X'],result['DISPLAY_Y'],result['DISPLAY_WIDTH'],result['DISPLAY_HEIGHT']),(-3840,-200,3840,2160))
        self.assertEqual(config['DISPLAY_NAME'],'stale5')
        self.assertEqual(result['CAMERA_FPS'],30)
        self.assertEqual(result['DISPLAY_TARGET'],'audience')

    def test_single_screen_never_falls_back_to_operator(self):
        with self.assertRaises(DisplayConfigurationError):
            external_test_config({},monitors=[monitor('p',True)])

    def test_multiple_external_screens_require_explicit_choice(self):
        displays=[monitor('p',True),monitor('a',x=1920),monitor('b',x=3840)]
        with self.assertRaises(DisplayConfigurationError):
            external_test_config({},monitors=displays)
        self.assertEqual(external_test_config({},'B',displays)['DISPLAY_NAME'],'B')

    def test_primary_must_be_unique(self):
        for displays in ([monitor('p')],[monitor('p',True),monitor('q',True,x=1920)]):
            with self.subTest(displays=displays),self.assertRaises(DisplayConfigurationError):
                external_test_config({},monitors=displays)

    def test_invalid_or_ambiguous_geometry_never_accepted(self):
        for external in (monitor('a',x=0),monitor('a',x=1920,width=0),monitor('p',x=1920)):
            with self.subTest(external=external),self.assertRaises(DisplayConfigurationError):
                external_test_config({},monitors=[monitor('p',True),external])

    def test_explicit_primary_and_missing_screen_are_rejected(self):
        for name in ('p','missing'):
            with self.subTest(name=name),self.assertRaises(DisplayConfigurationError):
                external_test_config({},name,[monitor('p',True),monitor('a',x=1920)])


class ExternalLauncherTests(unittest.TestCase):
    def setUp(self):
        self.module=load('external_launcher_fixture',ROOT/'scripts/launch_production.py')

    def test_c922n_name_preflight_without_open_and_no_fixed_device_index(self):
        import stage_display
        import shared_camera
        config={'PRODUCTION_SCENES':[],'CAMERA_NAME_HINTS':['c922'],
                'CAMERA_EXCLUDE_HINTS':['virtual','integrated','user facing'],
                'CAMERA_OPENCV_INDEX':0,'CAMERA_REQUIRE_NAME_MATCH':True,
                'CAMERA_ALLOW_FALLBACK':False,'CAMERA_BACKEND':'dshow'}
        displays={'control':{'name':'p'},'audience':{'name':'a'}}
        for names, succeeds in ((['ACER HD User Facing','Logitech C922n'],True),
                                (['ACER HD User Facing'],False),([],False),
                                (['C922','C922n'],False),(['Virtual C922'],False)):
            with self.subTest(names=names),contextlib.ExitStack() as stack:
                stack.enter_context(mock.patch.object(stage_display,'configure_audience_dpi'))
                stack.enter_context(mock.patch.object(stage_display,'external_test_config',return_value=dict(config)))
                stack.enter_context(mock.patch.object(stage_display,'resolve_audience_displays',return_value=displays))
                stack.enter_context(mock.patch.object(shared_camera,'enumerate_camera_devices',return_value=names))
                opened=stack.enter_context(mock.patch.object(shared_camera.cv2,'VideoCapture',side_effect=AssertionError('camera forbidden')))
                stack.enter_context(mock.patch.object(self.module.importlib.util,'find_spec',return_value=True))
                stack.enter_context(mock.patch.object(Path,'read_text',return_value=json.dumps(config)))
                stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
                if succeeds:
                    result=self.module.check(True)
                    self.assertIsNone(result['CAMERA_OPENCV_INDEX'])
                    self.assertFalse(result['CAMERA_ALLOW_FALLBACK'])
                    self.assertEqual(result['CAMERA_NAME_HINTS'],['Logitech C922n'])
                    self.assertTrue(result['CAMERA_REQUIRE_NAME_MATCH'])
                    self.assertTrue(result['CAMERA_STRICT_BACKEND'])
                    self.assertEqual(result['CAMERA_BACKEND'],'dshow')
                else:
                    with self.assertRaisesRegex(RuntimeError,'exactly one C922'):
                        self.module.check(True)
                opened.assert_not_called()

    def test_external_check_only_never_spawns_or_opens_panel(self):
        with mock.patch.object(self.module.sys,'argv',['entry','--external-test','--check-only']), \
                mock.patch.object(self.module,'check',return_value={}) as check, \
                mock.patch.object(self.module.subprocess,'Popen') as spawn, \
                mock.patch.object(self.module.webbrowser,'open') as browser:
            self.module.main()
        check.assert_called_once_with(True,None)
        spawn.assert_not_called()
        browser.assert_not_called()


    def test_panel_only_recovers_ui_without_hardware_check_or_process(self):
        for url in ('http://127.0.0.1:8766/#token=fixture',None):
            with self.subTest(url=url), contextlib.ExitStack() as stack:
                stack.enter_context(mock.patch.object(self.module.sys,'argv',['entry','--external-test','--panel-only']))
                check=stack.enter_context(mock.patch.object(self.module,'check'))
                spawn=stack.enter_context(mock.patch.object(self.module.subprocess,'Popen'))
                stack.enter_context(mock.patch.object(self.module,'find_panel',return_value=url))
                browser=stack.enter_context(mock.patch.object(self.module.webbrowser,'open',return_value=True))
                stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
                if url:
                    self.module.main()
                    browser.assert_called_once_with(url)
                else:
                    with self.assertRaisesRegex(RuntimeError,'No authenticated'):
                        self.module.main()
                    browser.assert_not_called()
                check.assert_not_called()
                spawn.assert_not_called()


    def test_external_spawn_uses_session_config_and_discards_inherited_device_overrides(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.ExitStack() as stack:
            root=Path(folder)
            stack.enter_context(mock.patch.object(self.module,'ROOT',root))
            stack.enter_context(mock.patch.object(self.module.sys,'argv',['entry','--external-test']))
            stack.enter_context(mock.patch.object(self.module,'check',return_value={'DISPLAY_TARGET':'audience'}))
            kernel=mock.MagicMock()
            kernel.CreateMutexW.return_value=123
            stack.enter_context(mock.patch.object(self.module.ctypes,'WinDLL',return_value=kernel))
            stack.enter_context(mock.patch.object(self.module.ctypes,'get_last_error',return_value=0))
            socket=stack.enter_context(mock.patch.object(self.module.socket,'socket'))
            socket.return_value.__enter__.return_value.connect_ex.return_value=1
            spawn=stack.enter_context(mock.patch.object(self.module.subprocess,'Popen'))
            spawn.return_value.poll.return_value=None
            stack.enter_context(mock.patch.object(self.module,'find_panel',return_value='http://127.0.0.1:8766/#token=fixture'))
            stack.enter_context(mock.patch.object(self.module,'status',side_effect=[OSError('transient'),
                {'scene':{'current':'fixture','busy':False,'covered':False}}]))
            stack.enter_context(mock.patch.object(self.module.webbrowser,'open'))
            stack.enter_context(mock.patch.object(self.module.time,'sleep'))
            stack.enter_context(mock.patch.dict(os.environ,{'KIDZDISCO_CAMERA_ALLOW_FALLBACK':'true',
                'HARUKAZE_CAMERA_SHM':'stale','SDL_VIDEO_WINDOW_POS':'0,0'}))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            self.module.main()
            command=spawn.call_args.args[0]
            self.assertEqual(command[2],str(root/'scripts/start_operator.py'))
            self.assertEqual(command[3],'--config')
            self.assertEqual(json.loads(Path(command[4]).read_text(encoding='utf-8')),{'DISPLAY_TARGET':'audience'})
            environment=spawn.call_args.kwargs['env']
            self.assertNotIn('KIDZDISCO_CAMERA_ALLOW_FALLBACK',environment)
            self.assertNotIn('HARUKAZE_CAMERA_SHM',environment)
            self.assertNotIn('SDL_VIDEO_WINDOW_POS',environment)
            self.assertEqual(environment['SDL_WINDOWS_DPI_AWARENESS'],'permonitorv2')

    def test_required_camera_rechecks_ambiguity_and_reconnect_order_by_name(self):
        import shared_camera
        for devices,expected in ((['ACER HD User Facing','Logitech C922n'],1),
                                 (['Logitech C922n','ACER HD User Facing'],0)):
            with self.subTest(devices=devices),mock.patch.object(shared_camera,'enumerate_camera_devices',return_value=devices):
                self.assertEqual(shared_camera.resolve_camera_index(0,['Logitech C922n'],[],True),expected)
        with mock.patch.object(shared_camera,'enumerate_camera_devices',return_value=['C922n','C922n']):
            with self.assertRaisesRegex(RuntimeError,'Ambiguous'):
                shared_camera.resolve_camera_index(0,['C922n'],[],True)


class OperatorSingletonTests(unittest.TestCase):
    def setUp(self):
        self.module=load('operator_entry_fixture',ROOT/'scripts/start_operator.py')
        self.kernel=mock.MagicMock()
        self.kernel.CreateMutexW.return_value=123
        self.stack=contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(mock.patch.object(self.module.ctypes,'WinDLL',return_value=self.kernel))
        self.error=self.stack.enter_context(mock.patch.object(self.module.ctypes,'get_last_error',return_value=0))

    def test_existing_owner_rejects_before_manager_or_dpi(self):
        self.error.return_value=183
        with mock.patch.object(self.module.sys,'argv',['entry']), \
                mock.patch.object(self.module,'configure_audience_dpi') as dpi, \
                mock.patch.object(self.module.runpy,'run_path') as run:
            with self.assertRaisesRegex(RuntimeError,'already running or starting'):
                self.module.main()
        dpi.assert_not_called()
        run.assert_not_called()
        self.kernel.CloseHandle.assert_called_once_with(123)

    def test_lock_lives_until_manager_returns_and_closes_on_failure(self):
        with self.assertRaisesRegex(RuntimeError,'fixture'):
            with self.module.operator_session():
                self.kernel.CloseHandle.assert_not_called()
                raise RuntimeError('fixture')
        self.kernel.CloseHandle.assert_called_once_with(123)

    def test_failed_create_does_not_close_unowned_handle(self):
        self.kernel.CreateMutexW.return_value=0
        with self.assertRaises(OSError):
            with self.module.operator_session():
                self.fail('must not run')
        self.kernel.CloseHandle.assert_not_called()
