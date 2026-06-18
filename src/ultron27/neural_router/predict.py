from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .dataset import DEFAULT_MAX_LENGTH, DEFAULT_VOCAB_SIZE, hash_tokens
from .labels import HEADS, LabelMaps
from .model import MODEL_CONFIG, build_model, require_torch


@dataclass(frozen=True)
class NeuralRouterPrediction:
    route: str
    intent: str
    tool_name: str
    risk_level: str
    requires_confirmation: bool
    confidence: float
    source: str = "neural_router"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class NeuralRouterPredictor:
    def __init__(self, model_path: Path | str) -> None:
        self.model_path = Path(model_path)
        self.available = False
        self.error: str | None = None
        self.torch: Any | None = None
        self.model: Any | None = None
        self.label_maps: LabelMaps | None = None
        self.config: dict[str, Any] = dict(MODEL_CONFIG)
        self._load()

    def predict(self, text: str) -> NeuralRouterPrediction | None:
        if not self.available or self.model is None or self.torch is None or self.label_maps is None:
            return None
        input_ids = self.torch.tensor(
            [hash_tokens(text, max_length=int(self.config["max_length"]), vocab_size=int(self.config["vocab_size"]))],
            dtype=self.torch.long,
        )
        with self.torch.no_grad():
            logits = self.model(input_ids)
        decoded: dict[str, str] = {}
        confidences: list[float] = []
        for head in HEADS:
            probabilities = self.torch.softmax(logits[head], dim=-1)[0]
            confidence, index = self.torch.max(probabilities, dim=0)
            decoded[head] = self.label_maps.decode(head, int(index.item()))
            confidences.append(float(confidence.item()))
        return NeuralRouterPrediction(
            route=decoded["route"],
            intent=decoded["intent"],
            tool_name=decoded["tool_name"],
            risk_level=decoded["risk_level"],
            requires_confirmation=decoded["requires_confirmation"] == "true",
            confidence=sum(confidences) / max(1, len(confidences)),
        )

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.available,
            "model_path": str(self.model_path),
            "error": self.error,
            "source": "neural_router",
        }

    def _load(self) -> None:
        if not self.model_path.exists():
            self.error = f"Neural router model not found: {self.model_path}"
            return
        try:
            self.torch = require_torch()
            checkpoint = self.torch.load(self.model_path, map_location="cpu")
            self.config = {**MODEL_CONFIG, **checkpoint.get("config", {})}
            self.label_maps = LabelMaps.from_dict(checkpoint["label_maps"])
            self.model = build_model(self.label_maps.num_classes(), self.config)
            self.model.load_state_dict(checkpoint["model_state"])
            self.model.eval()
            self.available = True
            self.error = None
        except Exception as exc:  # pragma: no cover - defensive optional model loading
            self.available = False
            self.error = str(exc)
