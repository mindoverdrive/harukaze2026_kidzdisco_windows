"""Runner finalization fault injection without scenes, sockets, or OS state changes."""

import io
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

import scene_control
import scene_profile_runner


class RunnerFinalizationTests(unittest.TestCase):
    def run_case(self, *, scene_failure=None, close_failure=None, finish_failure=None,
                 signal_failure=None, constructor_failure=None, send_failure=None,
                 environment_type=dict, managed=True):
        prior_control = mock.Mock(name="enclosing_control")
        prior_lifecycle = object()
        prior_handler = object()
        prior_argv = ["fixture_acer.py", "--fixture-option"]
        if managed:
            prior_argv += ["--control-port", "1", "--launch-id", "finalization-test"]
        prior_environment = {"KIDZDISCO_CAMERA_INDEX": "7", "RUNNER_TEST_KEEP": "inherited"}
        environment = environment_type(prior_environment)
        control = mock.Mock(name="owned_control")
        control.close.side_effect = close_failure
        control.send.side_effect = send_failure
        lifecycle = scene_control.SceneLifecycle("finger_colorfull_dots_2.py")
        lifecycle.finish = mock.Mock(wraps=lifecycle.finish)
        caught = None
        with (
            mock.patch.object(scene_profile_runner.os, "environ", environment),
            mock.patch.object(sys, "argv", list(prior_argv)),
            mock.patch.object(scene_control, "_child_control", prior_control),
            mock.patch.object(scene_control, "_scene_lifecycle", prior_lifecycle),
            mock.patch.object(scene_control, "SceneLifecycle", return_value=lifecycle),
            mock.patch.object(scene_control, "SceneChildControl", return_value=control,
                              side_effect=constructor_failure) as construct_control,
            mock.patch.object(scene_profile_runner.runpy, "run_path", side_effect=scene_failure,
                              return_value={}) as run_path,
            mock.patch.object(scene_profile_runner.signal, "SIGBREAK", 21, create=True),
            mock.patch.object(scene_profile_runner.signal, "signal",
                              side_effect=[prior_handler, signal_failure]) as set_signal,
            mock.patch("builtins.print", side_effect=finish_failure),
            mock.patch.object(sys, "stderr", io.StringIO()),
        ):
            try:
                scene_profile_runner.run_scene("finger_colorfull_dots_2.py", profile="acer")
            except BaseException as exc:
                caught = exc
            state = SimpleNamespace(
                child_control=scene_control._child_control,
                lifecycle=scene_control._scene_lifecycle,
                argv=list(sys.argv),
                environment=dict(environment),
            )
        return SimpleNamespace(
            caught=caught, state=state, control=control, lifecycle=lifecycle,
            prior_control=prior_control, prior_lifecycle=prior_lifecycle,
            prior_argv=prior_argv, prior_environment=prior_environment,
            prior_handler=prior_handler, set_signal=set_signal,
            construct_control=construct_control, run_path=run_path,
        )

    def assert_restored(self, result, *, expected_environment=None):
        self.assertIs(result.state.child_control, result.prior_control)
        self.assertIs(result.state.lifecycle, result.prior_lifecycle)
        self.assertEqual(result.state.argv, result.prior_argv)
        self.assertEqual(result.state.environment,
                         result.prior_environment if expected_environment is None else expected_environment)
        self.assertEqual(result.set_signal.call_count, 2)
        self.assertEqual(result.set_signal.call_args.args, (21, result.prior_handler))
        result.prior_control.close.assert_not_called()

    def test_scene_failure_survives_close_failure_and_restores_state(self):
        for failure in (RuntimeError("scene failed"), SystemExit(7), KeyboardInterrupt()):
            with self.subTest(failure=type(failure).__name__):
                result = self.run_case(scene_failure=failure, close_failure=OSError("close failed"))
                self.assertIs(result.caught, failure)
                result.lifecycle.finish.assert_called_once_with(failure)
                result.control.close.assert_called_once_with()
                self.assert_restored(result)

    def test_finish_interrupt_and_close_failure_do_not_mask_scene_failure(self):
        failure = RuntimeError("original scene error")
        result = self.run_case(scene_failure=failure,
                               finish_failure=KeyboardInterrupt("interrupt during runner_end"),
                               close_failure=OSError("close failed"))
        self.assertIs(result.caught, failure)
        result.control.close.assert_called_once_with()
        self.assert_restored(result)
        self.assertEqual(failure.__notes__, ["Runner lifecycle.finish failed: KeyboardInterrupt",
                                            "Runner control.close failed: OSError"])

    def test_close_failure_after_normal_return_is_raised_after_restoration(self):
        failure = OSError("close failed after return")
        result = self.run_case(close_failure=failure, signal_failure=RuntimeError("signal restore failed"))
        self.assertIs(result.caught, failure)
        result.lifecycle.finish.assert_called_once_with(None)
        self.assert_restored(result)
        self.assertEqual(failure.__notes__, ["Runner signal restore failed: RuntimeError"])

    def test_finish_interrupt_after_normal_return_is_raised_after_other_cleanup(self):
        failure = KeyboardInterrupt("interrupt during runner_end")
        result = self.run_case(finish_failure=failure, close_failure=OSError("close failed"))
        self.assertIs(result.caught, failure)
        result.control.close.assert_called_once_with()
        self.assert_restored(result)

    def test_error_notification_failure_preserves_the_original_exception(self):
        for notification_failure in (BrokenPipeError("disconnected control"),
                                     scene_control.SceneControlError("control message failed"),
                                     RuntimeError("notification failed"), KeyboardInterrupt()):
            with self.subTest(notification_failure=type(notification_failure).__name__):
                failure = RuntimeError("original scene error")
                result = self.run_case(scene_failure=failure, send_failure=notification_failure)
                self.assertIs(result.caught, failure)
                result.lifecycle.finish.assert_called_once_with(failure)
                result.control.close.assert_called_once_with()
                self.assert_restored(result)
                self.assertEqual(failure.__notes__,
                                 [f"Runner ERROR notification failed: {type(notification_failure).__name__}"])

    def test_error_notification_formatting_cannot_replace_the_original_exception(self):
        class UnprintableSceneError(RuntimeError):
            def __str__(self):
                raise ValueError("exception formatting failed")

        failure = UnprintableSceneError()
        result = self.run_case(scene_failure=failure)
        self.assertIs(result.caught, failure)
        result.control.send.assert_not_called()
        result.control.close.assert_called_once_with()
        self.assert_restored(result)
        self.assertEqual(failure.__notes__, ["Runner ERROR notification failed: ValueError"])

    def test_environment_restore_failure_does_not_skip_later_keys(self):
        class PartlyFailingEnvironment(dict):
            def pop(self, key, *args):
                if key == "KIDZDISCO_DISPLAY_TARGET":
                    raise OSError("environment restore failed")
                return super().pop(key, *args)

        failure = RuntimeError("original scene error")
        result = self.run_case(scene_failure=failure, environment_type=PartlyFailingEnvironment)
        self.assertIs(result.caught, failure)
        expected_environment = {**result.prior_environment, "KIDZDISCO_DISPLAY_TARGET": "primary"}
        self.assert_restored(result, expected_environment=expected_environment)

    def test_signal_restore_failure_does_not_skip_environment_or_replace_scene_failure(self):
        for scene_failure in (None, RuntimeError("scene failed")):
            with self.subTest(scene_failure=scene_failure):
                signal_failure = OSError("signal restore failed")
                result = self.run_case(scene_failure=scene_failure, signal_failure=signal_failure)
                self.assertIs(result.caught, scene_failure or signal_failure)
                result.control.close.assert_called_once_with()
                self.assert_restored(result)

    def test_standalone_return_and_failure_restore_enclosing_control(self):
        for failure in (None, ValueError("standalone scene failed")):
            with self.subTest(failure=failure):
                result = self.run_case(scene_failure=failure, managed=False)
                self.assertIs(result.caught, failure)
                result.construct_control.assert_not_called()
                result.control.close.assert_not_called()
                self.assert_restored(result)

    def test_managed_return_restores_enclosing_control_and_lifecycle(self):
        result = self.run_case()
        self.assertIsNone(result.caught)
        result.control.wait_for_start.assert_called_once_with()
        result.control.close.assert_called_once_with()
        self.assert_restored(result)

    def test_control_constructor_failure_restores_state_without_closing_enclosing_control(self):
        failure = OSError("control connection failed")
        result = self.run_case(constructor_failure=failure)
        self.assertIs(result.caught, failure)
        result.run_path.assert_not_called()
        result.control.close.assert_not_called()
        result.lifecycle.finish.assert_called_once_with(failure)
        self.assert_restored(result)


if __name__ == "__main__":
    unittest.main()
