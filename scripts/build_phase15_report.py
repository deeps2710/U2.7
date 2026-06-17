from __future__ import annotations

from pathlib import Path

from phase_report_common import ROOT, build_docx


REPORT = {
    "phase": 15,
    "title": "ULTRON 2.7 Phase 15 Execution Report",
    "subtitle": "Semantic intent routing with local LLM fallback",
    "phase_label": "Phase 15: Flexible Natural-Language Understanding",
    "status": "Implemented and verified with mocked LLM tests",
    "blocks": [
        {
            "kind": "section",
            "heading": "Executive Summary",
            "paragraphs": [
                "Phase 15 makes ULTRON less dependent on exact command wording. The command pipeline now uses hybrid routing: a fast deterministic router handles obvious commands, and a local Ollama-backed semantic router can propose structured JSON tool intents for flexible phrasing.",
                "The local LLM is not an executor. It can only propose typed tool calls, which must still pass schema validation, policy gates, executor restrictions, and audit logging before any task runs.",
            ],
        },
        {
            "kind": "bullets",
            "heading": "Phase 15 Scope",
            "items": [
                "Add semantic routing through a local free LLM using Ollama when configured.",
                "Use fast regex routing first for obvious app, note, music, and reminder commands.",
                "Use local LLM fallback for flexible wording and multi-step intent proposal.",
                "Require strict JSON tool-intent output from the LLM.",
                "Reject unknown tools, invalid arguments, malformed JSON, and low-confidence tool proposals.",
                "Ask clarification when wording is ambiguous or confidence is too low.",
                "Add prompt templates for classification, tool selection, decomposition, and clarification.",
                "Add mocked LLM tests so safety and routing behavior can be verified without Ollama installed.",
            ],
        },
        {
            "kind": "table",
            "heading": "What Was Implemented",
            "columns": ["Area", "File(s)", "Result"],
            "rows": [
                ["Semantic router", "src/ultron27/llm.py", "Adds SemanticIntentRouter, Ollama planner integration, prompt templates, strict JSON parsing, and confidence-based clarification."],
                ["Hybrid runtime", "src/ultron27/runtime.py", "Routes utterances through regex first, then semantic LLM fallback when planner mode allows it."],
                ["Fast phrasing support", "src/ultron27/planner.py", "Maps launch, start, bring up, notes app, jot this down, and music phrases to the correct typed intents where safe."],
                ["Clarification tool", "src/ultron27/executor.py, src/ultron27/brain.py", "Adds ask_clarification handling so uncertain intents return a question rather than executing."],
                ["Tests", "tests/test_pipeline.py", "Adds mocked LLM and flexible-phrasing tests for low confidence, explicit clarification, music routing, and safe fallback."],
                ["Docs", "README.md, docs/architecture.md", "Documents hybrid routing, Ollama configuration, and the LLM safety boundary."],
            ],
            "widths": [1.35, 2.35, 2.8],
        },
        {
            "kind": "table",
            "heading": "Routing Behavior",
            "columns": ["Input Style", "Routing Path", "Expected Result"],
            "rows": [
                ["open notepad / launch notepad / bring up notepad", "Fast router", "Maps to open_application with the Notepad alias."],
                ["start the notes app", "Fast router with alias normalization", "Maps to Notepad because notes app is normalized to notepad."],
                ["jot this down", "Fast router when safe", "Maps to create_note with captured note content."],
                ["write this in notepad", "Clarification path", "Asks what text should be written before taking action."],
                ["play blinding lights on Spotify", "Fast router or LLM fallback", "Maps to play_music with query and Spotify provider."],
                ["put on some lofi music", "LLM fallback if needed", "Maps to play_music only after valid JSON and confidence checks."],
            ],
            "widths": [2.15, 2.0, 2.35],
        },
        {
            "kind": "table",
            "heading": "Prompt and Validation Boundary",
            "columns": ["Component", "Role", "Constraint"],
            "rows": [
                ["Classification template", "Decides whether text is chat, question, command, or ambiguous.", "It returns JSON only; no direct execution."],
                ["Tool selection template", "Chooses a typed ULTRON tool and argument object.", "Unknown tools or malformed arguments are rejected."],
                ["Multi-step template", "Breaks flexible goals into proposed tool steps.", "Every step still passes validation and policy."],
                ["Clarification template", "Creates a short question when intent is uncertain.", "Ambiguous commands do not execute."],
                ["Confidence gate", "Blocks low-confidence command proposals.", "ULTRON asks before acting when confidence is insufficient."],
            ],
            "widths": [1.55, 2.55, 2.4],
        },
        {
            "kind": "table",
            "heading": "Verification Results",
            "columns": ["Check", "Command or Coverage", "Result"],
            "rows": [
                ["Compile check", "python -m compileall src\\ultron27", "Python modules compiled successfully."],
                ["Unit tests", "python -m unittest discover -s tests", "89 tests passed."],
                ["Flexible app wording", "Regex tests for launch, start, bring up, notes app", "Multiple phrasings map to the same typed tool intent."],
                ["LLM low confidence", "Mocked LLM response with low confidence", "ULTRON asks clarification instead of executing."],
                ["Invalid or unavailable LLM", "Hybrid fallback coverage", "ULTRON remains safe and usable without Ollama."],
                ["Music phrasing", "Mocked LLM response for lofi music", "Valid JSON maps to play_music through the safe pipeline."],
            ],
            "widths": [1.35, 2.75, 2.4],
        },
        {
            "kind": "section",
            "heading": "Safety Impact",
            "paragraphs": [
                "Phase 15 improves understanding, not authority. The LLM is restricted to proposing JSON. Every proposal must still pass the same typed schema validation, policy decision, executor boundary, and audit logging already used by ULTRON.",
                "If Ollama is unavailable, malformed, or uncertain, ULTRON falls back to deterministic routing or asks the user for clarification.",
            ],
        },
        {
            "kind": "bullets",
            "heading": "Recommended Next Step",
            "items": [
                "Add an executor phase for app-specific automation, including writing into Notepad and controlling Spotify playback.",
                "Add a phrase-training fixture so real user wording can be added safely to regression tests.",
                "Add an Ollama setup wizard that checks model availability and recommends a small local model.",
            ],
        },
    ],
}


if __name__ == "__main__":
    build_docx(REPORT, ROOT / "docs" / "ULTRON_2.7_Phase_15_Report.docx")
