from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .wake import (
    DEFAULT_WAKE_PHRASES,
    EnergyVADProvider,
    TextWakeWordProvider,
    VADProvider,
    WakeGateConfig,
    WakeStatus,
    WakeWordProvider,
    build_vad_provider,
    build_wake_provider,
    gate_providers_status,
    strip_wake_phrase,
)


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


@dataclass(frozen=True)
class VoiceProviderConfig:
    stt_provider: str = "text_payload"
    tts_provider: str = "browser_speech_synthesis"
    stt_model_path: Path | None = None
    tts_model_path: Path | None = None
    tts_voice_path: Path | None = None
    device: str = "cpu"
    voice_identity: str = "ULTRON"
    rate: float = 0.92
    pitch: float = 0.72
    volume: float = 0.95

    @classmethod
    def from_config(cls, config: Any) -> "VoiceProviderConfig":
        return cls(
            stt_provider=str(getattr(config, "voice_stt_provider", cls.stt_provider)).lower(),
            tts_provider=str(getattr(config, "voice_tts_provider", cls.tts_provider)).lower(),
            stt_model_path=getattr(config, "voice_stt_model_path", None),
            tts_model_path=getattr(config, "voice_tts_model_path", None),
            tts_voice_path=getattr(config, "voice_tts_voice_path", None),
            device=str(getattr(config, "voice_device", cls.device)).lower(),
            voice_identity=str(getattr(config, "voice_identity", cls.voice_identity)),
            rate=float(getattr(config, "voice_rate", cls.rate)),
            pitch=float(getattr(config, "voice_pitch", cls.pitch)),
            volume=float(getattr(config, "voice_volume", cls.volume)),
        )


@dataclass
class ProviderHealth:
    kind: str
    name: str
    configured: bool
    active: bool
    available: bool
    detail: str
    fallback_to: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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
    configured_stt_provider: str = "text_payload"
    configured_tts_provider: str = "browser_speech_synthesis"
    voice_identity: str = "ULTRON"
    voice_rate: float = 0.92
    voice_pitch: float = 0.72
    voice_volume: float = 0.95
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

    def health(self) -> ProviderHealth:
        return ProviderHealth("stt", self.name, configured=True, active=True, available=True, detail="Accepts transcript/text payloads.")


class BrowserTranscriptSTT(TextPayloadSTT):
    name = "browser"

    def health(self) -> ProviderHealth:
        return ProviderHealth("stt", self.name, configured=True, active=True, available=True, detail="Uses browser speech recognition transcript payloads.")


class MockSTT(TextPayloadSTT):
    name = "mock_stt"

    def __init__(self, transcript: str = "create note mock voice") -> None:
        self.transcript = transcript

    def transcribe(self, payload: dict[str, Any]) -> STTResult:
        if payload.get("transcript") or payload.get("text"):
            return super().transcribe(payload)
        normalized = strip_wake_word(self.transcript)
        return STTResult(text=normalized, confidence=1.0, provider=self.name, empty=not bool(normalized))

    def health(self) -> ProviderHealth:
        return ProviderHealth("stt", self.name, configured=True, active=True, available=True, detail="Deterministic mock STT provider for tests and demos.")


