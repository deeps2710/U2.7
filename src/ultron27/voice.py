from __future__ import annotations

import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol


CONFIRMATION_PHRASES = {"yes confirm", "confirm", "confirmed", "yes proceed", "proceed"}


class STTProvider(Protocol):
    name: str

    def transcribe(self, payload: dict[str, Any]) -> "STTResult":
        ...


class TTSProvider(Protocol):
    name: str

    def speak(self, text: str, *, voice: str = "ULTRON") -> dict[str, Any]:
        ...

    def stop(self) -> dict[str, Any]:
        ...


@dataclass
class STTResult:
    text: str
    confidence: float = 1.0
    provider: str = "text_payload"
    empty: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VoiceStatus:
    microphone_enabled: bool = False
    listening: bool = False
    muted: bool = False
    speaking: bool = False
    push_to_talk: bool = True
    stt_provider: str = "text_payload"
    tts_provider: str = "browser_speech_synthesis"
    pending_confirmation_goal: str | None = None
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TranscriptRecord:
    transcript_id: str
    user_said: str
    ultron_understood: str
    tool_selected: str | None
    action_result: str | None
    spoken_response: str
    needs_confirmation: bool = False
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TextPayloadSTT:
    name = "text_payload"

    def transcribe(self, payload: dict[str, Any]) -> STTResult:
        text = str(payload.get("transcript") or payload.get("text") or "").strip()
        normalized = strip_wake_word(text)
        return STTResult(text=normalized, confidence=1.0 if normalized else 0.0, provider=self.name, empty=not bool(normalized))


class BrowserSpeechTTS:
    name = "browser_speech_synthesis"

    def speak(self, text: str, *, voice: str = "ULTRON") -> dict[str, Any]:
        if not text.strip():
            return {"status": "empty", "provider": self.name, "voice": voice}
        return {
            "status": "delegated",
            "provider": self.name,
            "voice": voice,
            "message": "Speech synthesis is delegated to the browser client.",
            "text": text,
        }

    def stop(self) -> dict[str, Any]:
        return {"status": "stopped", "provider": self.name}


class MockTTS:
    name = "mock_tts"

    def __init__(self) -> None:
        self.spoken: list[str] = []
        self.stopped = False

    def speak(self, text: str, *, voice: str = "ULTRON") -> dict[str, Any]:
        self.spoken.append(text)
        return {"status": "spoken", "provider": self.name, "voice": voice, "text": text}

    def stop(self) -> dict[str, Any]:
        self.stopped = True
        return {"status": "stopped", "provider": self.name}


class VoiceSession:
    def __init__(self, stt: STTProvider | None = None, tts: TTSProvider | None = None, *, history_limit: int = 20):
        self.stt = stt or TextPayloadSTT()
        self.tts = tts or BrowserSpeechTTS()
        self.status = VoiceStatus(stt_provider=self.stt.name, tts_provider=self.tts.name)
        self.history: list[TranscriptRecord] = []
        self.history_limit = history_limit

    def start(self, *, push_to_talk: bool | None = None) -> dict[str, Any]:
        if push_to_talk is not None:
            self.status.push_to_talk = bool(push_to_talk)
        self.status.microphone_enabled = True
        self.status.listening = True
        self.status.last_error = None
        return self.snapshot({"status": "ok"})

    def stop(self) -> dict[str, Any]:
        self.status.microphone_enabled = False
        self.status.listening = False
        return self.snapshot({"status": "ok"})

    def set_muted(self, muted: bool) -> dict[str, Any]:
        self.status.muted = bool(muted)
        if muted:
            self.status.speaking = False
        return self.snapshot({"status": "ok"})

    def transcribe_and_run(self, payload: dict[str, Any], command_runner) -> dict[str, Any]:
        self.status.listening = False
        result = self.stt.transcribe(payload)
        if result.empty:
            self.status.last_error = "No speech was detected."
            return self.snapshot({"status": "empty", "transcript": result.to_dict(), "message": self.status.last_error})

        confirmed = False
        goal = result.text
        normalized = normalize_confirmation(result.text)
        if normalized in CONFIRMATION_PHRASES and self.status.pending_confirmation_goal:
            confirmed = True
            goal = self.status.pending_confirmation_goal

        command_payload = command_runner(goal, confirmed=confirmed)
        task = command_payload.get("task") if isinstance(command_payload, dict) else None
        spoken_response = response_for_task(task, command_payload.get("subtitle") if isinstance(command_payload, dict) else None)
        needs_confirmation = bool(task and task.get("status") == "waiting_for_confirmation")
        if needs_confirmation:
            self.status.pending_confirmation_goal = goal
            spoken_response = "I need explicit confirmation before doing that. Say yes confirm or click Confirm."
        else:
            self.status.pending_confirmation_goal = None

        record = TranscriptRecord(
            transcript_id=str(uuid.uuid4()),
            user_said=str(payload.get("transcript") or payload.get("text") or result.text),
            ultron_understood=goal,
            tool_selected=first_tool(task),
            action_result=first_result(task),
            spoken_response=spoken_response,
            needs_confirmation=needs_confirmation,
        )
        self._remember(record)
        self.status.speaking = not self.status.muted
        self.status.last_error = None
        return self.snapshot(
            {
                "status": "ok",
                "transcript": result.to_dict(),
                "confirmed": confirmed,
                "task": task,
                "spoken_response": spoken_response,
                "needs_confirmation": needs_confirmation,
                "record": record.to_dict(),
            }
        )

    def speak(self, text: str) -> dict[str, Any]:
        if self.status.muted:
            self.status.speaking = False
            return self.snapshot({"status": "muted", "message": "Voice output is muted.", "text": text})
        payload = self.tts.speak(text, voice="ULTRON")
        self.status.speaking = payload.get("status") not in {"empty", "error"}
        return self.snapshot({"status": "ok", "speech": payload})

    def stop_speaking(self) -> dict[str, Any]:
        payload = self.tts.stop()
        self.status.speaking = False
        return self.snapshot({"status": "ok", "speech": payload})

    def snapshot(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {
            "voice": self.status.to_dict(),
            "history": [item.to_dict() for item in self.history],
        }
        if extra:
            payload.update(extra)
        return payload

    def _remember(self, record: TranscriptRecord) -> None:
        self.history.append(record)
        if len(self.history) > self.history_limit:
            self.history = self.history[-self.history_limit :]


def strip_wake_word(text: str) -> str:
    value = " ".join(text.strip().split())
    value = re.sub(r"^(?:hey\s+)?ultron[\s,.:;-]+", "", value, flags=re.IGNORECASE)
    return value.strip()


def normalize_confirmation(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def response_for_task(task: dict[str, Any] | None, fallback: str | None = None) -> str:
    if not task:
        return fallback or "I could not process that command."
    if task.get("summary"):
        return str(task["summary"])
    status = task.get("status", "updated")
    return f"Task {status}."


def first_tool(task: dict[str, Any] | None) -> str | None:
    if not task:
        return None
    steps = task.get("steps")
    if not isinstance(steps, list) or not steps:
        return None
    tool = steps[0].get("tool_call") if isinstance(steps[0], dict) else None
    return tool.get("name") if isinstance(tool, dict) else None


def first_result(task: dict[str, Any] | None) -> str | None:
    if not task:
        return None
    steps = task.get("steps")
    if not isinstance(steps, list) or not steps:
        return None
    result = steps[-1].get("result") if isinstance(steps[-1], dict) else None
    if not isinstance(result, dict):
        return None
    status = result.get("status")
    message = result.get("message")
    if status and message:
        return f"{status}: {message}"
    return str(status or message or "")
