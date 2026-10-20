import unittest
import test_operator_panel


class StaffOperatorTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_operator_panel.OperatorPanelTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.panel = self.fixture.panel()

    def test_staff_commands_use_existing_authenticated_channel(self):
        for payload in ({'action': 'staff_start', 'scene': 'minecraft', 'revision': 0},
                        {'action': 'staff_return', 'revision': 2}):
            self.fixture.request(self.panel, '/api/action', payload)
            self.assertEqual(self.panel.consume_action(), payload)

    def test_staff_request_requires_authorization_and_revision(self):
        code, _ = self.fixture.request(self.panel, '/api/action', {'action': 'staff_return', 'revision': 0}, authorized=False)
        self.assertEqual(code, 401)
        code, _ = self.fixture.request(self.panel, '/api/action', {'action': 'staff_return'})
        self.assertEqual(code, 404)
        self.assertIsNone(self.panel.consume_action())

    def test_revision_is_preserved_for_normal_navigation(self):
        payload = {'action': 'back', 'revision': 7}
        self.fixture.request(self.panel, '/api/action', payload)
        self.assertEqual(self.panel.consume_action(), payload)

    def test_mode_change_discards_navigation_but_preserves_quit(self):
        self.panel.actions.put_nowait('next')
        self.panel.discard_actions()
        self.assertIsNone(self.panel.consume_action())
        self.panel.actions.put_nowait('quit')
        self.panel.discard_actions()
        self.assertEqual(self.panel.consume_action(), 'quit')

    def test_queue_is_bounded_during_repeated_clicks(self):
        payload = {'action': 'staff_start', 'scene': 'minecraft', 'revision': 0}
        self.fixture.request(self.panel, '/api/action', payload)
        code, _ = self.fixture.request(self.panel, '/api/action', payload)
        self.assertEqual(code, 409)

    def test_fresh_click_survives_mode_revision_publication(self):
        action = {'action': 'staff_return', 'revision': 3}
        self.panel.actions.put_nowait(action)
        self.panel.discard_actions(3)
        self.assertEqual(self.panel.consume_action(), action)
