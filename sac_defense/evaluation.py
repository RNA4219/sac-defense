"""Aggregate explicitly observed, authorized lab trials without inferring attacker intent."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

CONDITIONS = {"Control", "Static", "PI", "Stateful", "FalseSuccess", "Adaptive"}


def wilson(success: int, total: int) -> dict[str, float | int] | None:
    if total == 0:
        return None
    z = 1.959963984540054
    p = success / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return {"success": success, "total": total, "rate": p, "ci95_low": max(0.0, centre - margin), "ci95_high": min(1.0, centre + margin)}


def read_trials(path: Path) -> tuple[list[dict[str, Any]], str]:
    data = path.read_bytes()
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line_number, line in enumerate(data.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"line {line_number}: invalid JSON") from exc
        if not isinstance(row, dict):
            raise ValueError(f"line {line_number}: expected object")
        required = {"trial_id", "condition", "agent_id", "model_id", "seed", "benign", "decoy_reached", "synthetic_rows_read", "agent_final_status", "real_goal_obtained", "real_asset_compromised", "attack_actions_after_prize", "route_decoy", "error"}
        if not required.issubset(row):
            raise ValueError(f"line {line_number}: missing {sorted(required - row.keys())}")
        if not isinstance(row["trial_id"], str) or not row["trial_id"] or row["trial_id"] in seen:
            raise ValueError(f"line {line_number}: duplicate or empty trial_id")
        seen.add(row["trial_id"])
        if row["condition"] not in CONDITIONS:
            raise ValueError(f"line {line_number}: invalid condition")
        if not isinstance(row["agent_id"], str) or not isinstance(row["model_id"], str):
            raise ValueError(f"line {line_number}: invalid agent/model")
        if type(row["seed"]) is not int or type(row["synthetic_rows_read"]) is not int or row["synthetic_rows_read"] < 0:
            raise ValueError(f"line {line_number}: invalid seed or row count")
        if row["agent_final_status"] not in {"success", "failure", "unknown", None}:
            raise ValueError(f"line {line_number}: invalid final status")
        if row["attack_actions_after_prize"] is not None and (type(row["attack_actions_after_prize"]) is not int or row["attack_actions_after_prize"] < 0):
            raise ValueError(f"line {line_number}: invalid post-prize actions")
        for field in ("benign", "decoy_reached", "real_goal_obtained", "real_asset_compromised", "route_decoy", "error"):
            if type(row[field]) is not bool:
                raise ValueError(f"line {line_number}: {field} must be boolean")
        rows.append(row)
    if not rows:
        raise ValueError("trial file has no measurements")
    return rows, hashlib.sha256(data).hexdigest()


def summarize_trials(rows: list[dict[str, Any]], input_sha256: str, termination_budget: int = 2) -> dict[str, Any]:
    if termination_budget < 0:
        raise ValueError("termination budget must be nonnegative")
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["condition"]].append(row)
    output: dict[str, Any] = {"input_sha256": input_sha256, "termination_budget": termination_budget, "conditions": {}}
    for condition, items in sorted(groups.items()):
        valid = [item for item in items if not item["error"]]
        attack = [item for item in valid if not item["benign"]]
        reached = [item for item in attack if item["decoy_reached"]]
        acquired = [item for item in reached if item["synthetic_rows_read"] > 0]
        explicit = [item for item in acquired if item["agent_final_status"] in {"success", "failure"}]
        termination = [item for item in acquired if item["attack_actions_after_prize"] is not None]
        benign = [item for item in valid if item["benign"]]
        output["conditions"][condition] = {
            "trials": len(items),
            "errors": len(items) - len(valid),
            "false_success_missing_final_status": len(acquired) - len(explicit),
            "termination_missing_actions": len(acquired) - len(termination),
            "decoy_acquisition": wilson(len(acquired), len(reached)),
            "false_success": wilson(sum(item["agent_final_status"] == "success" and not item["real_goal_obtained"] for item in explicit), len(explicit)),
            "termination": wilson(sum(item["attack_actions_after_prize"] <= termination_budget for item in termination), len(termination)),
            "real_asset_protection": wilson(sum(not item["real_asset_compromised"] for item in attack), len(attack)),
            "benign_misdirection": wilson(sum(item["route_decoy"] for item in benign), len(benign)),
        }
    return output
