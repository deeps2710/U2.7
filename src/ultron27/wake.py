from __future__ import annotations

import importlib.util
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol


DEFAULT_WAKE_PHRASES = ("ultron", "hey ultron")
NOISE_TOKENS = {"", ".", "...", "noise", "static", "[noise]", "[silence]", "silence", "background noise"}


class WakeWordProvider(Protocol):
    name: str

    def detect(self, payload: dict[str, Any]) -> "WakeWordResult":
        ...


class VADProvider(Protocol):
    name: str

    def detect(self, payload: dict[str, Any]) -> "VADResult":
        ...


@dataclass(frozen=True)
class WakeGateConfig:
    wake_word_provider: str = "text"
    wake_phrases: tuple[str, ...] = DEFAULT_WAKE_PHRASES
    wake_model_path: Path | None = None
    vad_provider: str = "energy"
    vad_energy_threshold: float = 0.015
    clap_spike_ratio: float = 7.0
    clap_min_rms: float = 0.012
    clap_min_gap_s: float = 0.05
    clap_max_gap_s: float = 0.35
    clap_cooldown_s: float = 0.45
    clap_retrigger_ratio: float = 0.55
    clap_noise_floor_alpha: float = 0.992
    clap_quiet_gate_mult: float = 2.2

    @classmethod
    def from_config(cls, config: Any) -> "WakeGateConfig":
        return cls(
            wake_word_provider=str(getattr(config, "wake_word_provider", cls.wake_word_provider)).lower(),
            wake_phrases=tuple(getattr(config, "wake_phrases", cls.wake_phrases)),
            wake_model_path=getattr(config, "wake_model_path", None),
            vad_provider=str(getattr(config, "vad_provider", cls.vad_provider)).lower(),
            vad_energy_threshold=float(getattr(config, "vad_energy_threshold", cls.vad_energy_threshold)),
            clap_spike_ratio=float(getattr(config, "clap_spike_ratio", cls.clap_spike_ratio)),
            clap_min_rms=float(getattr(config, "clap_min_rms", cls.clap_min_rms)),
            clap_min_gap_s=float(getattr(config, "clap_min_gap_s", cls.clap_min_gap_s)),
            clap_max_gap_s=float(getattr(config, "clap_max_gap_s", cls.clap_max_gap_s)),
            clap_cooldown_s=float(getattr(config, "clap_cooldown_s", cls.clap_cooldown_s)),
            clap_retrigger_ratio=float(getattr(config, "clap_retrigger_ratio", cls.clap_retrigger_ratio)),
            clap_noise_floor_alpha=float(getattr(config, "clap_noise_floor_alpha", cls.clap_noise_floor_alpha)),
            clap_quiet_gate_mult=float(getattr(config, "clap_quiet_gate_mult", cls.clap_quiet_gate_mult)),
        )


@dataclass
class GateProviderHealth:
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
class WakeWordResult:
    detected: bool
    phrase: str | None = None
    confidence: float = 0.0
    provider: str = "text_wake_word"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VADResult:
    speech: bool
    confidence: float = 0.0
    energy: float | None = None
    noisy: bool = False
    reason: str = "No speech detected."
    provider: str = "energy_threshold"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WakeStatus:
    always_listening: bool = False
    mode: str = "inactive"
    wake_provider: str = "text_wake_word"
    vad_provider: str = "energy_threshold"
    wake_phrases: tuple[str, ...] = DEFAULT_WAKE_PHRASES
    wake_word_detected: bool = False
    voice_detected: bool = False
    noisy_ignored: bool = False
    last_wake_phrase: str | None = None
    last_event: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["wake_phrases"] = list(self.wake_phrases)
        return payload


