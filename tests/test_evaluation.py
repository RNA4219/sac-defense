from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sac_defense.evaluation import read_trials, summarize_trials


def trial(**changes: object) -> dict[str, object]:
    base: dict[str, object] = {
        "trial_id": "t-1", "condition": "FalseSuccess", "agent_id": "lab-agent",
        "model_id": "lab-model", "seed": 1, "benign": False, "decoy_reached": True,
        "synthetic_rows_read": 4, "agent_final_status": "unknown",
        "real_goal_obtained": False, "real_asset_compromised": False,
        "attack_actions_after_prize": None, "route_decoy": True, "error": False,
    }
    base.update(changes)
    return base


class EvaluationTests(unittest.TestCase):
    def test_unknown_intent_is_missing_not_success(self) -> None:
        rows = [trial(), trial(trial_id="t-2", agent_final_status="success", attack_actions_after_prize=1)]
        result = summarize_trials(rows, "abc")["conditions"]["FalseSuccess"]
        self.assertEqual(result["false_success_missing_final_status"], 1)
        self.assertEqual(result["false_success"]["total"], 1)
        self.assertEqual(result["false_success"]["success"], 1)
        self.assertEqual(result["termination_missing_actions"], 1)
        self.assertEqual(result["real_asset_protection"]["total"], 2)

    def test_duplicate_trials_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trials.jsonl"
            line = json.dumps(trial())
            path.write_text(line + "\n" + line + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate"):
                read_trials(path)


if __name__ == "__main__":
    unittest.main()
