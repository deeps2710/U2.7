from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ultron27.planner import DEFAULT_DATASET_PATH, DatasetPlanner
from ultron27.policy import decide
from ultron27.tools import validate_tool_call


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate safety regression cases against planner and policy.")
    parser.add_argument("--cases", type=Path, default=Path("data/regression/safety_cases.jsonl"))
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    planner = DatasetPlanner.from_jsonl(args.dataset)
    total = 0
    policy_matches = 0
    tool_matches = 0
    misses = []

    for line in args.cases.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        case = json.loads(line)
        plan = planner.plan(case["utterance"])
        decision = decide(plan, validate_tool_call(plan.tool_call), confirmed=False)
        expected_action = case["expected_policy_action"]

        total += 1
        tool_ok = plan.tool_call.name == case["expected_tool"]
        policy_ok = decision.action == expected_action
        tool_matches += int(tool_ok)
        policy_matches += int(policy_ok)

        if len(misses) < 10 and not (tool_ok and policy_ok):
            misses.append(
                {
                    "utterance": case["utterance"],
                    "expected_tool": case["expected_tool"],
                    "actual_tool": plan.tool_call.name,
                    "expected_policy_action": expected_action,
                    "actual_policy_action": decision.action,
                }
            )
        if args.limit is not None and total >= args.limit:
            break

    result = {
        "total": total,
        "tool_accuracy": round(tool_matches / total, 4) if total else 0.0,
        "policy_action_accuracy": round(policy_matches / total, 4) if total else 0.0,
        "sample_misses": misses,
    }
    print(json.dumps(result, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()

