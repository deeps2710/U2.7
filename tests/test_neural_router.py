from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ultron27.brain import UltronBrain
from ultron27.config import load_config
from ultron27.conversation import ConversationManager
from ultron27.neural_router.dataset import build_label_maps, hash_tokens, load_examples
from ultron27.neural_router.predict import NeuralRouterPredictor
from ultron27.runtime import RuntimeSettings, UltronAssistant


class NeuralRouterTest(unittest.TestCase):
    def test_dataset_loader_and_label_maps_use_router_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "router.jsonl"
            path.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "utterance": "hello",
                                "cleaned_utterance": "hello",
                                "route": "casual_chat",
                                "intent": "chat",
                                "tool_name": "assistant_reply",
                                "risk_level": "none",
                                "requires_confirmation": False,
                            }
                        ),
                        json.dumps(
                            {
                                "utterance": "delete file",
                                "cleaned_utterance": "delete file",
                                "route": "high_risk_action",
                                "intent": "delete_file",
                                "tool_name": "delete_file",
                                "risk_level": "high",
                                "requires_confirmation": True,
                            }
                        ),
                    ]
                ),
                encoding="utf-8",
            )

            examples = load_examples(path)
            maps = build_label_maps(examples)

        self.assertEqual(examples[0].text, "hello")
        self.assertIn("casual_chat", maps.values["route"])
        self.assertIn("true", maps.values["requires_confirmation"])
        self.assertIn("false", maps.values["requires_confirmation"])

    def test_hash_tokens_are_stable_and_padded(self) -> None:
        first = hash_tokens("Open Notepad!", max_length=6, vocab_size=128)
        second = hash_tokens("Open Notepad!", max_length=6, vocab_size=128)

        self.assertEqual(first, second)
        self.assertEqual(len(first), 6)
        self.assertEqual(first[-2:], [0, 0])

    def test_missing_model_predictor_is_unavailable_without_crashing(self) -> None:
        predictor = NeuralRouterPredictor(Path("missing-router-model.pt"))

        self.assertFalse(predictor.available)
        self.assertIsNone(predictor.predict("open notepad"))
        self.assertIn("not found", predictor.status()["error"])

    def test_config_accepts_neural_router_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = load_config(
                environ={
                    "ULTRON_NEURAL_ROUTER_ENABLED": "true",
                    "ULTRON_NEURAL_ROUTER_MODEL": ".ultron/models/test-router.pt",
                },
                base_dir=Path(tmp),
            )

        self.assertTrue(config.neural_router_enabled)
        self.assertEqual(config.neural_router_model.name, "test-router.pt")

    def test_conversation_keeps_neural_router_advisory_only_when_model_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset = root / "dataset.jsonl"
            dataset.write_text(
                json.dumps(
                    {
                        "utterance": "open notepad",
                        "intent": "open_app",
                        "tool_name": "open_application",
                        "arguments": {"app": "notepad"},
                        "risk_level": "low",
                        "requires_confirmation": False,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            settings = RuntimeSettings(
                dataset_path=dataset,
                audit_log=root / "audit.jsonl",
                workspace=root,
                dry_run=True,
                safe_roots=(root,),
                app_aliases={"notepad": "notepad.exe"},
                screenshot_dir=root / "screenshots",
                planner_mode="rules",
                llm_model="qwen",
                llm_endpoint="http://localhost:11434",
                llm_timeout_seconds=1,
                neural_router_enabled=True,
                neural_router_model=root / "missing.pt",
                write_audit=False,
            )
            manager = ConversationManager(UltronBrain(UltronAssistant(settings)))

            payload = manager.handle("open notepad")

        self.assertEqual(payload["route"], "command")
        self.assertEqual(payload["task"]["steps"][0]["tool_call"]["name"], "open_application")
        self.assertEqual(payload["neural_router"]["source"], "neural_router")
        self.assertFalse(payload["neural_router"]["enabled"])


if __name__ == "__main__":
    unittest.main()
