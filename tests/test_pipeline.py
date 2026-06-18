from __future__ import annotations

import io
import json
import os
import socket
import threading
import tempfile
import unittest
from contextlib import redirect_stdout
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen

from ultron27.audit import append_audit_record, read_recent_audit_records
from ultron27.brain import MemoryStore, TaskState, UltronBrain
from ultron27.cli import main
from ultron27.console import format_assistant_response, run_console
from ultron27.config import load_config
from ultron27.conversation import ConversationManager
from ultron27.diagnostics import build_diagnostics
from ultron27.dataset_quality import DatasetRow, analyze_dataset, build_safety_cases, is_underspecified
from ultron27.executor import Executor
from ultron27.internet import WebSearchResponse, WebSearchResult
from ultron27.knowledge import KnowledgeBase
from ultron27.llm import GroqProvider, LLMPlanner, LLMPlannerError, parse_llm_tool_call
from ultron27.models import RiskLevel, ToolCall
from ultron27.planner import DatasetPlanner, regex_plan
from ultron27.policy import decide
from ultron27.runtime import RuntimeSettings, UltronAssistant
from ultron27.skills import SkillRegistry, SkillSpec, validate_skill_input
from ultron27.tools import validate_tool_call
from ultron27.voice import (
    DeepgramSTT,
    MockMicrophoneCapture,
    MockSTT,
    MockTTS,
    TextPayloadSTT,
    VoiceProviderConfig,
    VoiceSession,
    analyze_audio_payload,
    build_voice_session,
    clean_transcript,
    strip_wake_word,
)
from ultron27.wake import DoubleClapWakeProvider, EnergyVADProvider, MockVADProvider, MockWakeWordProvider, WakeGateConfig
from ultron27.web_server import WebState, make_handler
from ultron27.windows_executor import merge_windows_app_aliases, resolve_app_alias
from scripts.config_wizard import generate_config
from scripts.launch_ultron import find_open_port


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

    def test_regex_web_and_spotify_commands_use_typed_tools(self) -> None:
        web = regex_plan("search the web for weather in Delhi")
        spotify = regex_plan("play blinding lights on spotify")
        generic_spotify = regex_plan("play songs through spotify")

        self.assertEqual(web.tool_call, ToolCall("search_web", {"query": "weather in delhi"}))
        self.assertEqual(spotify.tool_call, ToolCall("play_music", {"query": "blinding lights"}))
        self.assertEqual(generic_spotify.tool_call, ToolCall("play_music", {"query": "songs"}))

    def test_assistant_reply_handles_conversation_without_blocking(self) -> None:
        state = WebState(UltronBrain(UltronAssistant(_test_settings())))

        payload = state.command("hello ultron")

        self.assertEqual(payload["route"], "chat")
        self.assertEqual(payload["task"]["status"], "completed")
        self.assertEqual(payload["task"]["steps"][0]["tool_call"]["name"], "assistant_reply")
        self.assertIn("At your service", payload["subtitle"])

    def test_audibility_check_is_chat_not_unsupported_command(self) -> None:
        state = WebState(UltronBrain(UltronAssistant(_test_settings())))

        payload = state.command("Am I audible or wrong?")

        self.assertEqual(payload["route"], "chat")
        self.assertEqual(payload["task"]["steps"][0]["tool_call"]["name"], "assistant_reply")
        self.assertIn("read your messages", payload["response"])

    def test_cortana_greeting_is_chat_not_unsupported_command(self) -> None:
        state = WebState(UltronBrain(UltronAssistant(_test_settings())))

        payload = state.command("Hey, Cortana. Hello.")

        self.assertEqual(payload["route"], "chat")
        self.assertNotIn("No safe supported tool", payload["response"])

    def test_factual_question_uses_web_search_response(self) -> None:
        state = WebState(UltronBrain(UltronAssistant(_test_settings())))
        web = WebSearchResponse(
            "success",
            "who is ada lovelace",
            "I found this on the web for who is ada lovelace:\n1. Ada Lovelace - Mathematician",
            (WebSearchResult("Ada Lovelace", "https://example.test/ada", "Mathematician and early programmer."),),
        )

        with patch("ultron27.conversation.search_web", return_value=web) as search_mock:
            payload = state.command("Who is Ada Lovelace?")

        self.assertEqual(payload["route"], "web_search")
        self.assertIn("Ada Lovelace", payload["response"])
        self.assertEqual(payload["task"]["steps"][0]["tool_call"]["name"], "assistant_reply")
        self.assertEqual(payload["task"]["steps"][0]["result"]["data"]["web"]["results"][0]["url"], "https://example.test/ada")
        search_mock.assert_called_once_with("Ada Lovelace")

    def test_conversation_manager_learns_and_forgets_safe_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _workspace_settings(Path(tmp), dry_run=True, write_audit=False)
            state = WebState(UltronBrain(UltronAssistant(settings)))

            remembered = state.command("remember that I prefer concise responses")
            memory = state.memory_status()
            forgotten = state.memory_forget("concise")

            self.assertEqual(remembered["route"], "memory_remember")
            self.assertTrue(any("concise responses" in item["value"] for item in memory["memory"]))
            self.assertEqual(forgotten["removed"], 1)
            self.assertFalse(any("concise responses" in item.get("value", "") for item in forgotten["memory"]))

    def test_conversation_memory_off_stops_new_personalization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = _workspace_settings(Path(tmp), dry_run=True, write_audit=False)
            state = WebState(UltronBrain(UltronAssistant(settings)))

            off = state.command("turn memory off")
            remembered = state.command("remember that I prefer long reports")

            self.assertEqual(off["route"], "memory_toggle")
            self.assertFalse(remembered["memory_enabled"])
            self.assertIn("did not store", remembered["response"])
            self.assertFalse(any("long reports" in item.get("value", "") for item in state.memory_status()["memory"]))

    def test_conversation_high_risk_still_requires_confirmation(self) -> None:
        manager = ConversationManager(UltronBrain(UltronAssistant(_test_settings())))

        payload = manager.handle("delete project_report.txt")

        self.assertEqual(payload["route"], "command")
        self.assertTrue(payload["needs_confirmation"])
        self.assertEqual(payload["task"]["status"], "waiting_for_confirmation")

    def test_web_and_spotify_executor_open_safe_urls(self) -> None:
        executor = Executor(dry_run=False)

        with patch("webbrowser.open", return_value=True) as open_mock:
            web = executor.execute(ToolCall("search_web", {"query": "ultron project"}))
            spotify = executor.execute(ToolCall("play_music", {"query": "lofi beats"}))

        self.assertEqual(web.status, "success")
        self.assertEqual(spotify.status, "success")
        opened_urls = [call.args[0] for call in open_mock.call_args_list]
        self.assertTrue(any(url.startswith("https://www.google.com/search?") for url in opened_urls))
        self.assertTrue(any(url.startswith("spotify:search:") for url in opened_urls))

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

    def test_phase15_regex_handles_flexible_open_app_phrasing(self) -> None:
        phrases = ["launch notepad", "bring up notepad", "start the notes app", "launch the basic text editor"]

        plans = [regex_plan(phrase) for phrase in phrases]

        self.assertTrue(all(plan.tool_call == ToolCall("open_application", {"app": "notepad"}) for plan in plans))
        self.assertTrue(all(plan.source == "regex" for plan in plans))

    def test_phase15_llm_low_confidence_asks_clarification(self) -> None:
        class FakeProvider:
            def complete(self, prompt: str, timeout: float) -> str:
                return '{"intent":"open_app","tool_name":"open_application","tool_arguments":{"app":"notepad"},"confidence":0.2}'

        plan = LLMPlanner(FakeProvider()).plan("maybe notes maybe not")

        self.assertEqual(plan.tool_call.name, "ask_clarification")
        self.assertEqual(plan.intent, "clarify_intent")
        self.assertEqual(plan.risk_level.value, "none")
        self.assertNotIn("I heard", plan.tool_call.arguments["question"])

    def test_phase15_llm_explicit_clarification_payload_is_supported(self) -> None:
        call, intent, confidence = parse_llm_tool_call(
            '{"intent":"clarify_intent","tool_name":"ask_clarification","tool_arguments":{"question":"What text should I write in Notepad?"},"confidence":0.72,"needs_clarification":true,"clarification_question":"What text should I write in Notepad?"}'
        )

        self.assertEqual(call, ToolCall("ask_clarification", {"question": "What text should I write in Notepad?"}))
        self.assertEqual(intent, "clarify_intent")
        self.assertEqual(confidence, 0.72)

    def test_phase15_llm_parser_strips_thinking_blocks(self) -> None:
        call, intent, confidence = parse_llm_tool_call(
            '<think>I should not be visible.</think>{"intent":"open_app","tool_name":"open_application","tool_arguments":{"app":"notepad"},"confidence":0.87}'
        )

        self.assertEqual(call, ToolCall("open_application", {"app": "notepad"}))
        self.assertEqual(intent, "open_app")
        self.assertEqual(confidence, 0.87)

    def test_phase15_mock_llm_maps_flexible_music_phrase(self) -> None:
        class FakeProvider:
            def complete(self, prompt: str, timeout: float) -> str:
                self.prompt = prompt
                return '{"intent":"play_music","tool_name":"play_music","tool_arguments":{"query":"lofi music"},"confidence":0.78}'

        provider = FakeProvider()
        plan = LLMPlanner(provider).plan("put on some lofi music")

        self.assertEqual(plan.tool_call, ToolCall("play_music", {"query": "lofi music"}))
        self.assertIn("put on some lofi music", provider.prompt)

    def test_phase15_hybrid_llm_unavailable_falls_back_safely(self) -> None:
        settings = RuntimeSettings(
            dataset_path=Path("data/jarvis_dataset_v2/jarvis_laptop_commands_synthetic_v2.jsonl"),
            audit_log=Path(".ultron/test-audit.jsonl"),
            workspace=Path("."),
            dry_run=True,
            safe_roots=(Path("."),),
            app_aliases=None,
            screenshot_dir=Path(".ultron/screenshots"),
            planner_mode="hybrid",
            llm_model="unused",
            llm_endpoint="http://localhost:11434",
            llm_timeout_seconds=1.0,
            write_audit=False,
        )
        assistant = UltronAssistant(settings)

        with patch("ultron27.runtime.make_ollama_router", side_effect=LLMPlannerError("Ollama unavailable")):
            payload = assistant.handle("do a completely unknown assistant task")

        self.assertEqual(payload["tool_call"]["name"], "unsupported_request")
        self.assertTrue(payload["runtime"]["llm"]["attempted"])
        self.assertIn("Ollama unavailable", payload["runtime"]["llm"]["error"])

    def test_hybrid_groq_retries_unknown_open_app_alias(self) -> None:
        class FakeRouter:
            def route(self, utterance: str):
                self.utterance = utterance
                return regex_plan("open notepad")

        settings = RuntimeSettings(
            dataset_path=Path("data/jarvis_dataset_v2/jarvis_laptop_commands_synthetic_v2.jsonl"),
            audit_log=Path(".ultron/test-audit.jsonl"),
            workspace=Path("."),
            dry_run=True,
            safe_roots=(Path("."),),
            app_aliases=None,
            screenshot_dir=Path(".ultron/screenshots"),
            planner_mode="hybrid",
            llm_model="unused",
            llm_endpoint="https://api.groq.com/openai/v1",
            llm_timeout_seconds=1.0,
            llm_provider="groq",
            write_audit=False,
        )
        router = FakeRouter()

        with patch("ultron27.runtime.make_groq_router", return_value=router) as mocked:
            payload = UltronAssistant(settings).handle("launch the simple writing program")

        self.assertTrue(mocked.called)
        self.assertEqual(router.utterance, "launch the simple writing program")
        self.assertEqual(payload["tool_call"], {"name": "open_application", "arguments": {"app": "notepad"}})
        self.assertTrue(payload["runtime"]["llm"]["attempted"])

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

    def test_groq_provider_parses_openai_compatible_response(self) -> None:
        class FakeResponse:
            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps(
                    {
                        "choices": [
                            {
                                "message": {
                                    "content": '{"intent":"open_app","tool_name":"open_application","tool_arguments":{"app":"notepad"},"confidence":0.92}'
                                }
                            }
                        ]
                    }
                ).encode("utf-8")

        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}), patch("urllib.request.urlopen", return_value=FakeResponse()) as mocked:
            content = GroqProvider(endpoint="https://api.groq.com/openai/v1", model="test-model").complete("open notepad", 2)

        self.assertIn('"tool_name":"open_application"', content)
        request = mocked.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.groq.com/openai/v1/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")

    def test_config_accepts_groq_and_deepgram_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "ultron.config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "planner_mode": "hybrid",
                        "llm_provider": "groq",
                        "llm_model": "openai/gpt-oss-20b",
                        "llm_endpoint": "https://api.groq.com/openai/v1",
                        "voice_stt_provider": "deepgram",
                        "voice_stt_model": "nova-3",
                    }
                ),
                encoding="utf-8",
            )

            config = load_config(config_path, environ={}, base_dir=root)

            self.assertEqual(config.llm_provider, "groq")
            self.assertEqual(config.llm_endpoint, "https://api.groq.com/openai/v1")
            self.assertEqual(config.voice_stt_provider, "deepgram")
            self.assertEqual(config.voice_stt_model, "nova-3")

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

    def test_phase8_voice_transcript_executes_command(self) -> None:
        state = WebState(UltronBrain(UltronAssistant(_test_settings())))

        payload = state.voice_transcribe({"transcript": "ULTRON, create note voice demo"})

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["transcript"]["text"], "create note voice demo")
        self.assertEqual(payload["visual_state"], "speaking")
        self.assertEqual(payload["task"]["steps"][0]["tool_call"]["name"], "create_note")
        self.assertEqual(payload["history"][0]["tool_selected"], "create_note")

    def test_phase8_high_risk_voice_command_requires_confirmation(self) -> None:
        state = WebState(UltronBrain(UltronAssistant(_test_settings())))

        payload = state.voice_transcribe({"transcript": "ULTRON, delete project_report.txt"})

        self.assertTrue(payload["needs_confirmation"])
        self.assertEqual(payload["task"]["status"], "waiting_for_confirmation")
        self.assertEqual(payload["voice"]["pending_confirmation_goal"], "delete project_report.txt")
        self.assertIn("yes confirm", payload["spoken_response"])

        confirmed = state.voice_transcribe({"transcript": "yes confirm"})

        self.assertTrue(confirmed["confirmed"])
        self.assertNotEqual(confirmed["task"]["status"], "waiting_for_confirmation")

    def test_phase8_tts_response_generated(self) -> None:
        tts = MockTTS()
        state = WebState(UltronBrain(UltronAssistant(_test_settings())), voice=VoiceSession(tts=tts))

        payload = state.speak({"text": "Done. I created the note demo."})

        self.assertEqual(tts.spoken, ["Done. I created the note demo."])
        self.assertEqual(payload["speech"]["status"], "spoken")
        self.assertTrue(payload["voice"]["speaking"])

    def test_phase8_mute_disables_speaking(self) -> None:
        tts = MockTTS()
        state = WebState(UltronBrain(UltronAssistant(_test_settings())), voice=VoiceSession(tts=tts))
        state.voice.set_muted(True)

        payload = state.speak({"text": "This should not be spoken."})

        self.assertEqual(tts.spoken, [])
        self.assertEqual(payload["status"], "muted")
        self.assertFalse(payload["voice"]["speaking"])

    def test_phase8_voice_subtitles_update_and_toggle_still_works(self) -> None:
        state = WebState(UltronBrain(UltronAssistant(_test_settings())))

        payload = state.voice_transcribe({"transcript": "create note subtitles"})
        toggled = state.toggle_subtitles(False)

        self.assertNotIn("You said:", payload["last_subtitle"])
        self.assertNotIn("Understood:", payload["last_subtitle"])
        self.assertNotIn("ULTRON:", payload["last_subtitle"])
        self.assertIn("note", payload["last_subtitle"].lower())
        self.assertFalse(toggled["subtitles_enabled"])

    def test_phase8_empty_voice_input_does_not_execute(self) -> None:
        state = WebState(UltronBrain(UltronAssistant(_test_settings())))

        payload = state.voice_transcribe({"transcript": "   "})

        self.assertEqual(payload["status"], "empty")
        self.assertEqual(payload["visual_state"], "listening")
        self.assertEqual(payload["last_task"], None)
        self.assertEqual(payload["history"], [])

    def test_voice_low_confidence_transcript_asks_for_clarification(self) -> None:
        state = WebState(UltronBrain(UltronAssistant(_test_settings())))

        payload = state.voice_transcribe({"transcript": "delete project report", "confidence": 0.2})

        self.assertEqual(payload["status"], "clarification_required")
        self.assertEqual(payload["last_task"], None)
        self.assertNotIn("I heard", payload["spoken_response"])
        self.assertIn("not fully sure", payload["spoken_response"])
        self.assertEqual(payload["history"][0]["action_result"], "clarification_required")

    def test_phase8_voice_api_endpoints(self) -> None:
        state = WebState(UltronBrain(UltronAssistant(_test_settings())))
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(state))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            started = json.loads(
                urlopen(
                    Request(
                        base + "/api/voice/start",
                        data=json.dumps({"push_to_talk": True}).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    ),
                    timeout=5,
                )
                .read()
                .decode("utf-8")
            )
            transcribed = json.loads(
                urlopen(
                    Request(
                        base + "/api/voice/transcribe",
                        data=json.dumps({"transcript": "ULTRON, create note api voice"}).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    ),
                    timeout=5,
                )
                .read()
                .decode("utf-8")
            )
            status = json.loads(urlopen(base + "/api/voice/status", timeout=5).read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()

        self.assertEqual(started["visual_state"], "listening")
        self.assertEqual(transcribed["task"]["steps"][0]["tool_call"]["name"], "create_note")
        self.assertEqual(status["status"], "ok")

    def test_voice_session_defaults_to_continuous_listening(self) -> None:
        state = WebState(UltronBrain(UltronAssistant(_test_settings())))

        payload = state.voice_status()

        self.assertFalse(payload["voice"]["push_to_talk"])

    def test_blocked_command_summary_is_actionable(self) -> None:
        state = WebState(UltronBrain(UltronAssistant(_test_settings())))

        payload = state.command("do something impossible and unsafe")

        self.assertEqual(payload["task"]["status"], "blocked")
        self.assertIn("I do not have a safe tool", payload["subtitle"])
        self.assertIn("create a note", payload["subtitle"])

    def test_phase9_config_accepts_voice_provider_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "ultron.config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "voice_stt_provider": "faster_whisper",
                        "voice_tts_provider": "piper",
                        "voice_stt_model_path": "models/whisper",
                        "voice_tts_model_path": "models/piper.onnx",
                        "voice_tts_voice_path": "models/piper.json",
                        "voice_device": "cpu",
                        "voice_identity": "ULTRON-local",
                        "voice_rate": 0.86,
                        "voice_pitch": 0.7,
                        "voice_volume": 0.8,
                    }
                ),
                encoding="utf-8",
            )

            config = load_config(
                config_path,
                environ={"ULTRON_TTS_PROVIDER": "pyttsx3", "ULTRON_VOICE_RATE": "1.05"},
                base_dir=root,
            )

            self.assertEqual(config.voice_stt_provider, "faster_whisper")
            self.assertEqual(config.voice_tts_provider, "pyttsx3")
            self.assertEqual(config.voice_stt_model_path, root / "models" / "whisper")
            self.assertEqual(config.voice_tts_model_path, root / "models" / "piper.onnx")
            self.assertEqual(config.voice_tts_voice_path, root / "models" / "piper.json")
            self.assertEqual(config.voice_identity, "ULTRON-local")
            self.assertEqual(config.voice_rate, 1.05)

    def test_deepgram_stt_parses_prerecorded_audio_response(self) -> None:
        class FakeResponse:
            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps(
                    {
                        "results": {
                            "channels": [
                                {
                                    "alternatives": [
                                        {"transcript": "open notepad", "confidence": 0.91}
                                    ]
                                }
                            ]
                        }
                    }
                ).encode("utf-8")

        with tempfile.TemporaryDirectory() as tmp:
            audio_path = Path(tmp) / "sample.wav"
            audio_path.write_bytes(b"RIFF....WAVEfmt ")

            with patch.dict(os.environ, {"DEEPGRAM_API_KEY": "test-key"}), patch("urllib.request.urlopen", return_value=FakeResponse()) as mocked:
                result = DeepgramSTT(model_name="nova-3").transcribe({"audio_path": str(audio_path)})

        self.assertEqual(result.text, "open notepad")
        self.assertEqual(result.provider, "deepgram")
        self.assertAlmostEqual(result.confidence, 0.91)
        request = mocked.call_args.args[0]
        self.assertIn("https://api.deepgram.com/v1/listen?model=nova-3", request.full_url)
        self.assertEqual(request.get_header("Authorization"), "Token test-key")

    def test_deepgram_stt_reports_missing_key_as_unavailable(self) -> None:
        with patch("ultron27.voice.get_secret", return_value=""):
            health = DeepgramSTT(model_name="nova-3").health()

        self.assertFalse(health.available)
        self.assertEqual(health.fallback_to, "browser")

    def test_phase9_missing_local_voice_models_fall_back_gracefully(self) -> None:
        class Config:
            voice_stt_provider = "faster_whisper"
            voice_tts_provider = "piper"
            voice_stt_model_path = None
            voice_tts_model_path = None
            voice_tts_voice_path = None
            voice_device = "cpu"
            voice_identity = "ULTRON"
            voice_rate = 0.92
            voice_pitch = 0.72
            voice_volume = 0.95

        session = build_voice_session(Config())
        providers = session.providers_status()

        self.assertEqual(providers["configured"]["stt"], "faster_whisper")
        self.assertEqual(providers["configured"]["tts"], "piper")
        self.assertEqual(providers["active"]["stt"], "browser")
        self.assertEqual(providers["active"]["tts"], "browser_speech_synthesis")
        self.assertFalse(providers["providers"]["stt"]["available"])
        self.assertFalse(providers["providers"]["tts"]["available"])

    def test_phase9_mocked_stt_tts_provider_selection(self) -> None:
        tts = MockTTS()
        session = VoiceSession(
            stt=MockSTT("ULTRON, create note provider test"),
            tts=tts,
            configured_stt=MockSTT(),
            configured_tts=tts,
            provider_config=VoiceProviderConfig(stt_provider="mock", tts_provider="mock", voice_identity="ULTRON-test"),
        )

        stt_payload = session.test_stt({})
        tts_payload = session.test_tts("Done.")

        self.assertEqual(stt_payload["transcript"]["text"], "create note provider test")
        self.assertEqual(stt_payload["transcript"]["provider"], "mock_stt")
        self.assertEqual(tts_payload["speech"]["provider"], "mock_tts")
        self.assertEqual(tts.spoken, ["Done."])
        self.assertEqual(tts_payload["speech"]["voice"], "ULTRON-test")

    def test_backend_capture_is_one_shot_and_turns_microphone_off(self) -> None:
        session = VoiceSession(
            stt=MockSTT("ULTRON, create note backend once"),
            tts=MockTTS(),
            capture=MockMicrophoneCapture("ULTRON, create note backend once"),
            configured_capture=MockMicrophoneCapture(),
        )
        state = WebState(UltronBrain(UltronAssistant(_test_settings())), voice=session)

        payload = state.voice_capture({})

        self.assertEqual(payload["status"], "ok")
        self.assertFalse(payload["voice"]["microphone_enabled"])
        self.assertEqual(payload["voice_diagnostics"]["capture_provider"], "mock_capture")

    def test_voice_calibration_updates_energy_vad_threshold(self) -> None:
        vad = EnergyVADProvider(0.015)
        session = VoiceSession(
            capture=MockMicrophoneCapture(),
            configured_capture=MockMicrophoneCapture(),
            vad=vad,
            configured_vad=vad,
        )
        state = WebState(UltronBrain(UltronAssistant(_test_settings())), voice=session)

        payload = state.voice_calibrate({"audio_energy": 0.04, "seconds": 1})

        self.assertEqual(payload["status"], "ok")
        self.assertAlmostEqual(vad.threshold, 0.018, places=3)
        self.assertEqual(payload["voice_diagnostics"]["status"], "calibrated")

    def test_phase9_voice_provider_api_endpoints(self) -> None:
        tts = MockTTS()
        state = WebState(
            UltronBrain(UltronAssistant(_test_settings())),
            voice=VoiceSession(
                stt=MockSTT("ULTRON, create note api provider"),
                tts=tts,
                configured_stt=MockSTT(),
                configured_tts=tts,
                provider_config=VoiceProviderConfig(stt_provider="mock", tts_provider="mock"),
            ),
        )
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(state))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            providers = json.loads(urlopen(base + "/api/voice/providers", timeout=5).read().decode("utf-8"))
            stt = json.loads(
                urlopen(
                    Request(
                        base + "/api/voice/test-stt",
                        data=json.dumps({}).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    ),
                    timeout=5,
                )
                .read()
                .decode("utf-8")
            )
            tts_payload = json.loads(
                urlopen(
                    Request(
                        base + "/api/voice/test-tts",
                        data=json.dumps({"text": "Provider API test."}).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    ),
                    timeout=5,
                )
                .read()
                .decode("utf-8")
            )
        finally:
            server.shutdown()
            server.server_close()

        self.assertEqual(providers["active"]["stt"], "mock_stt")
        self.assertEqual(providers["active"]["tts"], "mock_tts")
        self.assertEqual(stt["transcript"]["text"], "create note api provider")
        self.assertEqual(tts_payload["speech"]["provider"], "mock_tts")

    def test_phase10_wake_word_detected_enters_listening(self) -> None:
        state = WebState(UltronBrain(UltronAssistant(_test_settings())))

        state.wake_start()
        payload = state.wake_process({"transcript": "ULTRON", "audio_energy": 0.8})

        self.assertEqual(payload["status"], "wake_detected")
        self.assertEqual(payload["wake"]["mode"], "listening")
        self.assertEqual(payload["visual_state"], "listening")
        self.assertIsNone(payload["last_task"])

    def test_phase10_config_accepts_wake_and_vad_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "ultron.config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "wake_word_provider": "openwakeword",
                        "wake_phrases": ["ULTRON", "Hey ULTRON"],
                        "wake_model_path": "models/wake.onnx",
                        "vad_provider": "silero",
                        "vad_energy_threshold": 0.025,
                    }
                ),
                encoding="utf-8",
            )

            config = load_config(
                config_path,
                environ={"ULTRON_WAKE_WORD_PROVIDER": "text", "ULTRON_VAD_PROVIDER": "energy"},
                base_dir=root,
            )

            self.assertEqual(config.wake_word_provider, "text")
            self.assertEqual(config.wake_phrases, ("ULTRON", "Hey ULTRON"))
            self.assertEqual(config.wake_model_path, root / "models" / "wake.onnx")
            self.assertEqual(config.vad_provider, "energy")
            self.assertEqual(config.vad_energy_threshold, 0.025)

    def test_phase10_config_accepts_double_clap_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "ultron.config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "wake_word_provider": "double_clap",
                        "clap_spike_ratio": 5.5,
                        "clap_min_gap_s": 0.08,
                        "clap_max_gap_s": 0.42,
                        "clap_cooldown_s": 0.6,
                    }
                ),
                encoding="utf-8",
            )

            config = load_config(config_path, environ={}, base_dir=root)

            self.assertEqual(config.wake_word_provider, "double_clap")
            self.assertEqual(config.clap_spike_ratio, 5.5)
            self.assertEqual(config.clap_min_gap_s, 0.08)
            self.assertEqual(config.clap_max_gap_s, 0.42)
            self.assertEqual(config.clap_cooldown_s, 0.6)

    def test_phase10_double_clap_provider_detects_second_spike(self) -> None:
        config = WakeGateConfig(wake_word_provider="double_clap")
        provider = DoubleClapWakeProvider(config)

        first = provider.detect({"audio_energy": 0.05, "timestamp_s": 1.0})
        provider.detect({"audio_energy": 0.001, "timestamp_s": 1.10})
        second = provider.detect({"audio_energy": 0.05, "timestamp_s": 1.20})

        self.assertFalse(first.detected)
        self.assertTrue(second.detected)
        self.assertEqual(second.phrase, "double_clap")
        self.assertEqual(second.provider, "double_clap")

    def test_phase10_double_clap_wake_gate_enters_listening_without_command(self) -> None:
        config = WakeGateConfig(wake_word_provider="double_clap")
        wake = DoubleClapWakeProvider(config)
        vad = EnergyVADProvider(0.015)
        state = WebState(
            UltronBrain(UltronAssistant(_test_settings())),
            voice=VoiceSession(
                wake=wake,
                vad=vad,
                configured_wake=wake,
                configured_vad=vad,
                wake_config=config,
            ),
        )

        state.wake_start()
        first = state.wake_process({"audio_energy": 0.05, "timestamp_s": 1.0})
        quiet = state.wake_process({"audio_energy": 0.001, "timestamp_s": 1.10})
        second = state.wake_process({"audio_energy": 0.05, "timestamp_s": 1.20})

        self.assertEqual(first["status"], "ignored")
        self.assertEqual(quiet["status"], "ignored")
        self.assertEqual(second["status"], "wake_detected")
        self.assertEqual(second["wake"]["mode"], "listening")
        self.assertFalse(second["command_executed"])

    def test_phase10_no_wake_word_does_not_execute(self) -> None:
        state = WebState(UltronBrain(UltronAssistant(_test_settings())))

        state.wake_start()
        payload = state.wake_process({"transcript": "create note ignored background speech", "audio_energy": 0.8})

        self.assertEqual(payload["status"], "ignored")
        self.assertFalse(payload["command_executed"])
        self.assertEqual(payload["wake"]["mode"], "waiting_for_wake_word")
        self.assertIsNone(payload["last_task"])
        self.assertEqual(payload["history"], [])

    def test_phase10_noisy_audio_is_ignored(self) -> None:
        state = WebState(UltronBrain(UltronAssistant(_test_settings())))

        state.wake_start()
        payload = state.wake_process({"transcript": "   ", "audio_energy": 0.0})

        self.assertEqual(payload["status"], "ignored")
        self.assertTrue(payload["wake"]["noisy_ignored"])
        self.assertFalse(payload["command_executed"])
        self.assertIsNone(payload["last_task"])

    def test_phase10_vad_speech_segment_calls_stt_after_wake(self) -> None:
        class CountingSTT(TextPayloadSTT):
            def __init__(self) -> None:
                self.calls = 0

            def transcribe(self, payload: dict) -> object:
                self.calls += 1
                return super().transcribe(payload)

        stt = CountingSTT()
        state = WebState(
            UltronBrain(UltronAssistant(_test_settings())),
            voice=VoiceSession(
                stt=stt,
                wake=MockWakeWordProvider(),
                vad=MockVADProvider(speech=True),
                configured_wake=MockWakeWordProvider(),
                configured_vad=MockVADProvider(speech=True),
                wake_config=WakeGateConfig(wake_word_provider="mock", vad_provider="mock"),
            ),
        )

        state.wake_start()
        payload = state.wake_process({"transcript": "ULTRON, create note wake test", "audio_energy": 0.9})

        self.assertEqual(stt.calls, 1)
        self.assertTrue(payload["command_executed"])
        self.assertEqual(payload["task"]["steps"][0]["tool_call"]["name"], "create_note")

    def test_phase10_wake_voice_safety_behavior_is_unchanged(self) -> None:
        state = WebState(UltronBrain(UltronAssistant(_test_settings())))

        state.wake_start()
        payload = state.wake_process({"transcript": "Hey ULTRON, delete project_report.txt", "audio_energy": 0.8})

        self.assertTrue(payload["needs_confirmation"])
        self.assertEqual(payload["task"]["status"], "waiting_for_confirmation")
        self.assertEqual(payload["voice"]["pending_confirmation_goal"], "delete project_report.txt")

    def test_phase10_wake_api_endpoints(self) -> None:
        state = WebState(UltronBrain(UltronAssistant(_test_settings())))
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(state))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            started = json.loads(
                urlopen(
                    Request(
                        base + "/api/wake/start",
                        data=json.dumps({}).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    ),
                    timeout=5,
                )
                .read()
                .decode("utf-8")
            )
            status = json.loads(urlopen(base + "/api/wake/status", timeout=5).read().decode("utf-8"))
            ignored = json.loads(
                urlopen(
                    Request(
                        base + "/api/wake/process",
                        data=json.dumps({"transcript": "background speech", "audio_energy": 0.8}).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    ),
                    timeout=5,
                )
                .read()
                .decode("utf-8")
            )
            stopped = json.loads(
                urlopen(
                    Request(
                        base + "/api/wake/stop",
                        data=json.dumps({}).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    ),
                    timeout=5,
                )
                .read()
                .decode("utf-8")
            )
        finally:
            server.shutdown()
            server.server_close()

        self.assertEqual(started["wake"]["mode"], "waiting_for_wake_word")
        self.assertTrue(status["wake"]["always_listening"])
        self.assertEqual(ignored["status"], "ignored")
        self.assertEqual(stopped["wake"]["mode"], "inactive")

    def test_phase11_safe_root_blocks_explicit_outside_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            allowed = workspace / "allowed"
            outside = workspace / "outside"
            allowed.mkdir()
            outside.mkdir()
            outside_file = outside / "secret.txt"
            outside_file.write_text("nope", encoding="utf-8")

            executor = Executor(dry_run=False, workspace=workspace, safe_roots=(allowed,))

            opened = executor.execute(ToolCall("open_file", {"file_name": str(outside_file)}))
            searched = executor.execute(ToolCall("search_files", {"query": "secret", "folder": str(outside)}))

            self.assertEqual(opened.status, "blocked")
            self.assertEqual(searched.status, "blocked")

    def test_phase11_windows_app_alias_resolution_is_allowlisted(self) -> None:
        aliases = merge_windows_app_aliases({"editor": "notepad.exe", "bad": "cmd.exe && whoami"})

        self.assertEqual(resolve_app_alias("Chrome", aliases), "chrome.exe")
        self.assertEqual(resolve_app_alias("editor", aliases), "notepad.exe")
        self.assertIsNone(resolve_app_alias("bad", aliases))
        self.assertIsNone(resolve_app_alias("unknown app", aliases))

    def test_phase11_cursor_alias_is_available_without_raw_shell(self) -> None:
        aliases = merge_windows_app_aliases()

        target = resolve_app_alias("cursor", aliases)

        self.assertIsNotNone(target)
        self.assertNotIn("&&", target or "")
        self.assertNotIn("|", target or "")

    def test_phase11_medium_risk_terminal_requires_confirmation(self) -> None:
        plan = regex_plan("open terminal")
        decision = decide(plan, validate_tool_call(plan.tool_call))
        payload = UltronAssistant(_test_settings()).handle("open terminal")

        self.assertEqual(plan.tool_call.name, "open_terminal")
        self.assertEqual(decision.action, "confirm")
        self.assertEqual(decision.permission_level, "medium_risk_confirmation")
        self.assertEqual(payload["tool_call"]["name"], "open_terminal")
        self.assertEqual(payload["policy"]["action"], "confirm")

    def test_phase11_destructive_action_remains_unimplemented_after_confirmation(self) -> None:
        plan = regex_plan("delete project_report.txt")
        decision = decide(plan, validate_tool_call(plan.tool_call), confirmed=True)
        result = Executor(dry_run=False).execute(plan.tool_call)

        self.assertEqual(decision.action, "allow")
        self.assertEqual(decision.permission_level, "destructive_blocked_or_not_implemented")
        self.assertEqual(result.status, "not_implemented")

    def test_phase11_audit_reader_returns_recent_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            audit_path = Path(tmp) / "audit.jsonl"
            append_audit_record({"utterance": "first"}, audit_path)
            append_audit_record({"utterance": "second"}, audit_path)

            records = read_recent_audit_records(audit_path, limit=1)

            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["utterance"], "second")

    def test_phase11_audit_recent_api_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            settings = RuntimeSettings(
                dataset_path=Path("data/jarvis_dataset_v2/jarvis_laptop_commands_synthetic_v2.jsonl"),
                audit_log=workspace / ".ultron" / "audit.jsonl",
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
            state = WebState(UltronBrain(UltronAssistant(settings)))
            state.command("open notepad")
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(state))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_address[1]}"
                payload = json.loads(urlopen(base + "/api/audit/recent?limit=5", timeout=5).read().decode("utf-8"))
            finally:
                server.shutdown()
                server.server_close()

            self.assertEqual(payload["status"], "ok")
            self.assertTrue(payload["records"])
            self.assertTrue(any(record.get("utterance") == "open notepad" for record in payload["records"]))

    def test_phase12_skill_schema_validation(self) -> None:
        registry = SkillRegistry.with_builtins(
            UltronAssistant(_test_settings()),
            KnowledgeBase(Path(".ultron/test-knowledge.json"), workspace=Path("."), safe_roots=(Path("."),)),
        )
        spec = registry.specs["notes"]

        validation = validate_skill_input(spec, {"action": "create"})

        self.assertFalse(validation.valid)
        self.assertIn("Missing required input: title", validation.errors)

    def test_phase12_unknown_skill_is_rejected(self) -> None:
        registry = SkillRegistry.with_builtins(
            UltronAssistant(_test_settings()),
            KnowledgeBase(Path(".ultron/test-knowledge.json"), workspace=Path("."), safe_roots=(Path("."),)),
        )

        result = registry.run("unknown_skill", {})

        self.assertEqual(result["status"], "unknown_skill")

    def test_phase12_notes_skill_runs_through_safe_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            assistant = UltronAssistant(_workspace_settings(workspace, dry_run=False, write_audit=False))
            knowledge = KnowledgeBase(workspace / ".ultron" / "knowledge.json", workspace=workspace, safe_roots=(workspace,))
            registry = SkillRegistry.with_builtins(assistant, knowledge)

            result = registry.run("notes", {"action": "create", "title": "phase twelve", "content": "skills work"})

            self.assertEqual(result["status"], "success")
            self.assertTrue((workspace / "notes" / "phase_twelve.md").exists())
            self.assertEqual(result["result"]["runtime"]["tool_call"]["name"], "create_note")
            self.assertEqual(result["result"]["runtime"]["policy"]["action"], "allow")

    def test_phase12_knowledge_ingest_and_search(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            source = workspace / "phase12.md"
            source.write_text("Phase 12 adds reusable skills and a local knowledge base for project planning.", encoding="utf-8")
            knowledge = KnowledgeBase(workspace / ".ultron" / "knowledge.json", workspace=workspace, safe_roots=(workspace,))

            ingest = knowledge.ingest(source)
            search = knowledge.search("reusable skills", limit=3)

            self.assertEqual(ingest["status"], "ok")
            self.assertEqual(search["status"], "ok")
            self.assertEqual(search["matches"][0]["title"], "phase12")

    def test_phase12_knowledge_rejects_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            source = workspace / "secret.txt"
            source.write_text("api_key = do-not-store-this", encoding="utf-8")
            knowledge = KnowledgeBase(workspace / ".ultron" / "knowledge.json", workspace=workspace, safe_roots=(workspace,))

            ingest = knowledge.ingest(source)

            self.assertEqual(ingest["status"], "rejected_sensitive")
            self.assertEqual(knowledge.sources(), [])

    def test_phase12_skill_policy_still_blocks_unconfirmed_medium_skill(self) -> None:
        registry = SkillRegistry.with_builtins(
            UltronAssistant(_test_settings()),
            KnowledgeBase(Path(".ultron/test-knowledge.json"), workspace=Path("."), safe_roots=(Path("."),)),
        )
        registry.register(
            SkillSpec(
                name="medium_test",
                description="A medium-risk test skill.",
                input_schema={"required": {"value": {"type": "string"}}, "optional": {}},
                risk_level=RiskLevel.MEDIUM,
            ),
            lambda _registry, _payload, _confirmed: {"status": "ok"},
        )

        result = registry.run("medium_test", {"value": "safe text"})

        self.assertEqual(result["status"], "confirmation_required")
        self.assertEqual(result["policy"]["permission_level"], "medium_risk_confirmation")

    def test_phase12_skills_and_knowledge_api_endpoints(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            source = workspace / "project.txt"
            source.write_text("ULTRON skills can summarize local project knowledge.", encoding="utf-8")
            assistant = UltronAssistant(_workspace_settings(workspace, dry_run=True, write_audit=False))
            knowledge = KnowledgeBase(workspace / ".ultron" / "knowledge.json", workspace=workspace, safe_roots=(workspace,))
            state = WebState(UltronBrain(assistant), knowledge=knowledge, skills=SkillRegistry.with_builtins(assistant, knowledge))
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(state))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_address[1]}"
                skills = json.loads(urlopen(base + "/api/skills", timeout=5).read().decode("utf-8"))
                ingest = json.loads(
                    urlopen(
                        Request(
                            base + "/api/knowledge/ingest",
                            data=json.dumps({"path": str(source)}).encode("utf-8"),
                            headers={"Content-Type": "application/json"},
                            method="POST",
                        ),
                        timeout=5,
                    )
                    .read()
                    .decode("utf-8")
                )
                search = json.loads(urlopen(base + "/api/knowledge/search?query=skills", timeout=5).read().decode("utf-8"))
                skill_run = json.loads(
                    urlopen(
                        Request(
                            base + "/api/skills/run",
                            data=json.dumps({"name": "project_summary", "input": {"query": "skills"}}).encode("utf-8"),
                            headers={"Content-Type": "application/json"},
                            method="POST",
                        ),
                        timeout=5,
                    )
                    .read()
                    .decode("utf-8")
                )
            finally:
                server.shutdown()
                server.server_close()

            self.assertEqual(skills["status"], "ok")
            self.assertTrue(any(skill["name"] == "notes" for skill in skills["skills"]))
            self.assertEqual(ingest["status"], "ok")
            self.assertEqual(search["knowledge"]["matches"][0]["title"], "project")
            self.assertEqual(skill_run["status"], "ok")

    def test_phase13_diagnostics_snapshot_contains_readiness(self) -> None:
        state = WebState(UltronBrain(UltronAssistant(_test_settings())))

        payload = build_diagnostics(state)

        self.assertEqual(payload["status"], "ok")
        self.assertIn("backend", payload)
        self.assertEqual(payload["brain"]["planner_mode"], "rules")
        self.assertIn("audit_log", payload["runtime"])
        self.assertIn("providers", payload["voice"])
        self.assertIn("recent_errors", payload)

    def test_phase13_diagnostics_api_endpoint(self) -> None:
        state = WebState(UltronBrain(UltronAssistant(_test_settings())))
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(state))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            payload = json.loads(urlopen(base + "/api/diagnostics", timeout=5).read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()

        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["version"].startswith("UltronPhase13"))
        self.assertIn("safe_roots", payload["runtime"])

    def test_phase13_config_wizard_defaults_are_safe(self) -> None:
        config = generate_config(workspace="workspace", safe_roots=["workspace"], stt_provider="mock", tts_provider="mock")

        self.assertTrue(config["dry_run"])
        self.assertEqual(config["workspace"], "workspace")
        self.assertEqual(config["safe_roots"], ["workspace"])
        self.assertEqual(config["voice_stt_provider"], "mock")
        self.assertEqual(config["voice_tts_provider"], "mock")

    def test_phase13_launcher_finds_next_port_when_busy(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as busy:
            busy.bind(("127.0.0.1", 0))
            busy.listen(1)
            used_port = busy.getsockname()[1]

            open_port = find_open_port("127.0.0.1", used_port, attempts=3)

        self.assertNotEqual(open_port, used_port)

    def test_phase8_wake_word_is_removed_from_transcript(self) -> None:
        self.assertEqual(strip_wake_word("ULTRON, create note demo"), "create note demo")
        self.assertEqual(strip_wake_word("hey ultron: open notepad"), "open notepad")

    def test_phase14_transcript_cleanup_removes_fillers_and_repeats(self) -> None:
        cleaned = clean_transcript("Hey ULTRON, um open open notepad please")

        self.assertEqual(cleaned, "open notepad please")

    def test_phase14_transcript_cleanup_removes_leading_by_before_command(self) -> None:
        cleaned = clean_transcript("Bye play Blinding Lights on Spotify")

        self.assertEqual(cleaned, "play Blinding Lights on Spotify")

    def test_phase14_audio_analysis_rejects_short_or_noisy_input(self) -> None:
        short = analyze_audio_payload({"audio_duration_ms": 90, "audio_energy": 0.2})
        noisy = analyze_audio_payload({"audio_duration_ms": 1200, "speech_ms": 900, "audio_energy": 0.3, "noisy": True})

        self.assertTrue(short["rejected"])
        self.assertIn("too short", short["reason"])
        self.assertTrue(noisy["rejected"])
        self.assertTrue(noisy["noisy"])

    def test_phase14_backend_mock_capture_executes_through_voice_pipeline(self) -> None:
        voice = VoiceSession(capture=MockMicrophoneCapture("ULTRON, create note backend voice"), stt=TextPayloadSTT())
        state = WebState(UltronBrain(UltronAssistant(_test_settings())), voice=voice)

        payload = state.voice_capture({})

        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["voice_diagnostics"]["capture_provider"], "mock_capture")
        self.assertEqual(payload["transcript"]["text"], "create note backend voice")
        self.assertEqual(payload["task"]["steps"][0]["tool_call"]["name"], "create_note")

    def test_phase14_backend_capture_unavailable_is_nonfatal(self) -> None:
        class UnavailableCapture:
            name = "unavailable_capture"

            def capture(self, payload: dict[str, object]) -> dict[str, object]:
                return {"status": "unavailable", "message": "No backend microphone."}

            def health(self):
                from ultron27.voice import ProviderHealth

                return ProviderHealth("capture", self.name, configured=True, active=True, available=False, detail="No backend microphone.")

        state = WebState(
            UltronBrain(UltronAssistant(_test_settings())),
            voice=VoiceSession(capture=UnavailableCapture(), configured_capture=UnavailableCapture()),
        )

        payload = state.voice_capture({})

        self.assertEqual(payload["status"], "capture_unavailable")
        self.assertEqual(payload["last_task"], None)
        self.assertIn("No backend microphone", payload["message"])


def _test_settings() -> RuntimeSettings:
    return RuntimeSettings(
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


def _workspace_settings(workspace: Path, *, dry_run: bool = True, write_audit: bool = False) -> RuntimeSettings:
    return RuntimeSettings(
        dataset_path=Path("data/jarvis_dataset_v2/jarvis_laptop_commands_synthetic_v2.jsonl"),
        audit_log=workspace / ".ultron" / "audit.jsonl",
        workspace=workspace,
        dry_run=dry_run,
        safe_roots=(workspace,),
        app_aliases=None,
        screenshot_dir=workspace / ".ultron" / "screenshots",
        planner_mode="rules",
        llm_model="unused",
        llm_endpoint="http://localhost:11434",
        llm_timeout_seconds=1.0,
        write_audit=write_audit,
    )


if __name__ == "__main__":
    unittest.main()
