# Batch Allow-List Impact Analysis — Implementation Notes (Phase 1)

**Date:** 2026-06-09  
**Plan:** [2026-06-09-batch-allowlist-impact-analysis.md](./2026-06-09-batch-allowlist-impact-analysis.md)

## Spec amendments applied before implementation

1. **Combined result labeling** — `commit_verdict.json` includes `combined_is_synthetic`, `counter_aggregation`, `changed_rows_aggregation`. Outcome counts derived from deduped rows only.
2. **Phase 1 no-op cost** — `selection_no_op_*` omitted unless `--compute-no-op` (deferred from default Phase 1 path).
3. **`rules_needed` band** — Uses `tuples_with_rules_count` (tuple coverage), not `rules_targeting_selected_new`.

## What was built (Phase 1)

| File | Change |
|------|--------|
| `src/cs_tickets/allowlist_compare.py` | Added `enrich_changed_row()`; `enrich_changed_rows=False` default on `compare_allowlists_on_ndjson()` |
| `src/cs_tickets/batch_allowlist_analysis.py` | New — commit simulation, aggregation, verdict bands, report writers |
| `src/cs_tickets/allowlist_training.py` | Added `build_candidate_rule_set_from_upload()` for CLI without portal session |
| `tools/batch_allowlist_compare.py` | New CLI entrypoint |
| `tests/test_batch_allowlist_analysis.py` | Phase 1 test matrix |

## Design decisions

- **Candidate allow-list CLI path** mirrors portal via `build_candidate_allowlist_cli()` (temp workbook copy + `merge_tuples_into_workbook`). Parity test confirms identical tuples vs `create_session` + `build_candidate_allowlist`.
- **Inline tuple selection** (`--merge-tuples` without xlsx) builds `allow_new` by set union only — no exemplar rows. Use `--merge-tuples-from` for portal-faithful candidate workbook.
- **`build_candidate_allowlist_cli`** creates `work_dir` before copy (Windows requires parent dir to exist).
- **Verdict band order:** `rules_needed` → `risky` → `strong_commit` → `review`.

## Not in Phase 1

- `--ablation`, `tuple_risk.csv`, `pattern_summary.csv` (Phase 2)
- Portal HTML opt-in for row enrichment
- Committing implementation notes or plan changes to git (unless requested)

## Phase 2 (2026-06-09)

| File | Change |
|------|--------|
| `src/cs_tickets/batch_allowlist_analysis.py` | `run_tuple_ablation()`, cached old classifications, `write_ablation_reports()`, `apply_ablation_no_op_to_result()` |
| `tools/batch_allowlist_compare.py` | `--ablation`, `--ablation-limit`; ablation populates `selection_no_op_*` in verdict |
| `tests/test_batch_allowlist_analysis.py` | 7 Phase 2 tests |

**Ablation cache:** `build_old_classification_cache()` classifies each ticket once under `allow_old`; per-tuple pass only re-classifies under `allow_old + {t}`.

**`--with-rules` during ablation:** `build_candidate_rule_set_from_upload(..., selected={t})` per tuple — not full-selection rules.

## Not yet implemented

- Portal HTML opt-in for row enrichment

## Test results

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_batch_allowlist_analysis.py tests/test_golden_classifier.py tests/test_allowlist_session.py -q
# 32 passed
```

## Quick start

```bash
.\.venv\Scripts\python.exe tools\batch_allowlist_compare.py \
  --ndjson tests/fixtures/training_tbc_probe.ndjson \
  --merge-tuples-from path/to/upload.xlsx \
  --output-dir reports/run-1
```

For probe-style evaluation where the tuple is already in `doc/`, tests construct `allow_old = full − {probe tuple}` programmatically; the CLI alone uses current `doc/` as baseline.
