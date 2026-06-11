# Batch Allow-List Impact Analysis — Reference

## Feature definition

Classify NDJSON ticket batch under **old allow-list** vs **candidate allow-list** (current + selected new 5-tuples). Produce:

- **View A:** commit verdict — net TBC, gap fixes, regressions, no-ops, advisory verdict band
- **View B:** tuple risk profile — per-tuple ablation + pattern rollup by `(segment, stream, cat)`
- **Summary:** `summary.md` — human-readable rollup written on every batch run (includes View B sections when `--ablation`)

Implemented by `tools/batch_allowlist_compare.py`. pytest validates the engine; it is not the analyst-facing feature.

## Required inputs

| Input | CLI flag | Notes |
|-------|----------|-------|
| NDJSON export(s) | `--ndjson` or `--ndjson-dir` | **Required** — all metrics from here |
| Selected 5-tuples | `--merge-tuples`, `--merge-tuples-from`, `--selected-tuples-json` | **Required** — at least one source |
| Baseline allow-list | `--taxonomy`, `--workbook` (defaults: `doc/`) | Implicit |
| Classified upload | `--merge-tuples-from` | Optional; **required for `--with-rules`** |

## JSON spec schema (version 1)

| Field | Type | Description |
|-------|------|-------------|
| `profile` | string | Built-in profile name; merged with overrides below |
| `description` | string | Human label for the run |
| `presteps` | string[] | `build_probe_upload` — runs `tools/build_training_test_upload.py` |
| `pytest` | string[] | pytest paths or `file.py::test_name` expressions |
| `batch` | object | Args for `tools/batch_allowlist_compare.py` |
| `assertions` | object | Checks on `commit_verdict.json` after batch CLI |

### `batch` object

| Field | Maps to CLI flag |
|-------|------------------|
| `ndjson` | `--ndjson` |
| `ndjson_dir` | `--ndjson-dir` |
| `merge_tuples` | `--merge-tuples` (repeatable strings) |
| `merge_tuples_from` | `--merge-tuples-from` |
| `selected_tuples_json` | `--selected-tuples-json` |
| `with_rules` | `--with-rules` |
| `ablation` | `--ablation` |
| `compute_no_op` | `--compute-no-op` |
| `limit` | `--limit` |
| `ablation_limit` | `--ablation-limit` |
| `taxonomy` | `--taxonomy` (default `doc/Taxonomy.csv`) |
| `workbook` | `--workbook` (default `doc/CS_ticket_new_categorizations.xlsx`) |
| `output_dir` | `--output-dir` |

Paths are relative to repo root unless absolute.

### `assertions` object

| Field | Check |
|-------|-------|
| `verdict_band` | Exact match (`strong_commit`, `review`, `rules_needed`, `risky`) |
| `min_net_tbc_improvement` | `net_tbc_improvement >= N` |
| `min_gap_fix_count` | `outcome_counts.gap_fix >= N` |
| `outcome_counts` | Exact match per outcome key |

## Built-in profiles

| Profile | What it runs | The feature? |
|---------|--------------|--------------|
| **`impact-analysis`** | View A + B batch CLI on probe fixture | Demo/smoke of the feature |
| `batch-commit` | View A batch CLI on probe fixture | Partial |
| `batch-ablation` | View A + B (subset pytest + batch CLI) | Partial |
| `ci` | pytest regression only | No — engine validation |
| `layers-1-3` | pytest layers 1–3 | No |
| `batch` | batch pytest only | No |
| `probe` | probe pytest + optional batch CLI | No — mechanism proof |

For real analyst evaluation, use a custom spec with `data/` NDJSON and your upload — see [specs/analyst-export.json](specs/analyst-export.json).

## Testing architecture layer map

| Layer | pytest files | Fixture |
|-------|--------------|---------|
| 1 — Unit | `test_allowlist_session.py`, `test_allowlist_training.py` | — |
| 2 — Probe | `test_golden_classifier.py` (probe tests) | `training_tbc_probe.ndjson` |
| 3 — Golden | `test_golden_classifier.py` (golden ceiling) | `golden_export.ndjson` |
| Advisory — Batch | `test_batch_allowlist_analysis.py` | probe + `five_tickets.ndjson` |
| 4 — Portal | Manual (`testcase.md` Test B) | writable `doc/` |

## Probe constants

| Field | Value |
|-------|-------|
| 5-tuple | `B2C,Service Task,Sales Leads,Rate or Renewal Inquiry,N/A` |
| Ticket id | `910001` |
| NDJSON | `tests/fixtures/training_tbc_probe.ndjson` |
| Upload | `tests/fixtures/training_tbc_probe_upload.xlsx` |

## Runner flags

| Flag | Effect |
|------|--------|
| `--pytest-only` | Skip batch CLI |
| `--batch-only` | Skip pytest (still runs presteps) |
| `--output-dir` | Override batch report directory |
