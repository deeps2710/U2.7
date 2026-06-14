# ULTRON 2.7 Architecture

ULTRON is designed as a safe local automation assistant. The LLM or planner proposes a tool call, but the application owns validation, permission checks, execution, and audit logging.

## Pipeline

```text
wake word -> VAD -> STT -> planner -> tool call -> validation
-> policy -> executor -> observation -> response -> TTS
```

The current repository implements the middle of the pipeline:

```text
text command -> planner -> validator -> policy -> safe executor -> audit log
```

## Core Principles

- Local-first by default.
- Tool calls are typed and allowlisted.
- High-risk actions require confirmation.
- Destructive actions are previewed, not blindly executed.
- Every decision is logged for evaluation and improvement.
- Voice and LLM components are adapters around the same safe tool layer.
- Real execution is limited to low-risk, allowlisted tools.
- File tools are restricted to configured safe roots.

## Risk Levels

| Level | Examples | Behavior |
|---|---|---|
| none | clarification, unsupported request | no execution |
| low | open app, set volume, search files | allowed after validation |
| medium | draft email, move file, smart-home control | confirmation when configured |
| high | delete file, send email, run script, shutdown | confirmation required |
| blocked | arbitrary shell, credential access | rejected |

## Phase 2 Execution Boundary

Phase 2 introduces real low-risk execution while keeping destructive actions blocked or preview-only.

Implemented low-risk execution includes:

- note creation and append operations under the configured workspace,
- reminder and timer JSONL records under `.ultron/`,
- safe-root file search,
- safe-root file and folder opening,
- application launch through aliases,
- clipboard helpers on Windows,
- screenshot capture when Pillow/ImageGrab is available.

High-risk operations such as file deletion, sending email, script execution, shutdown, and restart remain non-destructive. Even if the policy receives confirmation, the executor returns `not_implemented` for destructive actions.

## Dataset Role

The provided dataset is used for:

- intent recognition experiments,
- tool-name accuracy,
- slot/tool-argument extraction,
- confirmation-policy regression tests,
- unsafe-action refusal testing.

It should not be treated as execution authority. Dataset rows are examples for learning and evaluation, not commands to run without policy checks.
