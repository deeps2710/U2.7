from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .audit import append_audit_record
from .config import load_config
from .executor import Executor
from .llm import LLMPlannerError, make_ollama_planner
from .planner import DEFAULT_DATASET_PATH, DatasetPlanner
from .policy import decide
from .tools import validate_tool_call
from . import __version__


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="ULTRON 2.7 text-first assistant",
        epilog='Examples: ultron "set volume to 40 percent" | ultron "open notepad" | ultron "delete project_report.txt" --yes',
    )
    parser.add_argument("utterance", nargs="+", help="Command to plan and execute")
    parser.add_argument("--config", type=Path, default=None, help="JSON config path")
    parser.add_argument("--dataset", type=Path, default=None, help="Dataset JSONL path")
    parser.add_argument("--audit-log", type=Path, default=None, help="Audit log path")
    parser.add_argument("--workspace", type=Path, default=None, help="Workspace used by file/note tools")
    parser.add_argument("--execute", action="store_true", help="Run safe implemented tools instead of dry-run")
    parser.add_argument("--dry-run", action="store_true", help="Preview tool execution even if config disables dry-run")
    parser.add_argument("--planner-mode", choices=["rules", "hybrid", "llm"], default=None, help="Planner routing mode")
    parser.add_argument("--llm-model", default=None, help="Ollama model name for LLM planning")
    parser.add_argument("--llm-endpoint", default=None, help="Ollama endpoint for LLM planning")
    parser.add_argument("--yes", action="store_true", help="Confirm commands that require confirmation")
    parser.add_argument("--no-audit", action="store_true", help="Print the response without writing an audit record")
    parser.add_argument("--version", action="version", version=f"ultron27 {__version__}")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except (FileNotFoundError, ValueError) as exc:
        parser.error(str(exc))

    dataset_path = args.dataset or config.dataset_path
    audit_log = args.audit_log or config.audit_log
    workspace = args.workspace or config.workspace
    dry_run = config.dry_run
    if args.execute:
        dry_run = False
    if args.dry_run:
        dry_run = True

    if not dataset_path.exists():
        parser.error(f"Dataset file not found: {dataset_path}")

    utterance = " ".join(args.utterance)
    planner = DatasetPlanner.from_jsonl(dataset_path)
    planner_mode = args.planner_mode or config.planner_mode
    llm_trace: dict[str, Any] = {"attempted": False, "error": None}
    plan = planner.plan(utterance)
    if planner_mode in {"hybrid", "llm"} and (planner_mode == "llm" or plan.source == "fallback"):
        llm_trace["attempted"] = True
        try:
            llm = make_ollama_planner(
                endpoint=args.llm_endpoint or config.llm_endpoint,
                model=args.llm_model or config.llm_model,
                timeout=config.llm_timeout_seconds,
            )
            plan = llm.plan(utterance)
        except LLMPlannerError as exc:
            llm_trace["error"] = str(exc)
            if planner_mode == "llm":
                plan = planner.plan(utterance)
    validation = validate_tool_call(plan.tool_call)
    decision = decide(plan, validation, confirmed=args.yes)

    executor = Executor(
        dry_run=dry_run,
        workspace=workspace,
        safe_roots=config.safe_roots,
        app_aliases=config.app_aliases or {},
        screenshot_dir=config.screenshot_dir,
    )
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
        "runtime": {
            "dry_run": dry_run,
            "execute_requested": args.execute,
            "confirmed": args.yes,
            "dataset_path": str(dataset_path),
            "workspace": str(workspace),
            "safe_roots": [str(root) for root in config.safe_roots],
            "planner_mode": planner_mode,
            "llm": llm_trace,
            "python": sys.version.split()[0],
            "platform": sys.platform,
        },
    }
    if not args.no_audit:
        append_audit_record(payload, audit_log)
    print(json.dumps(payload, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()

