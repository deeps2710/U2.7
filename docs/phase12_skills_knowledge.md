# Phase 12: Skills and Local Knowledge

Phase 12 adds a reusable skill system and local knowledge base to ULTRON 2.7. The goal is to let ULTRON learn useful project capabilities and answer from local documents without turning knowledge into execution authority.

The safety boundary remains:

```text
skill input -> skill schema validation -> skill policy gate
-> typed tool call when needed -> tool schema validation -> tool policy gate
-> executor -> audit log -> response
```

Knowledge retrieval can provide context, summaries, and planning material. It cannot run actions, select OS tools directly, or bypass the existing executor.

## Skill Registry

The skill registry lives in `src/ultron27/skills.py`.

Each skill has:

- skill name,
- description,
- input schema,
- risk level,
- executor handler,
- examples.

`SkillRegistry.run()` validates the input schema, checks skill-level policy, runs the handler only when allowed, and writes an audit record. Skills that need laptop actions call `UltronAssistant.handle_tool_call()`, so they still pass through tool schema validation, policy, executor restrictions, and audit logging.

## Built-In Skills

| Skill | Purpose | Execution Boundary |
|---|---|---|
| `notes` | Create or append local notes. | Uses `create_note` or `append_to_note` through the safe runtime. |
| `reminders` | Save reminders. | Uses `set_reminder` through the safe runtime. |
| `file_search` | Search files inside safe roots. | Uses `search_files` through the safe runtime. |
| `project_summary` | Summarize matching local knowledge. | Reads knowledge chunks only; no OS execution. |
| `daily_planning` | Draft a daily plan from explicit priorities, memory path, and knowledge matches. | Produces a planning response only; no OS execution. |

## Local Knowledge Base

The knowledge base lives in `src/ultron27/knowledge.py` and stores its index under:

```text
.ultron/knowledge/index.json
```

Supported ingestion:

- Markdown,
- TXT,
- PDF when `pypdf` is available,
- DOCX when `python-docx` is available.

Ingestion behavior:

- source paths must be inside configured `safe_roots`,
- obvious secrets are rejected,
- text is chunked into searchable chunks,
- document metadata is stored,
- keyword search is the default retrieval path,
- an embedding provider abstraction exists, with `keyword_only` as the current fallback.

## APIs

```text
GET  /api/skills
POST /api/skills/run
POST /api/knowledge/ingest
GET  /api/knowledge/search?query=<text>&limit=5
```

The API also exposes knowledge sources through the normal status snapshot so the UI can show a user-visible source list.

## UI Panels

The Phase 12 interface adds:

- skills list,
- memory and knowledge viewer,
- local knowledge search,
- recent task history.

These panels are view/control surfaces only. They do not run tools directly.

## Privacy Rules

- Do not ingest files outside safe roots.
- Do not store content that appears to contain passwords, tokens, API keys, credentials, private keys, or bearer tokens.
- Keep knowledge sources visible to the user.
- Treat retrieved text as context only, never as execution authority.

## Verification

Phase 12 adds tests for:

- skill schema validation,
- unknown skill rejection,
- notes skill execution through the safe runtime,
- knowledge ingest/search,
- secret rejection,
- medium-risk skill policy blocking,
- skills and knowledge API endpoints.

The full test suite currently passes with 67 tests.
