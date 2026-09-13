"""Validate the executable Skill's arithmetic and input boundaries."""

import json
import subprocess
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "skills/minecraft-balance/scripts/analyze_balance.py"


class BalanceToolTests(unittest.TestCase):
    def run_tool(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args], capture_output=True,
            encoding="utf-8", timeout=10, check=False,
        )

    def output(self, *args):
        result = self.run_tool(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["game_tested"])
        self.assertEqual(payload["evidence"], "deterministic_input_calculation")
        return payload

    def test_reward_cycle_distinguishes_cooldown_start(self):
        common = ("reward", "--reward", "8", "--success-probability", "0.25",
                  "--task-seconds", "120", "--cooldown-seconds", "60", "--cooldown-start")
        completion = self.output(*common, "completion")
        acceptance = self.output(*common, "acceptance")
        self.assertEqual(completion["cycle_seconds"], 180)
        self.assertEqual(completion["long_run_expected_reward_per_hour"], 40)
        self.assertEqual(acceptance["cycle_seconds"], 120)
        self.assertEqual(acceptance["long_run_expected_reward_per_hour"], 60)

    def test_probability_known_example_and_boundaries(self):
        for chance, count, expected in [("0.1", "3", .271), ("0", "5", 0),
                                        ("1", "5", 1), ("1", "0", 0)]:
            with self.subTest(chance=chance, count=count):
                output = self.output("probability", "--success-probability", chance, "--attempts", count)
                self.assertAlmostEqual(output["probability_at_least_one_success"], expected)

    def test_tiny_probability_retains_precision(self):
        output = self.output("probability", "--success-probability", "1e-20", "--attempts", "10")
        self.assertGreater(output["probability_at_least_one_success"], 0)
        self.assertAlmostEqual(output["probability_at_least_one_success"] / 1e-19, 1)

    def test_invalid_probabilities_and_attempts_are_rejected(self):
        cases = [(value, "3") for value in ("nan", "inf", "-0.1", "1.1")]
        cases += [("0.5", value) for value in ("2.5", "-1", "1000000001")]
        for chance, count in cases:
            with self.subTest(chance=chance, count=count):
                result = self.run_tool("probability", "--success-probability", chance, "--attempts", count)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")

    def test_zero_cycle_and_overflow_are_rejected(self):
        for reward, task, cooldown in [("1", "0", "0"), ("1e308", "1", "0"),
                                       ("1", "1e308", "1e308")]:
            with self.subTest(reward=reward, task=task, cooldown=cooldown):
                result = self.run_tool("reward", "--reward", reward, "--task-seconds", task,
                                       "--cooldown-seconds", cooldown, "--cooldown-start", "completion")
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
