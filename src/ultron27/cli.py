from __future__ import annotations

import argparse
import json
from pathlib import Path

from .brain import UltronBrain, format_memory, format_task_plan
from .config import load_config
from .console import format_assistant_response, run_console
from .runtime import RuntimeSettings, UltronAssistant
from . import __version__


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="ULTRON 2.7 text-first assistant",
        epilog='Examples: ultron "set volume to 40 percent" | ultron "open notepad" | ultron "delete project_report.txt" --yes',
    )
    parser.add_argument("utterance", nargs="*", help="Command to plan and execute")
    parser.add_argument("--config", type=Path, default=None, help="JSON config path")
    parser.add_argument("--dataset", type=Path, default=None, help="Dataset JSONL path")
    parser.add_argument("--audit-log", type=Path, default=None, help="Audit log path")
    parser.add_argument("--workspace", type=Path, default=None, help="Workspace used by file/note tools")
    parser.add_argument("--execute", action="store_true", help="Run safe implemented tools instead of dry-run")
    parser.add_argument("--dry-run", action="store_true", help="Preview tool execution even if config disables dry-run")
    parser.add_argument("--interactive", "-i", action="store_true", help="Start an interactive assistant console")
    parser.add_argument("--planner-mode", choices=["rules", "hybrid", "llm"], default=None, help="Planner routing mode")
    parser.add_argument("--llm-model", default=None, help="Ollama model name for LLM planning")
    parser.add_argument("--llm-endpoint", default=None, help="Ollama endpoint for LLM planning")
    parser.add_argument("--text", action="store_true", help="Print a concise human-readable response instead of JSON")
    parser.add_argument("--yes", action="store_true", help="Confirm commands that require confirmation")
    parser.add_argument("--no-audit", action="store_true", help="Print the response without writing an audit record")
    parser.add_argument("--version", action="version", version=f"ultron27 {__version__}")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except (FileNotFoundError, ValueError) as exc:
        parser.error(str(exc))

    dry_run = config.dry_run
    if args.execute:
        dry_run = False
    if args.dry_run:
        dry_run = True

    try:
        settings = RuntimeSettings.from_config(
            config,
            dataset_path=args.dataset,
            audit_log=args.audit_log,
            workspace=args.workspace,
            dry_run=dry_run,
            execute_requested=args.execute,
            write_audit=not args.no_audit,
            planner_mode=args.planner_mode,
            llm_model=args.llm_model,
            llm_endpoint=args.llm_endpoint,
        )
        assistant = UltronAssistant(settings)
    except FileNotFoundError as exc:
        parser.error(str(exc))
    brain = UltronBrain(assistant)

    if args.interactive:
        if args.utterance:
            payload = assistant.handle(" ".join(args.utterance), confirmed=args.yes)
            print(format_assistant_response(payload))
        run_console(assistant, brain=brain)
        return

    if not args.utterance:
        parser.error("utterance is required unless --interactive is used")

    command = " ".join(args.utterance)
    lowered = command.lower()
    if lowered.startswith("/plan "):
        task = brain.plan(command[6:].strip())
        print(format_task_plan(task) if args.text else json.dumps(task.to_dict(), indent=2, ensure_ascii=True))
        return
    if lowered.startswith("/do "):
        task = brain.execute(command[4:].strip(), confirmed=args.yes)
        print(format_task_plan(task) if args.text else json.dumps(task.to_dict(), indent=2, ensure_ascii=True))
        return
    if lowered == "/memory":
        items = brain.memory.list()
        print(format_memory(items) if args.text else json.dumps(items, indent=2, ensure_ascii=True))
        return
    if lowered.startswith("/forget "):
        removed = brain.memory.forget(command[8:].strip())
        payload = {"forgot": removed}
        print(f"Forgot {removed} memory item(s)." if args.text else json.dumps(payload, indent=2, ensure_ascii=True))
        return

    payload = assistant.handle(command, confirmed=args.yes)
    if args.text:
        print(format_assistant_response(payload))
    else:
        print(json.dumps(payload, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()

