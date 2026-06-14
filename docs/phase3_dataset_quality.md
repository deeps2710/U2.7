# Phase 3: Dataset Quality And Safety Evaluation

Phase 3 improves the project by making the supplied dataset auditable and by extracting a dedicated safety regression set. This phase does not replace the synthetic dataset; it creates tools and reports that show where the dataset is strong, where it is ambiguous, and which examples must keep passing as ULTRON grows.

## Implemented

- Dataset quality analyzer: `scripts/analyze_dataset_quality.py`
- Safety regression evaluator: `scripts/evaluate_safety_regression.py`
- Dataset quality module: `src/ultron27/dataset_quality.py`
- Generated audit report: `docs/phase3_dataset_quality_report.json`
- Generated safety cases: `data/regression/safety_cases.jsonl`
- Tests for duplicate-conflict detection, underspecified examples, and safety case extraction

## Current Dataset Audit

```text
Total examples: 2500
Unique utterances: 2319
Duplicate utterance groups: 101
Conflicting duplicate groups: 101
Underspecified examples: 879
Safety examples: 362
```

The main issue is not intent coverage. The issue is that many synthetic file-search utterances assign specific file types or folders that are not actually present in the utterance. For example, a phrase such as "look for assignment documents" may appear with different generated file types and folders. Those examples should become clarification cases or be regenerated with explicit slot mentions.

## Safety Regression

The analyzer extracts high-risk, confirmation-gated, and unsupported examples into `data/regression/safety_cases.jsonl`. The current safety regression result is:

```text
Total safety cases: 362
Tool accuracy: 1.0
Policy action accuracy: 1.0
```

This gives ULTRON a stable safety gate before adding an LLM planner or voice interface.

## Recommended Dataset Fixes

1. Deduplicate identical utterances with conflicting labels.
2. Convert underspecified search/open-file examples into `ask_clarification` examples.
3. Add real usage logs with corrected transcripts.
4. Add Hinglish, Hindi, and STT-error variants.
5. Keep destructive actions in a separate safety regression split.

