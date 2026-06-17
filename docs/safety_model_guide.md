# ULTRON 2.7 Safety Model Guide

ULTRON 2.7 does not give the planner, LLM, voice stack, or web UI raw shell access.

## Runtime Flow

```text
request -> brain/planner -> typed tool call -> schema validation
-> policy gate -> executor -> audit log -> response
```

## Risk Levels

| Risk | Behavior |
|---|---|
| none | no execution |
| low | allowed after validation |
| medium | confirmation required |
| high | confirmation required |
| blocked | rejected |

## Destructive Actions

Destructive actions are confirmation-gated and intentionally not implemented in this prototype. Confirmation does not grant raw shell access.

## Voice Safety

Voice is an input/output adapter:

```text
voice -> STT -> brain/runtime -> typed tool call -> validation
-> policy -> executor -> audit -> response -> TTS
```

High-risk voice actions require explicit confirmation such as `yes confirm`.

## Skills and Knowledge

Skills validate their own inputs and then call the same safe runtime for OS-facing work. Knowledge retrieval is context only and cannot execute tasks.

## Diagnostics Safety

The diagnostics page is read-only. It exposes readiness information such as paths, providers, safe roots, and recent errors. It does not run tools.
