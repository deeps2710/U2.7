from __future__ import annotations

import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .audit import append_audit_record
from .config import UltronConfig
from .executor import Executor
from .llm import LLMPlannerError, make_ollama_planner
from .planner import DatasetPlanner
from .policy import decide
from .tools import validate_tool_call


@dataclass(frozen=True)
class RuntimeSettings:
    dataset_path: Path
    audit_log: Path
    workspace: Path
    dry_run: bool
    safe_roots: tuple[Path, ...]
    app_aliases: dict[str, str] | None
    screenshot_dir: Path
    planner_mode: str
    llm_model: str
    llm_endpoint: str
    llm_timeout_seconds: float
    execute_requested: bool = False
    write_audit: bool = True

    @classmethod
    def from_config(
        cls,
        config: UltronConfig,
        *,
        dataset_path: Path | None = None,
        audit_log: Path | None = None,
        workspace: Path | None = None,
        dry_run: bool | None = None,
        execute_requested: bool = False,
        write_audit: bool = True,
        planner_mode: str | None = None,
        llm_model: str | None = None,
        llm_endpoint: str | None = None,
    ) -> "RuntimeSettings":
        return cls(
            dataset_path=dataset_path or config.dataset_path,
            audit_log=audit_log or config.audit_log,
            workspace=workspace or config.workspace,
            dry_run=config.dry_run if dry_run is None else dry_run,
            safe_roots=config.safe_roots,
            app_aliases=config.app_aliases,
            screenshot_dir=config.screenshot_dir,
            planner_mode=planner_mode or config.planner_mode,
            llm_model=llm_model or config.llm_model,
            llm_endpoint=llm_endpoint or config.llm_endpoint,
            llm_timeout_seconds=config.llm_timeout_seconds,
            execute_requested=execute_requested,
            write_audit=write_audit,
        )


class UltronAssistant:
    def __init__(self, settings: RuntimeSettings):
        if not settings.dataset_path.exists():
            raise FileNotFoundError(f"Dataset file not found: {settings.dataset_path}")
        self.settings = settings
        self.planner = DatasetPlanner.from_jsonl(settings.dataset_path)

    def handle(self, utterance: str, *, confirmed: bool = False) -> dict[str, Any]:
        plan = self.planner.plan(utterance)
        llm_trace: dict[str, Any] = {"attempted": False, "error": None}
        if self.settings.planner_mode in {"hybrid", "llm"} and (
            self.settings.planner_mode == "llm" or plan.source == "fallback"
        ):
            llm_trace["attempted"] = True
            try:
                llm = make_ollama_planner(
                    endpoint=self.settings.llm_endpoint,
                    model=self.settings.llm_model,
                    timeout=self.settings.llm_timeout_seconds,
                )
                plan = llm.plan(utterance)
            except LLMPlannerError as exc:
                llm_trace["error"] = str(exc)
                if self.settings.planner_mode == "llm":
                    plan = self.planner.plan(utterance)

        validation = validate_tool_call(plan.tool_call)
        decision = decide(plan, validation, confirmed=confirmed)
        executor = Executor(
            dry_run=self.settings.dry_run,
            workspace=self.settings.workspace,
            safe_roots=self.settings.safe_roots,
            app_aliases=self.settings.app_aliases or {},
            screenshot_dir=self.settings.screenshot_dir,
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
                "dry_run": self.settings.dry_run,
                "execute_requested": self.settings.execute_requested,
                "confirmed": confirmed,
                "dataset_path": str(self.settings.dataset_path),
                "workspace": str(self.settings.workspace),
                "safe_roots": [str(root) for root in self.settings.safe_roots],
                "planner_mode": self.settings.planner_mode,
                "llm": llm_trace,
                "python": sys.version.split()[0],
                "platform": sys.platform,
            },
        }
        if self.settings.write_audit:
            append_audit_record(payload, self.settings.audit_log)
        return payload
