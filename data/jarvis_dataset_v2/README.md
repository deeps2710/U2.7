# Jarvis Laptop Commands Synthetic Dataset v2

This is an expanded synthetic dataset for a personal AI assistant similar to Jarvis.

## Files

- `jarvis_laptop_commands_synthetic_v2.csv`
- `jarvis_laptop_commands_synthetic_v2.jsonl`
- `splits/train.jsonl`
- `splits/validation.jsonl`
- `splits/test.jsonl`
- `intent_summary.csv`
- `schema.md`

## Size

- Total examples: 2500
- Train: 1985
- Validation: 230
- Test: 285
- Intent classes: 42

## Use cases

- Intent classification
- Slot extraction
- LLM function-calling evaluation
- Safety policy testing
- Confirmation-gate testing
- Voice command paraphrase testing

## Notes

This is synthetic. It is useful for bootstrapping, but you should improve it by adding:
1. real commands from your own usage logs,
2. STT transcripts with errors,
3. OS-specific execution results,
4. failure cases,
5. more Hinglish / Hindi / local accent variants if needed.

## Suggested evaluation metrics

- Intent accuracy
- Slot exact match
- Tool-name accuracy
- Tool-argument JSON exact match
- Confirmation policy accuracy
- Unsafe request refusal accuracy
