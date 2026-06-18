from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from .labels import HEADS, LabelMaps


DEFAULT_MAX_LENGTH = 64
DEFAULT_VOCAB_SIZE = 8192
TOKEN_RE = re.compile(r"[a-z0-9]+|[^\s]", re.IGNORECASE)


@dataclass(frozen=True)
class RouterExample:
    text: str
    labels: dict[str, str]


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                yield json.loads(stripped)


def load_examples(path: Path, *, limit: int | None = None) -> list[RouterExample]:
    examples: list[RouterExample] = []
    for row in iter_jsonl(path):
        text = str(row.get("cleaned_utterance") or row.get("utterance") or "").strip()
        if not text:
            continue
        labels = {head: str(row.get(head, "")) for head in HEADS}
        labels["requires_confirmation"] = "true" if bool(row.get("requires_confirmation")) else "false"
        examples.append(RouterExample(text=text, labels=labels))
        if limit is not None and len(examples) >= limit:
            break
    return examples


def build_label_maps(examples: list[RouterExample]) -> LabelMaps:
    return LabelMaps.from_rows(example.labels for example in examples)


def tokenize(text: str) -> list[str]:
    return [match.group(0).lower() for match in TOKEN_RE.finditer(text)]


def hash_tokens(text: str, *, max_length: int = DEFAULT_MAX_LENGTH, vocab_size: int = DEFAULT_VOCAB_SIZE) -> list[int]:
    ids = [stable_token_id(token, vocab_size=vocab_size) for token in tokenize(text)[:max_length]]
    if len(ids) < max_length:
        ids.extend([0] * (max_length - len(ids)))
    return ids


def stable_token_id(token: str, *, vocab_size: int = DEFAULT_VOCAB_SIZE) -> int:
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest()
    return int.from_bytes(digest, "big") % (vocab_size - 1) + 1


class TorchRouterDataset:
    def __init__(
        self,
        examples: list[RouterExample],
        label_maps: LabelMaps,
        *,
        max_length: int = DEFAULT_MAX_LENGTH,
        vocab_size: int = DEFAULT_VOCAB_SIZE,
    ) -> None:
        try:
            import torch
        except ImportError as exc:  # pragma: no cover - depends on optional torch install
            raise RuntimeError("PyTorch is required for TorchRouterDataset. Install with: pip install -e .[neural]") from exc
        self.torch = torch
        self.examples = examples
        self.label_maps = label_maps
        self.max_length = max_length
        self.vocab_size = vocab_size

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, index: int) -> dict[str, Any]:
        example = self.examples[index]
        item: dict[str, Any] = {
            "input_ids": self.torch.tensor(hash_tokens(example.text, max_length=self.max_length, vocab_size=self.vocab_size), dtype=self.torch.long),
        }
        for head in HEADS:
            item[head] = self.torch.tensor(self.label_maps.encode(head, example.labels[head]), dtype=self.torch.long)
        return item
