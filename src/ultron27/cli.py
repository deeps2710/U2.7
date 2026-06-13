from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .audit import append_audit_record
from .executor import Executor
from .planner import DEFAULT_DATASET_PATH, DatasetPlanner
from .policy import decide
from .tools import validate_tool_call


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="ULTRON 2.7 text-first assistant")
    parser.add_argument("utterance", nargs="+", help="Command to plan and execute")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH, help="Dataset JSONL path")
    parser.add_argument("--execute", action="store_true", help="Run executor instead of dry-run")
    parser.add_argument("--yes", action="store_true", help="Confirm commands that require confirmation")
    parser.add_argument("--audit-log", type=Path, default=Path(".ultron/audit.jsonl"), help="Audit log path")
    args = parser.parse_args(argv)

    utterance = " ".join(args.utterance)
    planner = DatasetPlanner.from_jsonl(args.dataset)
    plan = planner.plan(utterance)
    validation = validate_tool_call(plan.tool_call)
    decision = decide(plan, validation, confirmed=args.yes)

    executor = Executor(dry_run=not args.execute)
    if decision.action == "allow":
        result = executor.execute(plan.tool_call)
    elif decision.action == "confirm":
        result = {
            "status": "confirmation_required",
            "message": decision.reason,
        }
    else:
        result = {
            "status": "blocked",
            "message": decision.reason,
        }

    payload: dict[str, Any] = {
        "utterance": utterance,
        "intent": plan.intent,
        "source": plan.source,
        "confidence": plan.confidence,
        "tool_call": asdict(plan.tool_call),
        "validation": asdict(validation),
        "policy": asdict(decision),
        "result": asdict(result) if hasattr(result, "__dataclass_fields__") else result,
    }
    append_audit_record(payload, args.audit_log)
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