class FasterWhisperSTT(TextPayloadSTT):
    name = "faster_whisper"

    def __init__(self, model_path: Path | None, *, device: str = "cpu") -> None:
        self.model_path = model_path
        self.device = device

    def transcribe(self, payload: dict[str, Any]) -> STTResult:
        if payload.get("transcript") or payload.get("text"):
            result = super().transcribe(payload)
            result.provider = self.name
            return result
        audio_path = _payload_audio_path(payload)
        health = self.health()
        if not audio_path or not health.available:
            return STTResult(text="", confidence=0.0, provider=self.name, empty=True)
        try:
            from faster_whisper import WhisperModel  # type: ignore[import-not-found]

            model = WhisperModel(str(self.model_path), device=self.device)
            segments, info = model.transcribe(str(audio_path))
            text = " ".join(segment.text.strip() for segment in segments).strip()
            confidence = float(getattr(info, "language_probability", 1.0))
            return STTResult(text=strip_wake_word(text), confidence=confidence, provider=self.name, empty=not bool(text))
        except Exception:
            return STTResult(text="", confidence=0.0, provider=self.name, empty=True)

    def health(self) -> ProviderHealth:
        if importlib.util.find_spec("faster_whisper") is None:
            return ProviderHealth("stt", self.name, configured=True, active=False, available=False, detail="Python package faster-whisper is not installed.", fallback_to="browser")
        if self.model_path is None:
            return ProviderHealth("stt", self.name, configured=True, active=False, available=False, detail="No faster-whisper model path is configured.", fallback_to="browser")
        if not self.model_path.exists():
            return ProviderHealth("stt", self.name, configured=True, active=False, available=False, detail=f"Model path not found: {self.model_path}", fallback_to="browser")
        return ProviderHealth("stt", self.name, configured=True, active=True, available=True, detail=f"Ready on {self.device}.")


class WhisperCppSTT(TextPayloadSTT):
    name = "whisper_cpp"

    def __init__(self, model_path: Path | None, *, device: str = "cpu") -> None:
        self.model_path = model_path
        self.device = device
        self.executable = shutil.which("whisper-cli") or shutil.which("main") or shutil.which("whisper.cpp")

    def transcribe(self, payload: dict[str, Any]) -> STTResult:
        if payload.get("transcript") or payload.get("text"):
            result = super().transcribe(payload)
            result.provider = self.name
            return result
        audio_path = _payload_audio_path(payload)
        health = self.health()
        if not audio_path or not health.available or not self.executable:
            return STTResult(text="", confidence=0.0, provider=self.name, empty=True)
        try:
            process = subprocess.run(
                [self.executable, "-m", str(self.model_path), "-f", str(audio_path), "-nt"],
                check=False,
                capture_output=True,
                text=True,
                timeout=45,
            )
        except Exception:
            return STTResult(text="", confidence=0.0, provider=self.name, empty=True)
        output = process.stdout.strip()
        return STTResult(text=strip_wake_word(output), confidence=1.0 if output else 0.0, provider=self.name, empty=not bool(output))

    def health(self) -> ProviderHealth:
        if not self.executable:
            return ProviderHealth("stt", self.name, configured=True, active=False, available=False, detail="whisper.cpp executable was not found on PATH.", fallback_to="browser")
        if self.model_path is None:
            return ProviderHealth("stt", self.name, configured=True, active=False, available=False, detail="No whisper.cpp model path is configured.", fallback_to="browser")
        if not self.model_path.exists():
            return ProviderHealth("stt", self.name, configured=True, active=False, available=False, detail=f"Model path not found: {self.model_path}", fallback_to="browser")
        return ProviderHealth("stt", self.name, configured=True, active=True, available=True, detail=f"Ready on {self.device}.")


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

    def health(self) -> ProviderHealth:
        return ProviderHealth("tts", self.name, configured=True, active=True, available=True, detail="Browser SpeechSynthesis handles playback.")


