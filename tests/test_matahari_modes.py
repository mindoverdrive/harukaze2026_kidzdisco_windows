"""Current production mode policy, using the existing Manager fixture only."""
import json
import ast
import os
import importlib.util
from pathlib import Path
import unittest
from unittest import mock

import manager
from staff_scene_manager import StaffSceneManager
import test_staff_lifecycle
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


class ModeConfigurationTests(unittest.TestCase):
    def test_existing_acer_profile_includes_otedama_once_and_preserves_initial_hand_scene(self):
        path = os.environ.get('MATAHARI_MODE_ACER_SOURCE')
        if not path:
            path = str(ROOT/'tools/start_hand_play.py')
        tree = ast.parse(Path(path).read_text(encoding='utf-8-sig'))
        main = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        # Execute only the actual list setup, initial-scene choice and append;
        # never execute preflight, camera enumeration, subprocess or GUI code.
        statements = [n for n in main.body if
                      isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='scenes' for t in n.targets)
                      or isinstance(n,ast.If) and any(isinstance(x,ast.Attribute) and isinstance(x.value,ast.Name)
                          and x.value.id=='scenes' for x in ast.walk(n))
                      or isinstance(n,ast.Expr) and isinstance(n.value,ast.Call)
                          and isinstance(n.value.func,ast.Attribute) and isinstance(n.value.func.value,ast.Name)
                          and n.value.func.value.id=='scenes']
        for initial in ('shapes','drawing'):
            ns = {'args':SimpleNamespace(scene=initial)}
            exec(compile(ast.Module(body=statements,type_ignores=[]),str(path),'exec'),ns)
            self.assertEqual(len(ns['scenes']),3)
            self.assertEqual(ns['scenes'].count('modern_otedama_acer.py'),1)
            self.assertEqual(ns['scenes'][0],f'hand_{initial}_acer.py')
            self.assertNotIn('minecraft_staff_acer.py',ns['scenes'])
        config = next(n.value for n in main.body if isinstance(n,ast.Assign)
                      and any(isinstance(t,ast.Name) and t.id=='config' for t in n.targets))
        fields = {k.value:v for k,v in zip(config.keys,config.values)}
        self.assertTrue(fields['TRANSITION_ENABLED'].value)
        self.assertEqual(fields['DISPLAY_TARGET'].value,'stage')

    def launcher_module(self):
        path = os.environ.get('MATAHARI_MODE_ACER_SOURCE',
                             str(ROOT/'tools/start_hand_play.py'))
        spec = importlib.util.spec_from_file_location('mode_launcher_fixture',path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_user_entry_opens_only_its_loopback_operator_url_without_starting_another_manager(self):
        module = self.launcher_module()
        path = SimpleNamespace(parent=Path('fixture_logs'), read_text=mock.Mock(
            return_value='[Operator] http://127.0.0.1:8767/#token=test_fixture\n'))
        process = mock.Mock(**{'poll.return_value':None})
        with mock.patch.object(module.webbrowser,'open',return_value=True) as open_page, \
                mock.patch.object(module.subprocess,'Popen') as spawn:
            module.open_panel_when_ready(process,path)
        open_page.assert_called_once_with('http://127.0.0.1:8767/#token=test_fixture')
        spawn.assert_not_called()

    def test_user_entry_reports_exit_or_timeout_without_killing_or_relaunching(self):
        module = self.launcher_module()
        path = SimpleNamespace(parent=Path('fixture_logs'), read_text=mock.Mock(
            return_value='[Operator] https://external.invalid/#token=ignored\n'))
        with mock.patch.object(module.webbrowser,'open') as open_page, \
                mock.patch.object(module.subprocess,'Popen') as spawn:
            with self.assertRaisesRegex(RuntimeError,'exited'):
                module.open_panel_when_ready(mock.Mock(**{'poll.return_value':1}),path)
            process = mock.Mock(**{'poll.return_value':None})
            with mock.patch.object(module.time,'monotonic',side_effect=[0.,31.]):
                with self.assertRaisesRegex(RuntimeError,'may remain running'):
                    module.open_panel_when_ready(process,path)
            process.kill.assert_not_called()
            open_page.assert_not_called()
            spawn.assert_not_called()

    def test_actual_normal_playlist_has_twenty_entries_and_otedama_exactly_once(self):
        config = json.loads((ROOT/'configs/rebirth_operator_acer_xiaomi.json').read_text())
        names = config['PRODUCTION_SCENES']
        self.assertEqual(len(names),20)
        self.assertEqual(len(set(names)),20)
        self.assertEqual(names.count('modern_otedama_acer.py'),1)
        self.assertNotIn('minecraft_staff_acer.py',names)
        self.assertNotIn('minecraft.py',names)
        with mock.patch('builtins.print'):
            sm = StaffSceneManager(scenes=[str(ROOT/name) for name in names])
        self.addCleanup(sm.cleanup)
        self.assertEqual(list(sm.staff_scenes),['minecraft'])
        self.assertEqual(sm.operator_snapshot()['staff']['scenes'],[{'id':'minecraft','label':'マイクラ風'}])
        for identifier in ('hand_draw','otedama','modern_otedama_acer.py'):
            with self.subTest(identifier=identifier), self.assertRaises(manager.ConfigurationError):
                sm.request_staff(identifier)


class OtedamaModeNavigationTests(unittest.TestCase):
    setUp = test_staff_lifecycle.StaffLifecycleTests.setUp
    promote = test_staff_lifecycle.StaffLifecycleTests.promote

    def configure_otedama(self):
        self.sm.all_scenes = ['living_mosaic_acer.py','modern_otedama_acer.py','earth_acer.py']
        self.sm.running_scene_path = 'modern_otedama_acer.py'
        self.sm.current_scene_name = 'modern_otedama_acer.py'
        self.sm.scene_index = 2

    def test_normal_otedama_accepts_next_back_and_direct_selection(self):
        for action,scene,target in (('next',None,'earth_acer.py'),
                                    ('back',None,'living_mosaic_acer.py'),
                                    ('select','modern_otedama_acer.py','modern_otedama_acer.py')):
            with self.subTest(action=action):
                self.setUp()
                self.configure_otedama()
                self.assertTrue(self.sm.request_scene(action,scene))
                self.assertEqual(self.sm.preloaded_scene_path,target)
                self.assertEqual(self.sm.staff_mode,'normal')
                self.promote()
                self.assertEqual(self.sm.running_scene_path,target)
                self.assertFalse(self.sm.staff_locked)

    def test_minecraft_returns_to_interrupted_otedama_and_normal_navigation_unlocks(self):
        self.configure_otedama()
        self.assertTrue(self.sm.request_staff('minecraft'))
        self.assertEqual(self.sm.return_scene,'modern_otedama_acer.py')
        old = self.sm.running_process
        self.assertIs(self.sm.running_process,old)
        self.promote()
        self.assertEqual(self.sm.staff_mode,'active')
        self.assertFalse(self.sm.request_scene('next'))
        self.control.poll.return_value = 'READY'
        self.assertTrue(self.sm.return_to_rotation())
        self.assertEqual(self.sm.preloaded_scene_path,'modern_otedama_acer.py')
        self.promote()
        self.assertEqual(self.sm.staff_mode,'normal')
        self.assertEqual(self.sm.running_scene_path,'modern_otedama_acer.py')
        self.assertEqual(self.sm.scene_index,2)
        self.control.poll.return_value = 'READY'
        self.assertTrue(self.sm.request_scene('next'))
        self.assertEqual(self.sm.preloaded_scene_path,'earth_acer.py')


if __name__ == '__main__':
    unittest.main()
