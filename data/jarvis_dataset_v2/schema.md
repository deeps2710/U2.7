# Jarvis Laptop Commands Synthetic Dataset v2 — Schema

Each row represents one possible user voice/text command and the expected structured action.

## Columns

- `id`: Stable hash ID.
- `utterance`: Natural-language command.
- `intent`: Intent class to classify.
- `slots`: JSON object of extracted entities/values.
- `tool_name`: Tool/function that should be called.
- `tool_arguments`: JSON object passed to the tool.
- `risk_level`: `none`, `low`, `medium`, or `high`.
- `requires_confirmation`: Whether the assistant should ask before executing.
- `expected_result`: Expected high-level result or policy response.
- `source`: Synthetic generation type.
- `language`: Language code.
- `domain`: Dataset domain.

## Important safety rule

This dataset is for intent recognition, slot extraction, and safe tool-routing experiments. Do not directly execute tool calls from a model without validation, allowlisting, confirmation gates, and audit logging.
