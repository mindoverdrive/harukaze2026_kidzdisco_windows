import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('gpu_observer', Path(__file__).resolve().parents[1]/'scripts/observe_trial_gpu.py')
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)


class GpuObservationTests(unittest.TestCase):
    def test_missing_instance_is_unknown(self):
        p = {'pid': 12, 'creation_ticks': 100}
        self.assertIsNone(observer.match_counters(p, p, p, [])['dedicated_bytes'])

    def test_reused_pid_is_not_attributed(self):
        p = {'pid': 12, 'creation_ticks': 100}
        reused = dict(p, creation_ticks=101)
        self.assertIn('unavailable', observer.match_counters(p, p, reused, []))

    def test_multiple_adapters_and_duplicate_instance(self):
        p = {'pid': 12, 'creation_ticks': 100}
        a = {'Name': 'pid_12_luid_A_phys_0', 'DedicatedUsage': 10, 'SharedUsage': 20}
        b = {'Name': 'pid_12_luid_B_phys_0', 'DedicatedUsage': 30, 'SharedUsage': 40}
        unrelated = dict(a, Name='pid_123_luid_A_phys_0')
        result = observer.match_counters(p, p, p, [a, b, a, unrelated])
        self.assertEqual((result['dedicated_bytes'], result['shared_bytes']), (40, 60))

    def test_missing_value_is_not_zero(self):
        p = {'pid': 12, 'creation_ticks': 100}
        result = observer.match_counters(p, p, p, [{'Name': 'pid_12_luid_A_phys_0', 'SharedUsage': 0}])
        self.assertIn('unavailable', result)


if __name__ == '__main__':
    unittest.main()