class TextWakeWordProvider:
    name = "text_wake_word"

    def __init__(self, phrases: tuple[str, ...] = DEFAULT_WAKE_PHRASES) -> None:
        self.phrases = tuple(_normalize_phrase(phrase) for phrase in phrases if phrase.strip()) or DEFAULT_WAKE_PHRASES

    def detect(self, payload: dict[str, Any]) -> WakeWordResult:
        text = _payload_text(payload)
        for phrase in sorted(self.phrases, key=len, reverse=True):
            pattern = rf"\b{re.escape(phrase)}\b"
            if re.search(pattern, text, flags=re.IGNORECASE):
                return WakeWordResult(True, phrase=phrase, confidence=1.0, provider=self.name)
        return WakeWordResult(False, provider=self.name)

    def health(self) -> GateProviderHealth:
        return GateProviderHealth("wake", self.name, configured=True, active=True, available=True, detail="Detects configured wake phrases in transcript text.")


class MockWakeWordProvider(TextWakeWordProvider):
    name = "mock_wake_word"

    def health(self) -> GateProviderHealth:
        return GateProviderHealth("wake", self.name, configured=True, active=True, available=True, detail="Deterministic mock wake-word provider for tests.")


class OpenWakeWordProvider(TextWakeWordProvider):
    name = "openwakeword"

    def __init__(self, phrases: tuple[str, ...] = DEFAULT_WAKE_PHRASES, model_path: Path | None = None) -> None:
        super().__init__(phrases)
        self.model_path = model_path

    def detect(self, payload: dict[str, Any]) -> WakeWordResult:
        if payload.get("transcript") or payload.get("text"):
            result = super().detect(payload)
            result.provider = self.name
            return result
        if not self.health().available:
            return WakeWordResult(False, provider=self.name)
        return WakeWordResult(False, provider=self.name)

    def health(self) -> GateProviderHealth:
        if importlib.util.find_spec("openwakeword") is None:
            return GateProviderHealth("wake", self.name, configured=True, active=False, available=False, detail="Python package openwakeword is not installed.", fallback_to="text_wake_word")
        if self.model_path is not None and not self.model_path.exists():
            return GateProviderHealth("wake", self.name, configured=True, active=False, available=False, detail=f"Wake model path not found: {self.model_path}", fallback_to="text_wake_word")
        return GateProviderHealth("wake", self.name, configured=True, active=True, available=True, detail="openWakeWord is available; transcript fallback remains enabled.")


class DoubleClapWakeProvider:
    """Adaptive double-clap detector for energy-only wake events.

    This ports the useful part of the reference Jarvis script into ULTRON's
    provider boundary. It only authorizes listening; it never executes actions.
    """

    name = "double_clap"

    def __init__(self, config: WakeGateConfig | None = None) -> None:
        self.config = config or WakeGateConfig(wake_word_provider="double_clap")
        self.noise_floor = 1e-4
        self.last_logged_double = 0.0
        self.first_clap_time: float | None = None
        self.spike_armed = True
        self.last_threshold = max(self.noise_floor * self.config.clap_spike_ratio, self.config.clap_min_rms)

    def detect(self, payload: dict[str, Any]) -> WakeWordResult:
        text_result = TextWakeWordProvider(self.config.wake_phrases).detect(payload)
        if text_result.detected:
            text_result.provider = self.name
            return text_result

        level = _payload_energy(payload)
        if level is None:
            return WakeWordResult(False, provider=self.name)

        now = _payload_timestamp(payload)
        quiet_gate = self.noise_floor * self.config.clap_quiet_gate_mult
        if level < quiet_gate:
            alpha = _clamp_float(self.config.clap_noise_floor_alpha, 0.0, 0.9999)
            self.noise_floor = alpha * self.noise_floor + (1.0 - alpha) * level
            self.noise_floor = max(self.noise_floor, 1e-7)

        threshold = max(self.noise_floor * self.config.clap_spike_ratio, self.config.clap_min_rms)
        self.last_threshold = threshold
        if level < threshold * self.config.clap_retrigger_ratio:
            self.spike_armed = True

        if not self.spike_armed or level < threshold or (now - self.last_logged_double) < self.config.clap_cooldown_s:
            return WakeWordResult(False, provider=self.name)

        self.spike_armed = False
        if self.first_clap_time is None:
            self.first_clap_time = now
            return WakeWordResult(False, provider=self.name)

        gap = now - self.first_clap_time
        if gap < self.config.clap_min_gap_s:
            return WakeWordResult(False, provider=self.name)
        if gap <= self.config.clap_max_gap_s:
            self.first_clap_time = None
            self.last_logged_double = now
            confidence = min(1.0, level / max(threshold, 1e-7))
            return WakeWordResult(True, phrase="double_clap", confidence=confidence, provider=self.name)

        self.first_clap_time = now
        return WakeWordResult(False, provider=self.name)

    def health(self) -> GateProviderHealth:
        return GateProviderHealth(
            "wake",
            self.name,
            configured=True,
            active=True,
            available=True,
            detail=(
                "Adaptive double-clap wake gate using audio_energy payloads "
                f"(ratio={self.config.clap_spike_ratio:.1f}, gap={self.config.clap_min_gap_s:.2f}-{self.config.clap_max_gap_s:.2f}s)."
            ),
        )


