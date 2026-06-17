# Phase 11: Windows Automation Executor Pack

Phase 11 adds a Windows-oriented executor pack for practical low-risk laptop tasks while keeping ULTRON 2.7 inside the same safety architecture:

```text
user request -> brain/planner -> typed tool call -> schema validation
-> policy gate -> executor adapter -> audit log -> response
```

The LLM and planner still do not receive raw shell access. They can only propose a typed tool call from the allowlisted registry.

## Implemented Capabilities

The executor now supports or safely fronts these Windows automation areas:

| Tool Area | Behavior |
|---|---|
| Open application | Uses an approved alias registry for Chrome, VS Code, Notepad, Calculator, File Explorer, and Terminal. Unknown app names are blocked. |
| Open file/folder | Resolves only inside configured `safe_roots`; explicit paths outside safe roots are blocked. |
| Search files | Searches only inside configured `safe_roots`; explicit unsafe folder paths are blocked. |
| Notes | Creates and appends Markdown notes under `notes/`. |
| Clipboard | Reads and writes text with a typed clipboard adapter where supported. |
| Screenshot | Captures screenshots through Pillow/ImageGrab where supported. |
| Volume | Uses optional Windows `pycaw`/`comtypes` when installed; otherwise returns `not_implemented` without crashing. |
| Brightness | Uses optional `screen-brightness-control` when installed; otherwise returns `not_implemented` without crashing. |
| Reminders/timers | Appends JSONL records under `.ultron/`. |

Destructive or broad-control actions such as file deletion, file move/rename, email sending, script execution, shutdown, and restart remain confirmation-gated and non-destructive. After confirmation, the executor still returns `not_implemented` unless a safe dedicated adapter is designed later.

## Permission Levels

Phase 11 makes permission levels explicit in policy responses:

| Permission Level | Meaning |
|---|---|
| `low_risk_allowed` | Validated low-risk tools can run. |
| `medium_risk_confirmation` | Medium-risk tools pause for confirmation before execution. |
| `high_risk_confirmation` | High-risk tools pause for confirmation before execution. |
| `destructive_blocked_or_not_implemented` | Destructive tools are confirmation-gated but do not execute destructive behavior in this prototype. |
| `blocked` | Explicitly unsafe or invalid tool calls are rejected. |

## App Alias Registry

Default Windows aliases include:

```json
{
  "chrome": "chrome.exe",
  "google chrome": "chrome.exe",
  "vs code": "code",
  "vscode": "code",
  "notepad": "notepad.exe",
  "calculator": "calc.exe",
  "calc": "calc.exe",
  "file explorer": "explorer.exe",
  "explorer": "explorer.exe",
  "terminal": "wt.exe",
  "windows terminal": "wt.exe"
}
```

Custom aliases can be configured in `ultron.config.json` under `app_aliases`. Targets containing shell-control characters such as `&`, `|`, `;`, `<`, or `>` are ignored by the alias merger.

## Safe Root Enforcement

File tools are restricted to configured safe roots:

```json
{
  "safe_roots": [".", "~/Desktop", "~/Documents", "~/Downloads"]
}
```

If a command supplies an explicit absolute path outside those roots, ULTRON returns `blocked`. If a relative name is supplied, ULTRON searches within safe roots only.

## UI and API Additions

The web interface now includes a confirmation modal for risky actions. A command such as `open terminal` pauses and displays the tool and permission level. Execution continues only after the user clicks Confirm or provides the existing voice confirmation phrase.

New endpoint:

```text
GET /api/audit/recent?limit=25
```

The endpoint returns recent audit records, newest first, bounded to 100 records per request.

## Verification

Phase 11 adds tests for:

- safe-root blocking for explicit outside paths,
- Windows app alias resolution,
- medium-risk confirmation blocking,
- destructive action non-execution after confirmation,
- recent audit-log reading,
- `/api/audit/recent`.

The full test suite passes with 60 tests.
