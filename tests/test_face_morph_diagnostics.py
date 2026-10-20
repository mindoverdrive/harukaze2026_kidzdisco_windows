import unittest
from face_morph_diagnostics import FaceCheckDiagnostics


class DiagnosticRateTests(unittest.TestCase):
    def test_repeated_clock_sample_and_no_frames_are_safe(self):
        self.assertEqual(FaceCheckDiagnostics.rate([], 3), 0)
        self.assertEqual(FaceCheckDiagnostics.rate([3, 3], 3), 0)

    def test_stale_samples_do_not_report_a_live_rate(self):
        self.assertEqual(FaceCheckDiagnostics.rate([1, 1.1, 1.2], 5), 0)
        self.assertEqual(FaceCheckDiagnostics.rate([1, 3, 3.1, 3.2], 3.2), 10)


if __name__ == '__main__':
    unittest.main()