class EnergyVADProvider:
    name = "energy_threshold"

    def __init__(self, threshold: float = 0.015) -> None:
        self.threshold = threshold

    def detect(self, payload: dict[str, Any]) -> VADResult:
        text = _payload_text(payload)
        energy = _payload_energy(payload)
        if text in NOISE_TOKENS:
            return VADResult(False, confidence=0.0, energy=energy, noisy=True, reason="Empty or noisy text was ignored.", provider=self.name)
        if energy is not None and energy < self.threshold and not text:
            return VADResult(False, confidence=0.0, energy=energy, noisy=True, reason="Audio energy below speech threshold.", provider=self.name)
        if energy is not None and energy < self.threshold and text in NOISE_TOKENS:
            return VADResult(False, confidence=0.0, energy=energy, noisy=True, reason="Low-energy noisy input was ignored.", provider=self.name)
        if text:
            return VADResult(True, confidence=1.0, energy=energy, noisy=False, reason="Speech-like text detected.", provider=self.name)
        if energy is not None and energy >= self.threshold:
            return VADResult(True, confidence=min(1.0, energy / max(self.threshold, 0.0001)), energy=energy, noisy=False, reason="Energy threshold exceeded.", provider=self.name)
        return VADResult(False, confidence=0.0, energy=energy, noisy=True, reason="No speech signal was detected.", provider=self.name)

    def health(self) -> GateProviderHealth:
        return GateProviderHealth("vad", self.name, configured=True, active=True, available=True, detail=f"Energy threshold fallback at {self.threshold:.3f}.")


class MockVADProvider(EnergyVADProvider):
    name = "mock_vad"

    def __init__(self, speech: bool = True, noisy: bool = False) -> None:
        super().__init__()
        self.speech = speech
        self.noisy = noisy

    def detect(self, payload: dict[str, Any]) -> VADResult:
        if self.noisy:
            return VADResult(False, confidence=0.0, noisy=True, reason="Mock noisy input.", provider=self.name)
        return VADResult(self.speech, confidence=1.0 if self.speech else 0.0, noisy=not self.speech, reason="Mock VAD result.", provider=self.name)

    def health(self) -> GateProviderHealth:
        return GateProviderHealth("vad", self.name, configured=True, active=True, available=True, detail="Deterministic mock VAD provider for tests.")


class SileroVADProvider(EnergyVADProvider):
    name = "silero_vad"

    def health(self) -> GateProviderHealth:
        if importlib.util.find_spec("torch") is None:
            return GateProviderHealth("vad", self.name, configured=True, active=False, available=False, detail="PyTorch/Silero VAD dependencies are not installed.", fallback_to="energy_threshold")
        return GateProviderHealth("vad", self.name, configured=True, active=True, available=True, detail="Silero dependencies are importable; energy fallback handles transcript payloads.")


class WebRTCVADProvider(EnergyVADProvider):
    name = "webrtc_vad"

    def health(self) -> GateProviderHealth:
        if importlib.util.find_spec("webrtcvad") is None:
            return GateProviderHealth("vad", self.name, configured=True, active=False, available=False, detail="Python package webrtcvad is not installed.", fallback_to="energy_threshold")
        return GateProviderHealth("vad", self.name, configured=True, active=True, available=True, detail="WebRTC VAD is importable; energy fallback handles transcript payloads.")


