from __future__ import annotations

import importlib.util
import platform
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any


PHASE13_VERSION = "UltronPhase13/1.0"


def build_diagnostics(state: Any) -> dict[str, Any]:
    """Build a non-secret readiness snapshot for the local prototype UI."""

    assistant = state.brain.assistant
    settings = assistant.settings
    memory_path = state.brain.memory.path
    audit_log = settings.audit_log
    knowledge_path = state.knowledge.index_path if state.knowledge else None
    provider_status = state.voice.providers_status()
    gate_status = state.voice.gate_status()
    recent_errors = _recent_errors(settings, provider_status, state.voice.status.last_error)

    payload = {
        "status": "ok",
        "version": PHASE13_VERSION,
        "backend": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "cwd": str(Path.cwd()),
            "package": "ultron27",
        },
        "brain": {
            "status": "ready",
            "planner_mode": settings.planner_mode,
            "dataset": _path_status(settings.dataset_path),
            "memory": _path_status(memory_path),
            "session_memory_keys": sorted(state.brain.session_memory.keys()),
        },
        "runtime": {
            "dry_run": settings.dry_run,
            "execute_requested": settings.execute_requested,
            "audit_enabled": settings.write_audit,
            "workspace": _path_status(settings.workspace),
            "safe_roots": [_path_status(root) for root in settings.safe_roots],
            "audit_log": _path_status(audit_log),
            "screenshot_dir": _path_status(settings.screenshot_dir),
        },
        "voice": {
            "providers": provider_status,
            "wake": gate_status,
            "status": state.voice.status.to_dict(),
        },
        "skills": {
            "count": len(state.skills.specs) if state.skills else 0,
            "names": sorted(state.skills.specs) if state.skills else [],
        },
        "knowledge": {
            "index": _path_status(knowledge_path) if knowledge_path else None,
            "sources": state.knowledge.sources() if state.knowledge else [],
        },
        "dependencies": dependency_status(),
        "recent_errors": recent_errors,
        "readiness": "ready" if not recent_errors else "attention_needed",
    }
    return _jsonable(payload)


def dependency_status() -> dict[str, Any]:
    packages = {
        "docx": "python-docx for DOCX reports and knowledge ingestion",
        "reportlab": "ReportLab for PDF reports",
        "pypdf": "pypdf for PDF text checks and knowledge ingestion",
        "PIL": "Pillow for screenshots and PDF preview images",
        "pytest": "pytest for optional test runner support",
        "faster_whisper": "optional local STT",
        "pyttsx3": "optional local Windows TTS",
    }
    return {
        name: {
            "available": importlib.util.find_spec(name) is not None,
            "purpose": purpose,
        }
        for name, purpose in packages.items()
    }


def _path_status(path: Path | str | None) -> dict[str, Any]:
    if path is None:
        return {"path": None, "exists": False, "is_file": False, "is_dir": False}
    candidate = Path(path)
    return {
        "path": str(candidate),
        "exists": candidate.exists(),
        "is_file": candidate.is_file(),
        "is_dir": candidate.is_dir(),
        "parent_exists": candidate.parent.exists(),
    }


def _recent_errors(settings: Any, provider_status: dict[str, Any], voice_error: str | None) -> list[str]:
    errors: list[str] = []
    if voice_error:
        errors.append(voice_error)
    if not settings.dataset_path.exists():
        errors.append(f"Dataset missing: {settings.dataset_path}")
    if not settings.workspace.exists():
        errors.append(f"Workspace missing: {settings.workspace}")
    for root in settings.safe_roots:
        if not Path(root).expanduser().exists():
            errors.append(f"Safe root missing: {root}")
    for key in ("stt", "tts"):
        health = provider_status.get("providers", {}).get(key, {})
        if health and not health.get("available", True):
            errors.append(str(health.get("detail", f"{key.upper()} provider unavailable")))
    return errors


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "value"):
        return value.value
    return value
