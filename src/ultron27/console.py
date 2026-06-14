from __future__ import annotations

import json
import sys
from typing import TextIO

from .runtime import UltronAssistant


EXIT_COMMANDS = {"/exit", "/quit", "exit", "quit"}
HELP_COMMANDS = {"/help", "help", "?"}


def format_assistant_response(payload: dict) -> str:
    tool = payload["tool_call"]["name"]
    status = payload["result"]["status"]
    message = payload["result"]["message"]
    policy = _plain(payload["policy"]["action"])
    risk = _plain(payload["policy"]["risk_level"])
    source = payload["source"]
    confidence = payload["confidence"]

    lines = [
        f"Tool: {tool}",
        f"Policy: {policy} | Risk: {risk} | Source: {source} | Confidence: {confidence:.2f}",
        f"Result: {status} - {message}",
    ]
    if status == "confirmation_required":
        lines.append("Confirm with: /yes " + payload["utterance"])
    return "\n".join(lines)


def _plain(value: object) -> str:
    return str(getattr(value, "value", value))


def help_text() -> str:
    return "\n".join(
        [
            "Commands:",
            "  /help              Show this help.",
            "  /json <command>    Run a command and print the full JSON payload.",
            "  /yes <command>     Confirm a command that needs confirmation.",
            "  /exit              Leave the console.",
        ]
    )


def run_console(
    assistant: UltronAssistant,
    *,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
) -> None:
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    print("ULTRON 2.7 interactive console. Type /help or /exit.", file=output_stream)
    while True:
        print("ultron> ", end="", file=output_stream, flush=True)
        line = input_stream.readline()
        if line == "":
            print("", file=output_stream)
            break
        command = line.strip()
        if not command:
            continue
        lowered = command.lower()
        if lowered in EXIT_COMMANDS:
            print("Session ended.", file=output_stream)
            break
        if lowered in HELP_COMMANDS:
            print(help_text(), file=output_stream)
            continue
        if lowered.startswith("/json "):
            payload = assistant.handle(command[6:].strip())
            print(json.dumps(payload, indent=2, ensure_ascii=True), file=output_stream)
            continue
        confirmed = False
        if lowered.startswith("/yes "):
            command = command[5:].strip()
            confirmed = True
        payload = assistant.handle(command, confirmed=confirmed)
        print(format_assistant_response(payload), file=output_stream)
