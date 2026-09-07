"""Verify the chosen Mandala version and the existing checked audience entry."""
import os
from pathlib import Path
import runpy
import unittest
from unittest import mock

import test_grid_launch

ROOT = Path(__file__).resolve().parents[1]


class Mandala3LaunchTests(unittest.TestCase):
    run_launcher = test_grid_launch.GridLaunchTests.run_launcher

    def test_acer_entry_executes_version_three_with_acer_profile(self):
        with mock.patch('scene_profile_runner.run_scene') as run_scene:
            runpy.run_path(str(ROOT / 'finger_mandala_acer.py'), run_name='__main__')
        run_scene.assert_called_once_with('finger_mandala_3.py', profile='acer')

    @unittest.skipUnless(os.name == 'nt', 'Acer audience configuration requires Windows')
    def test_trial_keeps_camera_settings_and_single_checked_entry(self):
        result = self.run_launcher(
            ['--audience', '--scene', 'mandala3', '--duration-minutes', '31'],
            base_overrides={'CAMERA_EXPOSURE': -4, 'CAMERA_ZOOM': 176})
        self.assertEqual(result['exit_code'], 0, result['stderr'])
        config = result['observed']['config']
        self.assertEqual(config['PRODUCTION_SCENES'], ['finger_mandala_acer.py'])
        self.assertEqual((config['CAMERA_EXPOSURE'], config['CAMERA_ZOOM']), (-4, 176))
        self.assertTrue(config['SHARED_CAMERA_ENABLED'])
        self.assertEqual(config['DISPLAY_TARGET'], 'audience')
        self.assertEqual(config['PRELOAD_COUNT'], 0)
        self.assertFalse(config['TRANSITION_ENABLED'])
        self.assertFalse(config['CLAP_MONITOR_ENABLED'])
        argv = result['observed']['argv']
        self.assertEqual(argv[argv.index('--duration-seconds') + 1], '1860.0')

    def test_no_audience_or_nonlocal_operator_cannot_start(self):
        for args in (['--scene', 'mandala3'],
                     ['--audience', '--scene', 'mandala3', '--operator-host', '0.0.0.0']):
            with self.subTest(args=args):
                result = self.run_launcher(args)
                self.assertEqual(result['exit_code'], 2)
                self.assertEqual(result['observed'], {})
                self.assertEqual(result['import_count'], 0)

    @unittest.skipUnless(os.name == 'nt', 'Acer audience configuration requires Windows')
    def test_missing_display_or_detector_blocks_launch(self):
        for kwargs in ({'audience_present': False}, {'missing_modules': ('mediapipe',)}):
            with self.subTest(kwargs=kwargs):
                result = self.run_launcher(['--audience', '--scene', 'mandala3'], **kwargs)
                self.assertEqual(result['exit_code'], 2)
                self.assertEqual(result['observed'], {})


if __name__ == '__main__':
    unittest.main()