class PiperTTS:
    name = "piper"

    def __init__(self, model_path: Path | None, *, voice_path: Path | None = None, rate: float = 0.92, pitch: float = 0.72, volume: float = 0.95) -> None:
        self.model_path = model_path
        self.voice_path = voice_path
        self.rate = rate
        self.pitch = pitch
        self.volume = volume
        self.executable = shutil.which("piper")

    def speak(self, text: str, *, voice: str = "ULTRON") -> dict[str, Any]:
        if not text.strip():
            return {"status": "empty", "provider": self.name, "voice": voice}
        health = self.health()
        if not health.available or not self.executable or not self.model_path:
            return {"status": "unavailable", "provider": self.name, "voice": voice, "message": health.detail, "text": text}
        output = tempfile.NamedTemporaryFile(prefix="ultron-piper-", suffix=".wav", delete=False)
        output.close()
        command = [self.executable, "--model", str(self.model_path), "--output_file", output.name]
        if self.voice_path:
            command.extend(["--config", str(self.voice_path)])
        try:
            process = subprocess.run(command, input=text, check=False, capture_output=True, text=True, timeout=30)
        except Exception as exc:
            return {"status": "error", "provider": self.name, "voice": voice, "message": str(exc), "text": text}
        if process.returncode != 0:
            return {"status": "error", "provider": self.name, "voice": voice, "message": process.stderr.strip(), "text": text}
        return {"status": "audio_file", "provider": self.name, "voice": voice, "audio_path": output.name, "text": text}

    def stop(self) -> dict[str, Any]:
        return {"status": "stopped", "provider": self.name}

    def health(self) -> ProviderHealth:
        if not self.executable:
            return ProviderHealth("tts", self.name, configured=True, active=False, available=False, detail="Piper executable was not found on PATH.", fallback_to="browser_speech_synthesis")
        if self.model_path is None:
            return ProviderHealth("tts", self.name, configured=True, active=False, available=False, detail="No Piper model path is configured.", fallback_to="browser_speech_synthesis")
        if not self.model_path.exists():
            return ProviderHealth("tts", self.name, configured=True, active=False, available=False, detail=f"Model path not found: {self.model_path}", fallback_to="browser_speech_synthesis")
        if self.voice_path is not None and not self.voice_path.exists():
            return ProviderHealth("tts", self.name, configured=True, active=False, available=False, detail=f"Piper voice config not found: {self.voice_path}", fallback_to="browser_speech_synthesis")
        return ProviderHealth("tts", self.name, configured=True, active=True, available=True, detail="Piper is ready for local synthesis.")


class Pyttsx3TTS:
    name = "pyttsx3"

    def __init__(self, *, rate: float = 0.92, pitch: float = 0.72, volume: float = 0.95) -> None:
        self.rate = rate
        self.pitch = pitch
        self.volume = volume

    def speak(self, text: str, *, voice: str = "ULTRON") -> dict[str, Any]:
        if not text.strip():
            return {"status": "empty", "provider": self.name, "voice": voice}
        health = self.health()
        if not health.available:
            return {"status": "unavailable", "provider": self.name, "voice": voice, "message": health.detail, "text": text}
        try:
            import pyttsx3  # type: ignore[import-not-found]

            engine = pyttsx3.init()
            engine.setProperty("rate", max(80, min(260, int(185 * self.rate))))
            engine.setProperty("volume", max(0.0, min(1.0, self.volume)))
            engine.say(text)
            engine.runAndWait()
        except Exception as exc:
            return {"status": "error", "provider": self.name, "voice": voice, "message": str(exc), "text": text}
        return {"status": "spoken", "provider": self.name, "voice": voice, "text": text, "pitch": self.pitch}

    def stop(self) -> dict[str, Any]:
        return {"status": "stopped", "provider": self.name}

    def health(self) -> ProviderHealth:
        if importlib.util.find_spec("pyttsx3") is None:
            return ProviderHealth("tts", self.name, configured=True, active=False, available=False, detail="Python package pyttsx3 is not installed.", fallback_to="browser_speech_synthesis")
        return ProviderHealth("tts", self.name, configured=True, active=True, available=True, detail="pyttsx3 is importable for local speech synthesis.")


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

    def health(self) -> ProviderHealth:
        return ProviderHealth("tts", self.name, configured=True, active=True, available=True, detail="Deterministic mock TTS provider for tests.")


