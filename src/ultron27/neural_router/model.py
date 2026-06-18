from __future__ import annotations

from typing import Any

from .dataset import DEFAULT_MAX_LENGTH, DEFAULT_VOCAB_SIZE
from .labels import HEADS


MODEL_CONFIG = {
    "vocab_size": DEFAULT_VOCAB_SIZE,
    "max_length": DEFAULT_MAX_LENGTH,
    "embedding_dim": 384,
    "encoder_hidden_dim": 192,
    "hidden_dims": (1024, 512, 256),
    "dropout": 0.20,
}


def require_torch() -> Any:
    try:
        import torch
    except ImportError as exc:  # pragma: no cover - depends on optional torch install
        raise RuntimeError("PyTorch is required for the neural router. Install with: pip install -e .[neural]") from exc
    return torch


def build_model(num_classes: dict[str, int], config: dict[str, Any] | None = None) -> Any:
    torch = require_torch()
    nn = torch.nn
    cfg = {**MODEL_CONFIG, **(config or {})}

    class NeuralRouterModel(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.embedding = nn.Embedding(int(cfg["vocab_size"]), int(cfg["embedding_dim"]), padding_idx=0)
            self.encoder = nn.GRU(
                input_size=int(cfg["embedding_dim"]),
                hidden_size=int(cfg["encoder_hidden_dim"]),
                batch_first=True,
                bidirectional=True,
            )
            encoder_out = int(cfg["encoder_hidden_dim"]) * 2
            layers: list[Any] = []
            previous = encoder_out
            for hidden in cfg["hidden_dims"]:
                layers.extend([nn.Linear(previous, int(hidden)), nn.GELU(), nn.Dropout(float(cfg["dropout"]))])
                previous = int(hidden)
            self.mlp = nn.Sequential(*layers)
            self.heads = nn.ModuleDict({head: nn.Linear(previous, int(num_classes[head])) for head in HEADS})

        def forward(self, input_ids: Any) -> dict[str, Any]:
            mask = input_ids.ne(0).unsqueeze(-1)
            embedded = self.embedding(input_ids)
            encoded, _ = self.encoder(embedded)
            masked = encoded * mask
            lengths = mask.sum(dim=1).clamp(min=1)
            pooled = masked.sum(dim=1) / lengths
            hidden = self.mlp(pooled)
            return {head: layer(hidden) for head, layer in self.heads.items()}

    return NeuralRouterModel()
