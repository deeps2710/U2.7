# Phase 4: Optional LLM Planner

Phase 4 adds an optional LLM planning layer while preserving ULTRON's safety architecture. The model proposes a typed tool call; it does not execute tools and cannot bypass validation or policy.

## Implemented

- `src/ultron27/llm.py`
  - JSON tool-call parser
  - `LLMPlanner`
  - Ollama and Groq providers
  - prompt builder from the allowlisted tool registry
- CLI planner modes:
  - `rules`
  - `hybrid`
  - `llm`
- Config support:
  - `planner_mode`
  - `llm_provider`
  - `llm_model`
  - `llm_endpoint`
  - `llm_timeout_seconds`
- Tests for valid JSON planning, invalid schema rejection, safe plan construction, and config loading.

## Safety Boundary

The LLM is only a planner. Every proposed call still passes through:

```text
LLM JSON -> ToolCall -> schema validation -> policy -> executor
```

Invalid JSON, unknown tools, missing arguments, extra arguments, and invalid numeric ranges are rejected before execution. If the configured provider is unavailable, ULTRON reports the LLM error in the runtime trace and falls back safely.

## Example

```powershell
python -m ultron27 "launch the basic text editor" --planner-mode hybrid
```

Expected model output shape:

```json
{
  "intent": "open_app",
  "tool_name": "open_application",
  "tool_arguments": {
    "app": "notepad"
  },
  "confidence": 0.8
}
```

## Verification

```text
python -m unittest discover -s tests
21 tests passed

python scripts/evaluate_safety_regression.py
tool_accuracy: 1.0
policy_action_accuracy: 1.0
```

The local test environment did not have a live provider running, so CLI LLM mode was also tested for safe provider failure behavior.

