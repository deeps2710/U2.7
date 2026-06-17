from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from ultron27.brain import UltronBrain
from ultron27.knowledge import KnowledgeBase
from ultron27.runtime import RuntimeSettings, UltronAssistant
from ultron27.skills import SkillRegistry
from ultron27.voice import MockSTT, MockTTS, VoiceSession
from ultron27.web_server import WebState


def build_demo_state() -> WebState:
    workspace = ROOT / ".ultron" / "demo_workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    settings = RuntimeSettings(
        dataset_path=ROOT / "data" / "jarvis_dataset_v2" / "jarvis_laptop_commands_synthetic_v2.jsonl",
        audit_log=workspace / ".ultron" / "audit.jsonl",
        workspace=workspace,
        dry_run=False,
        safe_roots=(workspace,),
        app_aliases=None,
        screenshot_dir=workspace / ".ultron" / "screenshots",
        planner_mode="rules",
        llm_model="unused",
        llm_endpoint="http://localhost:11434",
        llm_timeout_seconds=1.0,
        write_audit=True,
    )
    assistant = UltronAssistant(settings)
    knowledge = KnowledgeBase(workspace / ".ultron" / "knowledge" / "index.json", workspace=workspace, safe_roots=(workspace,))
    return WebState(
        UltronBrain(assistant, memory_path=workspace / ".ultron" / "memory.json"),
        knowledge=knowledge,
        skills=SkillRegistry.with_builtins(assistant, knowledge),
        voice=VoiceSession(stt=MockSTT("ULTRON, create a note called demo and write that mock voice mode is working."), tts=MockTTS()),
    )


def main() -> int:
    state = build_demo_state()
    print("ULTRON 2.7 Phase 13 demo")

    typed = state.command("find files demo")
    print("\nTyped command demo:")
    print(_summary(typed))

    note = state.command("Create a note called beta demo and add that setup is working.")
    print("\nNote creation demo:")
    print(_summary(note))

    risky = state.command("open terminal")
    print("\nHigh-risk confirmation demo:")
    print(_summary(risky))

    voice = state.voice_transcribe({})
    print("\nMock voice demo:")
    print(_summary(voice))

    print("\nDemo workspace:")
    print(state.brain.assistant.settings.workspace)
    return 0


def _summary(payload: dict[str, object]) -> str:
    slim = {
        "status": payload.get("status"),
        "visual_state": payload.get("visual_state"),
        "subtitle": payload.get("subtitle") or payload.get("last_subtitle"),
        "task_status": (payload.get("task") or {}).get("status") if isinstance(payload.get("task"), dict) else None,
    }
    return json.dumps(slim, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    raise SystemExit(main())