class VoiceSession:
    def __init__(
        self,
        stt: STTProvider | None = None,
        tts: TTSProvider | None = None,
        *,
        configured_stt: STTProvider | None = None,
        configured_tts: TTSProvider | None = None,
        wake: WakeWordProvider | None = None,
        vad: VADProvider | None = None,
        configured_wake: WakeWordProvider | None = None,
        configured_vad: VADProvider | None = None,
        provider_config: VoiceProviderConfig | None = None,
        wake_config: WakeGateConfig | None = None,
        history_limit: int = 20,
    ):
        self.provider_config = provider_config or VoiceProviderConfig()
        self.wake_config = wake_config or WakeGateConfig()
        self.stt = stt or TextPayloadSTT()
        self.tts = tts or BrowserSpeechTTS()
        self.wake = wake or TextWakeWordProvider(self.wake_config.wake_phrases)
        self.vad = vad or EnergyVADProvider(self.wake_config.vad_energy_threshold)
        self.configured_stt = configured_stt or self.stt
        self.configured_tts = configured_tts or self.tts
        self.configured_wake = configured_wake or self.wake
        self.configured_vad = configured_vad or self.vad
        self.status = VoiceStatus(
            stt_provider=self.stt.name,
            tts_provider=self.tts.name,
            configured_stt_provider=self.configured_stt.name,
            configured_tts_provider=self.configured_tts.name,
            voice_identity=self.provider_config.voice_identity,
            voice_rate=self.provider_config.rate,
            voice_pitch=self.provider_config.pitch,
            voice_volume=self.provider_config.volume,
        )
        self.wake_status = WakeStatus(
            wake_provider=self.wake.name,
            vad_provider=self.vad.name,
            wake_phrases=self.wake_config.wake_phrases or DEFAULT_WAKE_PHRASES,
        )
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
        if self.wake_status.always_listening:
            self.stop_wake()
        return self.snapshot({"status": "ok"})

    def set_muted(self, muted: bool) -> dict[str, Any]:
        self.status.muted = bool(muted)
        if muted:
            self.status.speaking = False
        return self.snapshot({"status": "ok"})

    def transcribe_and_run(self, payload: dict[str, Any], command_runner) -> dict[str, Any]:
        self.status.listening = False
        self.wake_status.mode = "transcribing" if self.wake_status.always_listening else self.wake_status.mode
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
        if self.wake_status.always_listening:
            self.wake_status.mode = "speaking" if self.status.speaking else "waiting_for_wake_word"
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
        payload = self.tts.speak(text, voice=self.provider_config.voice_identity)
        self.status.speaking = payload.get("status") not in {"empty", "error", "unavailable"}
        return self.snapshot({"status": "ok", "speech": payload})

    def stop_speaking(self) -> dict[str, Any]:
        payload = self.tts.stop()
        self.status.speaking = False
        if self.wake_status.always_listening:
            self.wake_status.mode = "waiting_for_wake_word"
        return self.snapshot({"status": "ok", "speech": payload})

    def start_wake(self) -> dict[str, Any]:
        self.wake_status.always_listening = True
        self.wake_status.mode = "waiting_for_wake_word"
        self.wake_status.wake_word_detected = False
        self.wake_status.voice_detected = False
        self.wake_status.noisy_ignored = False
        self.wake_status.last_wake_phrase = None
        self.wake_status.last_event = "Always-listening mode is waiting for ULTRON."
        self.status.microphone_enabled = True
        self.status.listening = False
        self.status.push_to_talk = False
        self.status.last_error = None
        return self.snapshot({"status": "ok"})

    def stop_wake(self) -> dict[str, Any]:
        self.wake_status.always_listening = False
        self.wake_status.mode = "inactive"
        self.wake_status.wake_word_detected = False
        self.wake_status.voice_detected = False
        self.wake_status.noisy_ignored = False
        self.wake_status.last_event = "Always-listening mode stopped."
        self.status.microphone_enabled = False
        self.status.listening = False
        return self.snapshot({"status": "ok"})

    def wake_snapshot(self) -> dict[str, Any]:
        return self.snapshot({"status": "ok", **self.gate_status()})

    def process_wake_input(self, payload: dict[str, Any], command_runner) -> dict[str, Any]:
        if not self.wake_status.always_listening:
            self.wake_status.mode = "inactive"
            self.wake_status.last_event = "Always-listening mode is off."
            return self.snapshot({"status": "inactive", "message": self.wake_status.last_event, **self.gate_status()})

        vad_result = self.vad.detect(payload)
        self.wake_status.voice_detected = bool(vad_result.speech)
        self.wake_status.noisy_ignored = bool(vad_result.noisy or not vad_result.speech)
        if not vad_result.speech:
            self.wake_status.mode = "waiting_for_wake_word"
            self.wake_status.wake_word_detected = False
            self.wake_status.last_wake_phrase = None
            self.wake_status.last_event = vad_result.reason
            return self.snapshot(
                {
                    "status": "ignored",
                    "message": vad_result.reason,
                    "vad": vad_result.to_dict(),
                    "command_executed": False,
                    **self.gate_status(),
                }
            )

        wake_result = self.wake.detect(payload)
        raw_text = str(payload.get("transcript") or payload.get("text") or "").strip()
        if self.wake_status.mode != "listening" and not wake_result.detected:
            self.wake_status.wake_word_detected = False
            self.wake_status.last_wake_phrase = None
            self.wake_status.last_event = "Speech detected, but wake word was not detected."
            return self.snapshot(
                {
                    "status": "ignored",
                    "message": self.wake_status.last_event,
                    "wake_detection": wake_result.to_dict(),
                    "vad": vad_result.to_dict(),
                    "command_executed": False,
                    **self.gate_status(),
                }
            )

        authorized_text = raw_text
        if wake_result.detected:
            self.wake_status.wake_word_detected = True
            self.wake_status.last_wake_phrase = wake_result.phrase
            authorized_text = strip_wake_phrase(raw_text, self.wake_status.wake_phrases)
            if not authorized_text:
                self.wake_status.mode = "listening"
                self.wake_status.last_event = "Wake word detected. Listening for a command."
                self.status.listening = True
                return self.snapshot(
                    {
                        "status": "wake_detected",
                        "message": self.wake_status.last_event,
                        "wake_detection": wake_result.to_dict(),
                        "vad": vad_result.to_dict(),
                        "command_executed": False,
                        **self.gate_status(),
                    }
                )

        self.wake_status.mode = "thinking"
        self.wake_status.last_event = "Wake gate authorized a speech segment."
        command_payload = dict(payload)
        command_payload["transcript"] = authorized_text
        command_payload["wake_authorized"] = True
        voice_payload = self.transcribe_and_run(command_payload, command_runner)
        if voice_payload.get("status") == "empty":
            self.wake_status.mode = "listening"
            self.wake_status.noisy_ignored = True
            self.wake_status.last_event = str(voice_payload.get("message", "No speech was detected."))
            return self.snapshot(
                {
                    **voice_payload,
                    "wake_detection": wake_result.to_dict(),
                    "vad": vad_result.to_dict(),
                    "command_executed": False,
                    **self.gate_status(),
                }
            )
        return self.snapshot(
            {
                **voice_payload,
                "wake_detection": wake_result.to_dict(),
                "vad": vad_result.to_dict(),
                "command_executed": True,
                **self.gate_status(),
            }
        )

    def providers_status(self) -> dict[str, Any]:
        stt_configured = _health(self.configured_stt, kind="stt", configured=True, active=self.configured_stt.name == self.stt.name)
        tts_configured = _health(self.configured_tts, kind="tts", configured=True, active=self.configured_tts.name == self.tts.name)
        stt_active = _health(self.stt, kind="stt", configured=self.configured_stt.name == self.stt.name, active=True)
        tts_active = _health(self.tts, kind="tts", configured=self.configured_tts.name == self.tts.name, active=True)
        if self.configured_stt.name != self.stt.name:
            stt_configured.fallback_to = self.stt.name
        if self.configured_tts.name != self.tts.name:
            tts_configured.fallback_to = self.tts.name
        return {
            "configured": {"stt": self.configured_stt.name, "tts": self.configured_tts.name},
            "active": {"stt": self.stt.name, "tts": self.tts.name},
            "providers": {
                "stt": stt_configured.to_dict(),
                "tts": tts_configured.to_dict(),
                "active_stt": stt_active.to_dict(),
                "active_tts": tts_active.to_dict(),
            },
            "voice_identity": self.provider_config.voice_identity,
            "speech_settings": {
                "rate": self.provider_config.rate,
                "pitch": self.provider_config.pitch,
                "volume": self.provider_config.volume,
                "device": self.provider_config.device,
            },
        }

    def gate_status(self) -> dict[str, Any]:
        return {
            "wake": self.wake_status.to_dict(),
            "gate_providers": gate_providers_status(self.configured_wake, self.wake, self.configured_vad, self.vad),
        }

    def test_stt(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        test_payload = {"transcript": "ULTRON, create note provider test"} if payload is None else payload
        result = self.stt.transcribe(test_payload)
        return self.snapshot({"status": "ok" if not result.empty else "empty", "transcript": result.to_dict(), **self.providers_status()})

    def test_tts(self, text: str = "ULTRON voice provider test.") -> dict[str, Any]:
        if self.status.muted:
            return self.snapshot({"status": "muted", "message": "Voice output is muted.", **self.providers_status()})
        speech = self.tts.speak(text, voice=self.provider_config.voice_identity)
        provider_status = self.providers_status()
        return self.snapshot({"status": "ok", **provider_status, "speech": speech})

    def snapshot(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {
            "voice": self.status.to_dict(),
            "wake": self.wake_status.to_dict(),
            "history": [item.to_dict() for item in self.history],
        }
        if extra:
            payload.update(extra)
        return payload

    def _remember(self, record: TranscriptRecord) -> None:
        self.history.append(record)
        if len(self.history) > self.history_limit:
            self.history = self.history[-self.history_limit :]


def build_voice_session(config: Any | None = None) -> VoiceSession:
    provider_config = VoiceProviderConfig.from_config(config) if config is not None else VoiceProviderConfig()
    wake_config = WakeGateConfig.from_config(config) if config is not None else WakeGateConfig()
    requested_stt = _create_stt_provider(provider_config)
    requested_tts = _create_tts_provider(provider_config)
    configured_wake, wake = build_wake_provider(wake_config)
    configured_vad, vad = build_vad_provider(wake_config)
    stt = requested_stt if _health(requested_stt, kind="stt", configured=True, active=False).available else BrowserTranscriptSTT()
    tts = requested_tts if _health(requested_tts, kind="tts", configured=True, active=False).available else BrowserSpeechTTS()
    return VoiceSession(
        stt=stt,
        tts=tts,
        configured_stt=requested_stt,
        configured_tts=requested_tts,
        wake=wake,
        vad=vad,
        configured_wake=configured_wake,
        configured_vad=configured_vad,
        provider_config=provider_config,
        wake_config=wake_config,
    )


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


def _create_stt_provider(config: VoiceProviderConfig) -> STTProvider:
    provider = config.stt_provider
    if provider == "faster_whisper":
        return FasterWhisperSTT(config.stt_model_path, device=config.device)
    if provider == "whisper_cpp":
        return WhisperCppSTT(config.stt_model_path, device=config.device)
    if provider == "browser":
        return BrowserTranscriptSTT()
    if provider == "mock":
        return MockSTT()
    return TextPayloadSTT()


def _create_tts_provider(config: VoiceProviderConfig) -> TTSProvider:
    provider = "browser_speech_synthesis" if config.tts_provider == "browser" else config.tts_provider
    if provider == "piper":
        return PiperTTS(
            config.tts_model_path,
            voice_path=config.tts_voice_path,
            rate=config.rate,
            pitch=config.pitch,
            volume=config.volume,
        )
    if provider == "pyttsx3":
        return Pyttsx3TTS(rate=config.rate, pitch=config.pitch, volume=config.volume)
    if provider == "mock":
        return MockTTS()
    return BrowserSpeechTTS()


def _health(provider: Any, *, kind: str, configured: bool, active: bool) -> ProviderHealth:
    if hasattr(provider, "health"):
        health = provider.health()
        health.configured = configured
        health.active = active
        return health
    return ProviderHealth(kind, getattr(provider, "name", "unknown"), configured=configured, active=active, available=True, detail="Provider does not expose a detailed health check.")


def _payload_audio_path(payload: dict[str, Any]) -> Path | None:
    raw = payload.get("audio_path")
    if not raw:
        return None
    path = Path(str(raw)).expanduser()
    return path if path.exists() and path.is_file() else None
