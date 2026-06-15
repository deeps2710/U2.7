# Phase 6: Brain Layer

Phase 6 gives ULTRON 2.7 a task-level brain without giving any model or agent raw shell access. The brain decomposes user goals into safe steps, previews the intended tool calls, executes allowed steps through the existing runtime, pauses on confirmation gates, and records non-sensitive memory.

## What Changed

- Added `src/ultron27/brain.py`.
- Added `TaskState`, `TaskStep`, and `TaskPlan` models.
- Added `UltronBrain` for planning and executing multi-step goals.
- Added `MemoryStore` at `.ultron/memory.json` by default.
- Added console and CLI slash commands:
  - `/plan <goal>`
  - `/do <goal>`
  - `/memory`
  - `/forget <query>`
- Added task-level audit records with `record_type: brain_task`.
- Added tests for decomposition, safe execution, confirmation blocking, memory, failed steps, and audit logging.

## Safety Boundary

The brain does not execute arbitrary commands. Each step is sent through the same safe runtime:

```text
goal -> brain -> task plan -> runtime step -> planner -> validator -> policy -> executor -> audit -> result
```

This keeps ULTRON's core safety properties intact:

- Tool calls are allowlisted.
- Tool arguments are schema-validated.
- High-risk actions require confirmation.
- Unsupported or unsafe actions are blocked.
- Destructive execution remains intentionally unimplemented in the MVP.
- LLM planning, when enabled, can only propose JSON tool calls that pass validation and policy.

## Example

```powershell
python -m ultron27 "/plan Create a note called project ideas and add that I should test voice mode next." --text
python -m ultron27 "/do Create a note called project ideas and add that I should test voice mode next." --text --execute --workspace .
```

The brain decomposes that goal into:

```text
1. create note project ideas
2. add I should test voice mode next to note project ideas
```

The runtime then maps those steps to:

```text
create_note
append_to_note
```

## Memory

Persistent memory is stored at `.ultron/memory.json` unless a different path is supplied programmatically. It is intended for small non-sensitive facts such as:

- last completed goal,
- last used note title,
- recent file search query,
- user preferences.

The memory store rejects obvious sensitive content such as passwords, secrets, tokens, API keys, credentials, and private keys.

## Verification

Phase 6 adds regression coverage for:

- task decomposition,
- safe multi-step execution,
- high-risk confirmation pause,
- memory write/read/delete,
- failed tool handling,
- task-level audit logging.
