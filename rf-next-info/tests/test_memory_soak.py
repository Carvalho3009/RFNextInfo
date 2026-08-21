import os
import unittest

from tools.memory_soak import (
    MIB,
    MemorySample,
    _working_set_bytes,
    analyze_samples,
)


class MemorySoakTest(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Working Set disponível no Windows")
    def test_reads_current_process_working_set(self):
        self.assertGreater(_working_set_bytes(os.getpid()), 0)

    def test_stable_ten_hour_run_passes(self):
        samples = [
            MemorySample(hour * 3600, (220 + hour) * MIB)
            for hour in range(11)
        ]

        result = analyze_samples(samples)

        self.assertTrue(result["passed"])
        self.assertFalse(result["target_exceeded"])
        self.assertLess(result["tail_slope_bytes_per_hour"], 2 * MIB)

    def test_runaway_memory_fails_slope_and_hard_limit(self):
        samples = [
            MemorySample(hour * 3600, (220 + hour * 100) * MIB)
            for hour in range(11)
        ]

        result = analyze_samples(samples)

        self.assertFalse(result["passed"])
        self.assertFalse(result["hard_limit_ok"])
        self.assertFalse(result["slope_ok"])

    def test_selected_budget_can_be_used_as_release_limit(self):
        samples = [
            MemorySample(hour * 3600, 300 * MIB)
            for hour in range(11)
        ]

        result = analyze_samples(
            samples,
            target_bytes=256 * MIB,
            hard_limit_bytes=256 * MIB,
        )

        self.assertTrue(result["target_exceeded"])
        self.assertFalse(result["hard_limit_ok"])
        self.assertFalse(result["passed"])

    def test_observed_eight_to_fourteen_hour_samples_are_not_stable_enough(self):
        samples = [
            MemorySample(8 * 3600, 800 * MIB),
            MemorySample(11 * 3600, 500 * MIB),
            MemorySample(14 * 3600, 990 * MIB),
        ]

        result = analyze_samples(samples, warmup_seconds=0)

        self.assertFalse(result["passed"])
        self.assertFalse(result["slope_ok"])
        self.assertEqual(result["peak_working_set_bytes"], 990 * MIB)


if __name__ == "__main__":
    unittest.main()
