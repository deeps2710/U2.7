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

Phase 4 optionally expands the planner step:

```text
dataset/rules planner -> optional LLM planner -> typed tool call
```

The optional LLM planner is only allowed to propose a JSON tool call. The validator, policy layer, confirmation gates, and executor remain authoritative.

Phase 6 adds a task-level brain above the runtime:

```text
user goal -> brain -> TaskPlan -> safe runtime step(s)
```

Each runtime step still uses the original command pipeline:

```text
step utterance -> planner -> typed tool call -> validator -> policy -> executor -> audit log
```

The brain can plan multi-step tasks, pause on confirmation gates, summarize outcomes, and store non-sensitive memory. It cannot bypass validation, policy, executor restrictions, or audit logging.

## Core Principles

- Local-first by default.
- Tool calls are typed and allowlisted.
- High-risk actions require confirmation.
- Destructive actions are previewed, not blindly executed.
- Every decision is logged for evaluation and improvement.
- Voice and LLM components are adapters around the same safe tool layer.
- Real execution is limited to low-risk, allowlisted tools.
- File tools are restricted to configured safe roots.
- LLM output is treated as untrusted input until it passes schema validation and policy.
- The brain is orchestration only; it does not receive raw shell access.
- Persistent memory rejects obvious sensitive content such as passwords, API keys, tokens, credentials, and secrets.

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

## Phase 6 Brain Boundary

The brain owns task-level orchestration, not raw execution. It can:

- decompose a user goal into one or more step utterances,
- preview the selected tool and policy decision for each step,
- execute steps through `UltronAssistant.handle()`,
- stop when a step requires confirmation, fails, or is blocked,
- write a task-level audit record,
- store small non-sensitive memory facts under `.ultron/memory.json`.

It cannot directly call the OS, run shell commands, skip policy, skip schema validation, or treat an LLM response as trusted execution authority.

## Dataset Role

The provided dataset is used for:

- intent recognition experiments,
- tool-name accuracy,
- slot/tool-argument extraction,
- confirmation-policy regression tests,
- unsafe-action refusal testing.

It should not be treated as execution authority. Dataset rows are examples for learning and evaluation, not commands to run without policy checks.
