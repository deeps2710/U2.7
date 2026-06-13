# Evaluation Notes

Baseline command:

```powershell
python scripts/evaluate_dataset.py --split test
```

Current result on the supplied test split:

```json
{
  "total": 285,
  "intent_accuracy": 1.0,
  "tool_accuracy": 1.0,
  "argument_exact_match": 0.9614,
  "confirmation_accuracy": 1.0
}
```

The argument misses come from ambiguous synthetic rows where the same or near-identical utterance appears with different generated folders, file types, or file names. For example, generic commands such as "look for assignment documents" may have one generated label in the test split and another generated label in the full dataset. That is useful as a reminder that real execution should ask clarifying questions when slots are under-specified.

Recommended next dataset improvements:

- Deduplicate identical utterances with conflicting labels.
- Mark under-specified file searches as clarification cases.
- Add real corrected transcripts from actual usage.
- Add Hindi, Hinglish, and accent/STT-error variants.
- Keep high-risk action examples in a separate safety regression set.