def build_wake_provider(config: WakeGateConfig) -> tuple[WakeWordProvider, WakeWordProvider]:
    requested: WakeWordProvider
    if config.wake_word_provider == "openwakeword":
        requested = OpenWakeWordProvider(config.wake_phrases, config.wake_model_path)
    elif config.wake_word_provider == "double_clap":
        requested = DoubleClapWakeProvider(config)
    elif config.wake_word_provider == "mock":
        requested = MockWakeWordProvider(config.wake_phrases)
    else:
        requested = TextWakeWordProvider(config.wake_phrases)
    active = requested if _gate_health(requested, kind="wake", configured=True, active=False).available else TextWakeWordProvider(config.wake_phrases)
    return requested, active


def build_vad_provider(config: WakeGateConfig) -> tuple[VADProvider, VADProvider]:
    requested: VADProvider
    if config.vad_provider == "silero":
        requested = SileroVADProvider(config.vad_energy_threshold)
    elif config.vad_provider == "webrtc":
        requested = WebRTCVADProvider(config.vad_energy_threshold)
    elif config.vad_provider == "mock":
        requested = MockVADProvider()
    else:
        requested = EnergyVADProvider(config.vad_energy_threshold)
    active = requested if _gate_health(requested, kind="vad", configured=True, active=False).available else EnergyVADProvider(config.vad_energy_threshold)
    return requested, active


def gate_providers_status(
    configured_wake: WakeWordProvider,
    wake: WakeWordProvider,
    configured_vad: VADProvider,
    vad: VADProvider,
) -> dict[str, Any]:
    wake_configured = _gate_health(configured_wake, kind="wake", configured=True, active=configured_wake.name == wake.name)
    wake_active = _gate_health(wake, kind="wake", configured=configured_wake.name == wake.name, active=True)
    vad_configured = _gate_health(configured_vad, kind="vad", configured=True, active=configured_vad.name == vad.name)
    vad_active = _gate_health(vad, kind="vad", configured=configured_vad.name == vad.name, active=True)
    if configured_wake.name != wake.name:
        wake_configured.fallback_to = wake.name
    if configured_vad.name != vad.name:
        vad_configured.fallback_to = vad.name
    return {
        "configured": {"wake": configured_wake.name, "vad": configured_vad.name},
        "active": {"wake": wake.name, "vad": vad.name},
        "providers": {
            "wake": wake_configured.to_dict(),
            "vad": vad_configured.to_dict(),
            "active_wake": wake_active.to_dict(),
            "active_vad": vad_active.to_dict(),
        },
    }


def strip_wake_phrase(text: str, phrases: tuple[str, ...] = DEFAULT_WAKE_PHRASES) -> str:
    value = " ".join(text.strip().split())
    for phrase in sorted((_normalize_phrase(item) for item in phrases), key=len, reverse=True):
        value = re.sub(rf"^\s*{re.escape(phrase)}[\s,.:;-]*", "", value, flags=re.IGNORECASE)
    return value.strip()


def _gate_health(provider: Any, *, kind: str, configured: bool, active: bool) -> GateProviderHealth:
    if hasattr(provider, "health"):
        health = provider.health()
        health.configured = configured
        health.active = active
        return health
    return GateProviderHealth(kind, getattr(provider, "name", "unknown"), configured=configured, active=active, available=True, detail="Provider does not expose a detailed health check.")


def _payload_text(payload: dict[str, Any]) -> str:
    return " ".join(str(payload.get("transcript") or payload.get("text") or "").strip().lower().split())


def _payload_energy(payload: dict[str, Any]) -> float | None:
    value = payload.get("audio_energy", payload.get("energy"))
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _payload_timestamp(payload: dict[str, Any]) -> float:
    value = payload.get("timestamp_s", payload.get("timestamp", payload.get("time_s")))
    if value is not None:
        try:
            return float(value)
        except (TypeError, ValueError):
            pass
    return time.monotonic()


def _normalize_phrase(phrase: str) -> str:
    return " ".join(phrase.strip().lower().split())


def _clamp_float(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
