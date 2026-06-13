from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from ultron27.audit import append_audit_record
from ultron27.cli import main
from ultron27.config import load_config
from ultron27.executor import Executor
from ultron27.models import ToolCall
from ultron27.planner import DatasetPlanner, regex_plan
from ultron27.policy import decide
from ultron27.tools import validate_tool_call


class PipelineTest(unittest.TestCase):
    def test_regex_volume_command_is_valid_and_allowed(self) -> None:
        plan = regex_plan("set volume to 40 percent")
        validation = validate_tool_call(plan.tool_call)
        decision = decide(plan, validation)

        self.assertEqual(plan.tool_call, ToolCall("set_system_volume", {"level": 40}))
        self.assertTrue(validation.valid)
        self.assertEqual(decision.action, "allow")

    def test_high_risk_delete_requires_confirmation(self) -> None:
        plan = regex_plan("delete project_report.txt")
        validation = validate_tool_call(plan.tool_call)
        decision = decide(plan, validation)

        self.assertTrue(validation.valid)
        self.assertEqual(decision.action, "confirm")

    def test_dataset_exact_match_uses_expected_tool(self) -> None:
        planner = DatasetPlanner.from_jsonl()
        plan = planner.plan("play lofi beats")

        self.assertEqual(plan.tool_call.name, "play_music")
        self.assertEqual(plan.tool_call.arguments, {"query": "lofi beats"})
        self.assertEqual(plan.source, "dataset_exact")

    def test_planner_prefers_numeric_slot_extraction_over_fuzzy_match(self) -> None:
        planner = DatasetPlanner.from_jsonl()
        plan = planner.plan("set volume to 40 percent")

        self.assertEqual(plan.tool_call, ToolCall("set_system_volume", {"level": 40}))
        self.assertEqual(plan.source, "regex")

    def test_validation_rejects_bad_volume(self) -> None:
        validation = validate_tool_call(ToolCall("set_system_volume", {"level": 120}))

        self.assertFalse(validation.valid)
        self.assertTrue(any("between 0 and 100" in error for error in validation.errors))

    def test_dry_run_executor_does_not_mutate(self) -> None:
        result = Executor(dry_run=True).execute(ToolCall("set_system_volume", {"level": 25}))

        self.assertEqual(result.status, "dry_run")
        self.assertIn("25%", result.message)

    def test_config_file_and_environment_override_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "ultron.config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "dataset_path": "custom_dataset.jsonl",
                        "audit_log": "logs/audit.jsonl",
                        "dry_run": False,
                        "workspace": "workspace",
                    }
                ),
                encoding="utf-8",
            )

            config = load_config(
                config_path,
                environ={"ULTRON_DRY_RUN": "true", "ULTRON_AUDIT_LOG": "override.jsonl"},
                base_dir=root,
            )

            self.assertEqual(config.dataset_path, root / "custom_dataset.jsonl")
            self.assertEqual(config.audit_log, root / "override.jsonl")
            self.assertTrue(config.dry_run)
            self.assertEqual(config.workspace, root / "workspace")

    def test_audit_record_includes_stable_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            audit_path = Path(tmp) / "audit.jsonl"
            append_audit_record({"utterance": "open notepad"}, audit_path)

            record = json.loads(audit_path.read_text(encoding="utf-8"))

            self.assertEqual(record["schema_version"], 1)
            self.assertIn("record_id", record)
            self.assertIn("timestamp_utc", record)
            self.assertEqual(record["utterance"], "open notepad")

    def test_cli_returns_structured_dry_run_response(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            main(["set volume to 40 percent", "--no-audit"])

        payload = json.loads(output.getvalue())

        self.assertEqual(payload["tool_call"], {"name": "set_system_volume", "arguments": {"level": 40}})
        self.assertEqual(payload["policy"]["action"], "allow")
        self.assertEqual(payload["result"]["status"], "dry_run")
        self.assertTrue(payload["runtime"]["dry_run"])

    def test_cli_confirmed_delete_stays_non_destructive(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            main(["delete project_report.txt", "--yes", "--no-audit"])

        payload = json.loads(output.getvalue())

        self.assertEqual(payload["policy"]["action"], "allow")
        self.assertEqual(payload["tool_call"]["name"], "delete_file")
        self.assertEqual(payload["result"]["status"], "dry_run")
        self.assertIn("Would delete file", payload["result"]["message"])

    def test_execute_confirmed_delete_is_not_implemented(self) -> None:
        result = Executor(dry_run=False).execute(ToolCall("delete_file", {"file_name": "project_report.txt"}))

        self.assertEqual(result.status, "not_implemented")
        self.assertIn("intentionally not implemented", result.message)


if __name__ == "__main__":
    unittest.main()
