from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any

from .dataset import DEFAULT_MAX_LENGTH, DEFAULT_VOCAB_SIZE, TorchRouterDataset, build_label_maps, load_examples
from .labels import HEADS
from .model import MODEL_CONFIG, build_model, require_torch


DEFAULT_DATASET = Path("data/ultron_synthetic_training_dataset_v2_large_50000.jsonl")
DEFAULT_MODEL = Path(".ultron/models/neural_router.pt")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Train ULTRON's optional neural intent router.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--validation-ratio", type=float, default=0.1)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--seed", type=int, default=27)
    args = parser.parse_args(argv)
    try:
        metrics = train(args)
    except RuntimeError as exc:
        print(f"Neural router training unavailable: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    print(json.dumps(metrics, indent=2, sort_keys=True))


def train(args: argparse.Namespace) -> dict[str, Any]:
    torch = require_torch()
    random.seed(args.seed)
    torch.manual_seed(args.seed)

    examples = load_examples(args.dataset, limit=args.limit)
    if len(examples) < 10:
        raise ValueError("Need at least 10 examples to train the neural router.")
    random.shuffle(examples)
    label_maps = build_label_maps(examples)
    split_at = max(1, int(len(examples) * (1.0 - float(args.validation_ratio))))
    train_examples = examples[:split_at]
    validation_examples = examples[split_at:] or examples[-1:]

    train_dataset = TorchRouterDataset(train_examples, label_maps, max_length=DEFAULT_MAX_LENGTH, vocab_size=DEFAULT_VOCAB_SIZE)
    validation_dataset = TorchRouterDataset(validation_examples, label_maps, max_length=DEFAULT_MAX_LENGTH, vocab_size=DEFAULT_VOCAB_SIZE)
    train_loader = torch.utils.data.DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True)
    validation_loader = torch.utils.data.DataLoader(validation_dataset, batch_size=args.batch_size)

    model = build_model(label_maps.num_classes(), MODEL_CONFIG)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate)
    loss_fn = torch.nn.CrossEntropyLoss()

    history: list[dict[str, Any]] = []
    for epoch in range(1, args.epochs + 1):
        model.train()
        total_loss = 0.0
        batches = 0
        for batch in train_loader:
            optimizer.zero_grad()
            logits = model(batch["input_ids"])
            loss = sum(loss_fn(logits[head], batch[head]) for head in HEADS)
            loss.backward()
            optimizer.step()
            total_loss += float(loss.item())
            batches += 1
        validation = evaluate(model, validation_loader)
        history.append({"epoch": epoch, "train_loss": total_loss / max(1, batches), "validation": validation})

    args.output.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "model_state": model.state_dict(),
            "label_maps": label_maps.to_dict(),
            "config": MODEL_CONFIG,
            "history": history,
        },
        args.output,
    )
    return {
        "status": "ok",
        "examples": len(examples),
        "train_examples": len(train_examples),
        "validation_examples": len(validation_examples),
        "model_path": str(args.output),
        "label_counts": label_maps.num_classes(),
        "history": history,
    }


def evaluate(model: Any, loader: Any) -> dict[str, float]:
    torch = require_torch()
    model.eval()
    correct = {head: 0 for head in HEADS}
    total = 0
    with torch.no_grad():
        for batch in loader:
            logits = model(batch["input_ids"])
            batch_size = int(batch["input_ids"].shape[0])
            total += batch_size
            for head in HEADS:
                predictions = logits[head].argmax(dim=-1)
                correct[head] += int((predictions == batch[head]).sum().item())
    return {head: correct[head] / max(1, total) for head in HEADS}


if __name__ == "__main__":
    main()
