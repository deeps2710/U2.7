from __future__ import annotations

import io
import json
import threading
import tempfile
import unittest
from contextlib import redirect_stdout
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

from ultron27.audit import append_audit_record
from ultron27.brain import MemoryStore, TaskState, UltronBrain
from ultron27.cli import main
from ultron27.console import format_assistant_response, run_console
from ultron27.config import load_config
from ultron27.dataset_quality import DatasetRow, analyze_dataset, build_safety_cases, is_underspecified
from ultron27.executor import Executor
from ultron27.llm import LLMPlanner, LLMPlannerError, parse_llm_tool_call
from ultron27.models import ToolCall
from ultron27.planner import DatasetPlanner, regex_plan
from ultron27.policy import decide
from ultron27.runtime import RuntimeSettings, UltronAssistant
from ultron27.tools import validate_tool_call
from ultron27.web_server import WebState, make_handler


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

    def test_phase2_create_note_writes_inside_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            result = Executor(dry_run=False, workspace=workspace).execute(
                ToolCall("create_note", {"title": "phase two", "content": "real low-risk write"})
            )

            note_path = workspace / "notes" / "phase_two.md"

            self.assertEqual(result.status, "success")
            self.assertTrue(note_path.exists())
            self.assertEqual(note_path.read_text(encoding="utf-8").strip(), "real low-risk write")

    def test_phase2_search_files_respects_safe_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            allowed = workspace / "allowed"
            blocked = workspace / "blocked"
            allowed.mkdir()
            blocked.mkdir()
            (allowed / "resume.txt").write_text("ok", encoding="utf-8")
            (blocked / "resume.txt").write_text("no", encoding="utf-8")

            result = Executor(dry_run=False, workspace=workspace, safe_roots=(allowed,)).execute(
                ToolCall("search_files", {"query": "resume", "file_type": "txt"})
            )

            self.assertEqual(result.status, "success")
            self.assertEqual(result.data["matches"], [str((allowed / "resume.txt").resolve())])

    def test_phase2_reminder_and_timer_are_saved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            executor = Executor(dry_run=False, workspace=workspace)

            reminder = executor.execute(ToolCall("set_reminder", {"task": "check email", "time": "7 pm"}))
            timer = executor.execute(ToolCall("start_timer", {"duration": "15 minutes"}))

            self.assertEqual(reminder.status, "success")
            self.assertEqual(timer.status, "success")
            self.assertTrue((workspace / ".ultron" / "reminders.jsonl").exists())
            self.assertTrue((workspace / ".ultron" / "timers.jsonl").exists())

    def test_phase2_planner_handles_timer_and_screenshot(self) -> None:
        timer = regex_plan("start timer for 15 minutes")
        screenshot = regex_plan("take a screenshot")

        self.assertEqual(timer.tool_call, ToolCall("start_timer", {"duration": "15 minutes"}))
        self.assertEqual(screenshot.tool_call, ToolCall("take_screenshot", {}))

    def test_phase3_dataset_quality_finds_conflicts_and_safety_cases(self) -> None:
        rows = [
            DatasetRow(
                id="1",
                utterance="find resume documents",
                intent="search_files",
                tool_name="search_files",
                tool_arguments={"query": "resume", "file_type": "pdf", "folder": "Downloads"},
                risk_level="low",
                requires_confirmation=False,
                expected_result="Search results",
                source="test",
                language="en",
                domain="laptop_assistant",
            ),
            DatasetRow(
                id="2",
                utterance="find resume documents",
                intent="search_files",
                tool_name="search_files",
                tool_arguments={"query": "resume", "file_type": "docx", "folder": "Documents"},
                risk_level="low",
                requires_confirmation=False,
                expected_result="Search results",
                source="test",
                language="en",
                domain="laptop_assistant",
            ),
            DatasetRow(
                id="3",
                utterance="delete resume.pdf",
                intent="delete_file",
                tool_name="delete_file",
                tool_arguments={"file_name": "resume.pdf"},
                risk_level="high",
                requires_confirmation=True,
                expected_result="Confirmation required",
                source="test",
                language="en",
                domain="laptop_assistant",
            ),
        ]

        report = analyze_dataset(rows)
        safety_cases = build_safety_cases(rows)

        self.assertEqual(report["conflicting_duplicate_groups"], 1)
        self.assertEqual(report["safety_examples"], 1)
        self.assertEqual(safety_cases[0]["expected_policy_action"], "confirm")

    def test_phase3_underspecified_search_detection(self) -> None:
        row = DatasetRow(
            id="1",
            utterance="look for assignment documents",
            intent="search_files",
            tool_name="search_files",
            tool_arguments={"query": "assignment", "file_type": "png", "folder": "Videos"},
            risk_level="low",
            requires_confirmation=False,
            expected_result="Search results",
            source="test",
            language="en",
            domain="laptop_assistant",
        )

        self.assertTrue(is_underspecified(row))

    def test_phase4_llm_json_tool_call_parser(self) -> None:
        call, intent, confidence = parse_llm_tool_call(
            '{"intent":"set_volume","tool_name":"set_system_volume","tool_arguments":{"level":35},"confidence":0.91}'
        )

        self.assertEqual(call, ToolCall("set_system_volume", {"level": 35}))
        self.assertEqual(intent, "set_volume")
        self.assertEqual(confidence, 0.91)

    def test_phase4_llm_planner_validates_tool_schema(self) -> None:
        class FakeProvider:
            def complete(self, prompt: str, timeout: float) -> str:
                return '{"intent":"set_volume","tool_name":"set_system_volume","tool_arguments":{"level":150},"confidence":1}'

        planner = LLMPlanner(FakeProvider())

        with self.assertRaises(LLMPlannerError):
            planner.plan("set volume very high")

    def test_phase4_llm_planner_produces_safe_plan(self) -> None:
        class FakeProvider:
            def complete(self, prompt: str, timeout: float) -> str:
                return '{"intent":"open_app","tool_name":"open_application","tool_arguments":{"app":"notepad"},"confidence":0.8}'

        plan = LLMPlanner(FakeProvider()).plan("launch the basic text editor")

        self.assertEqual(plan.tool_call, ToolCall("open_application", {"app": "notepad"}))
        self.assertEqual(plan.source, "llm")
        self.assertEqual(plan.risk_level.value, "low")

    def test_phase4_config_accepts_llm_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "ultron.config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "planner_mode": "hybrid",
                        "llm_provider": "ollama",
                        "llm_model": "qwen-test",
                        "llm_endpoint": "http://localhost:11434",
                        "llm_timeout_seconds": 3,
                    }
                ),
                encoding="utf-8",
            )

            config = load_config(config_path, environ={}, base_dir=root)

            self.assertEqual(config.planner_mode, "hybrid")
            self.assertEqual(config.llm_model, "qwen-test")
            self.assertEqual(config.llm_endpoint, "http://localhost:11434")
            self.assertEqual(config.llm_timeout_seconds, 3.0)

    def test_phase5_runtime_reuses_pipeline(self) -> None:
        settings = RuntimeSettings(
            dataset_path=Path("data/jarvis_dataset_v2/jarvis_laptop_commands_synthetic_v2.jsonl"),
            audit_log=Path(".ultron/test-audit.jsonl"),
            workspace=Path("."),
            dry_run=True,
            safe_roots=(Path("."),),
            app_aliases=None,
            screenshot_dir=Path(".ultron/screenshots"),
            planner_mode="rules",
            llm_model="unused",
            llm_endpoint="http://localhost:11434",
            llm_timeout_seconds=1.0,
            write_audit=False,
        )

        payload = UltronAssistant(settings).handle("set volume to 40 percent")

        self.assertEqual(payload["tool_call"], {"name": "set_system_volume", "arguments": {"level": 40}})
        self.assertEqual(payload["policy"]["action"], "allow")
        self.assertEqual(payload["result"]["status"], "dry_run")

    def test_phase5_text_response_is_human_readable(self) -> None:
        payload = {
            "utterance": "set volume to 40 percent",
            "source": "regex",
            "confidence": 0.76,
            "tool_call": {"name": "set_system_volume", "arguments": {"level": 40}},
            "policy": {"action": "allow", "risk_level": "low"},
            "result": {"status": "dry_run", "message": "Would set volume to 40%"},
        }

        response = format_assistant_response(payload)

        self.assertIn("Tool: set_system_volume", response)
        self.assertIn("Policy: allow", response)
        self.assertIn("Result: dry_run", response)

    def test_phase5_console_accepts_help_json_and_exit(self) -> None:
        class FakeAssistant:
            def handle(self, utterance: str, *, confirmed: bool = False) -> dict:
                return {
                    "utterance": utterance,
                    "source": "regex",
                    "confidence": 0.76,
                    "tool_call": {"name": "set_system_volume", "arguments": {"level": 40}},
                    "policy": {"action": "allow", "risk_level": "low"},
                    "result": {"status": "dry_run", "message": "Would set volume to 40%"},
                    "runtime": {"confirmed": confirmed},
                }

        output = io.StringIO()
        run_console(FakeAssistant(), input_stream=io.StringIO("/help\n/json set volume to 40 percent\n/exit\n"), output_stream=output)

        text = output.getvalue()

        self.assertIn("Commands:", text)
        self.assertIn('"tool_call"', text)
        self.assertIn("Session ended.", text)

    def test_phase6_brain_decomposes_note_goal(self) -> None:
        settings = RuntimeSettings(
            dataset_path=Path("data/jarvis_dataset_v2/jarvis_laptop_commands_synthetic_v2.jsonl"),
            audit_log=Path(".ultron/test-audit.jsonl"),
            workspace=Path("."),
            dry_run=True,
            safe_roots=(Path("."),),
            app_aliases=None,
            screenshot_dir=Path(".ultron/screenshots"),
            planner_mode="rules",
            llm_model="unused",
            llm_endpoint="http://localhost:11434",
            llm_timeout_seconds=1.0,
            write_audit=False,
        )

        task = UltronBrain(UltronAssistant(settings)).plan(
            "Create a note called project ideas and add that I should test voice mode next."
        )

        self.assertEqual(task.classification, "multi_step")
        self.assertEqual(len(task.steps), 2)
        self.assertEqual(task.steps[0].tool_call["name"], "create_note")
        self.assertEqual(task.steps[1].tool_call["name"], "append_to_note")

    def test_phase6_brain_executes_safe_multistep_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            settings = RuntimeSettings(
                dataset_path=Path("data/jarvis_dataset_v2/jarvis_laptop_commands_synthetic_v2.jsonl"),
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
                write_audit=False,
            )

            task = UltronBrain(UltronAssistant(settings), memory_path=workspace / ".ultron" / "memory.json").execute(
                "Create a note called project ideas and add that I should test voice mode next."
            )

            self.assertEqual(task.status, TaskState.COMPLETED)
            note = workspace / "notes" / "project_ideas.md"
            self.assertTrue(note.exists())
            self.assertEqual(note.read_text(encoding="utf-8").strip(), "i should test voice mode next")

    def test_phase6_brain_high_risk_waits_for_confirmation(self) -> None:
        settings = RuntimeSettings(
            dataset_path=Path("data/jarvis_dataset_v2/jarvis_laptop_commands_synthetic_v2.jsonl"),
            audit_log=Path(".ultron/test-audit.jsonl"),
            workspace=Path("."),
            dry_run=True,
            safe_roots=(Path("."),),
            app_aliases=None,
            screenshot_dir=Path(".ultron/screenshots"),
            planner_mode="rules",
            llm_model="unused",
            llm_endpoint="http://localhost:11434",
            llm_timeout_seconds=1.0,
            write_audit=False,
        )

        task = UltronBrain(UltronAssistant(settings)).execute("delete project_report.txt")

        self.assertEqual(task.status, TaskState.WAITING_FOR_CONFIRMATION)
        self.assertEqual(task.steps[0].result["status"], "confirmation_required")

    def test_phase6_memory_write_read_and_forget(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory = MemoryStore(Path(tmp) / "memory.json")

            stored = memory.remember("preferred_editor", "notepad", kind="preference")
            rejected = memory.remember("api_key", "secret value", kind="secret")

            self.assertTrue(stored)
            self.assertFalse(rejected)
            self.assertEqual(memory.list()[0]["value"], "notepad")
            self.assertEqual(memory.forget("editor"), 1)
            self.assertEqual(memory.list(), [])

    def test_phase6_brain_marks_failed_tool_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            settings = RuntimeSettings(
                dataset_path=Path("data/jarvis_dataset_v2/jarvis_laptop_commands_synthetic_v2.jsonl"),
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
                write_audit=False,
            )

            task = UltronBrain(UltronAssistant(settings), memory_path=workspace / ".ultron" / "memory.json").execute(
                "set volume to 40 percent"
            )

            self.assertEqual(task.status, TaskState.FAILED)
            self.assertEqual(task.steps[0].result["status"], "not_implemented")

    def test_phase6_brain_writes_task_audit_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            audit_path = workspace / ".ultron" / "audit.jsonl"
            settings = RuntimeSettings(
                dataset_path=Path("data/jarvis_dataset_v2/jarvis_laptop_commands_synthetic_v2.jsonl"),
                audit_log=audit_path,
                workspace=workspace,
                dry_run=True,
                safe_roots=(workspace,),
                app_aliases=None,
                screenshot_dir=workspace / ".ultron" / "screenshots",
                planner_mode="rules",
                llm_model="unused",
                llm_endpoint="http://localhost:11434",
                llm_timeout_seconds=1.0,
                write_audit=True,
            )

            UltronBrain(UltronAssistant(settings), memory_path=workspace / ".ultron" / "memory.json").execute(
                "create note project ideas"
            )

            records = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]

            self.assertTrue(any(record.get("record_type") == "brain_task" for record in records))

    def test_phase6_cli_plan_command_outputs_task_plan(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            main(["/plan create a note called ideas and add that voice mode is next", "--text", "--no-audit"])

        text = output.getvalue()

        self.assertIn("Status: pending", text)
        self.assertIn("Tool: create_note", text)
        self.assertIn("Tool: append_to_note", text)

    def test_phase7_web_state_processes_command(self) -> None:
        settings = RuntimeSettings(
            dataset_path=Path("data/jarvis_dataset_v2/jarvis_laptop_commands_synthetic_v2.jsonl"),
            audit_log=Path(".ultron/test-audit.jsonl"),
            workspace=Path("."),
            dry_run=True,
            safe_roots=(Path("."),),
            app_aliases=None,
            screenshot_dir=Path(".ultron/screenshots"),
            planner_mode="rules",
            llm_model="unused",
            llm_endpoint="http://localhost:11434",
            llm_timeout_seconds=1.0,
            write_audit=False,
        )

        state = WebState(UltronBrain(UltronAssistant(settings)))
        payload = state.command("create note visual interface")

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["visual_state"], "speaking")
        self.assertEqual(payload["task"]["steps"][0]["tool_call"]["name"], "create_note")

    def test_phase7_subtitle_toggle_updates_state(self) -> None:
        settings = RuntimeSettings(
            dataset_path=Path("data/jarvis_dataset_v2/jarvis_laptop_commands_synthetic_v2.jsonl"),
            audit_log=Path(".ultron/test-audit.jsonl"),
            workspace=Path("."),
            dry_run=True,
            safe_roots=(Path("."),),
            app_aliases=None,
            screenshot_dir=Path(".ultron/screenshots"),
            planner_mode="rules",
            llm_model="unused",
            llm_endpoint="http://localhost:11434",
            llm_timeout_seconds=1.0,
            write_audit=False,
        )

        state = WebState(UltronBrain(UltronAssistant(settings)))
        payload = state.toggle_subtitles(False)

        self.assertFalse(payload["subtitles_enabled"])
        self.assertFalse(state.subtitles_enabled)

    def test_phase7_static_ui_uses_local_three_module(self) -> None:
        app = Path("web/app.js").read_text(encoding="utf-8")
        html = Path("web/index.html").read_text(encoding="utf-8")

        self.assertIn("./vendor/three.module.min.js", app)
        self.assertIn("ultron-scene", html)
        self.assertIn("subtitleToggle", html)

    def test_phase7_api_status_and_subtitle_toggle(self) -> None:
        settings = RuntimeSettings(
            dataset_path=Path("data/jarvis_dataset_v2/jarvis_laptop_commands_synthetic_v2.jsonl"),
            audit_log=Path(".ultron/test-audit.jsonl"),
            workspace=Path("."),
            dry_run=True,
            safe_roots=(Path("."),),
            app_aliases=None,
            screenshot_dir=Path(".ultron/screenshots"),
            planner_mode="rules",
            llm_model="unused",
            llm_endpoint="http://localhost:11434",
            llm_timeout_seconds=1.0,
            write_audit=False,
        )
        state = WebState(UltronBrain(UltronAssistant(settings)))
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(state))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            status = json.loads(urlopen(base + "/api/status", timeout=5).read().decode("utf-8"))
            request = Request(
                base + "/api/subtitles/toggle",
                data=json.dumps({"enabled": False}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            toggled = json.loads(urlopen(request, timeout=5).read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()

        self.assertEqual(status["status"], "ok")
        self.assertFalse(toggled["subtitles_enabled"])


if __name__ == "__main__":
    unittest.main()
