import unittest
import test_scene_navigation


class OperatorNavigationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_scene_navigation.NavigationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.sm = self.fixture.sm
        self.overlay = self.fixture.overlay

    def test_restart_uses_current_scene_and_cover(self):
        self.assertTrue(self.sm.request_scene('restart'))
        self.assertEqual(self.sm.requested_scene_index, 0)
        self.assertEqual(self.fixture.events, ['cover'])

    def test_safe_does_not_stop_scene_and_resume_requires_cover(self):
        self.assertTrue(self.sm.request_safe())
        self.assertEqual(self.fixture.events, ['cover'])
        self.overlay.holding_cover = False
        self.assertFalse(self.sm.resume_safe())
        self.overlay.holding_cover = True
        self.assertTrue(self.sm.resume_safe())
        self.assertEqual(self.fixture.events, ['cover', 'reveal'])

    def test_safe_during_switch_suppresses_reveal(self):
        self.sm.request_scene('next')
        self.sm.request_safe()
        self.overlay.covered = True
        self.overlay.holding_cover = True
        self.fixture.control.poll.return_value = 'FIRST_FRAME'
        self.sm.tick()
        self.assertNotIn('reveal', self.fixture.events)
        self.assertTrue(self.sm.operator_snapshot()['covered'])

    def test_restart_from_safe_reuses_cover(self):
        self.sm.request_safe()
        self.overlay.covered = True
        self.overlay.holding_cover = True
        self.assertTrue(self.sm.request_scene('restart'))
        self.assertEqual(self.fixture.events.count('cover'), 1)
        self.assertFalse(self.sm.safe_requested)

    def test_dead_scene_cannot_resume(self):
        self.sm.request_safe()
        self.overlay.holding_cover = True
        self.fixture.old.poll.return_value = 1
        self.assertFalse(self.sm.resume_safe())

    def test_failed_candidate_keeps_safe_cover(self):
        self.sm.request_scene('next')
        self.sm.request_safe()
        self.overlay.covered = True
        self.sm._fail_switch('injected READY failure')
        self.sm.tick()
        self.assertNotIn('reveal', self.fixture.events)
        self.assertTrue(self.sm.safe_requested)

    def test_safe_while_revealing_waits_then_covers(self):
        self.sm.transition = self.overlay
        self.overlay.busy = True
        self.overlay.holding_cover = False
        self.sm.request_safe()
        self.assertEqual(self.fixture.events, [])
        self.overlay.busy = False
        self.sm.tick()
        self.assertEqual(self.fixture.events, ['cover'])
