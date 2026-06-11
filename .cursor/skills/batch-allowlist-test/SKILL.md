---
name: batch-allowlist-test
description: >-
  Run batch allow-list impact analysis for a candidate Training commit: classify
  NDJSON exports under old vs new allow-list, produce commit verdict (net TBC,
  gap fixes, regressions, no-ops) and tuple risk profile (ablation by segment/pattern).
  Use when the user asks to evaluate a Training selection, batch compare, commit
  verdict, tuple risk, ablation, or allowlist impact on NDJSON exports.
---

# Batch Allow-List Impact Analysis

## What this feature is

For a **candidate Training commit** (selected new 5-tuples merged into the current allow-list), classify a batch of **NDJSON exports** under old vs new allow-list, then produce:

| View | Audience | Output | Question answered |
|------|----------|--------|-------------------|
| **A — Commit verdict** | Analyst | `commit_verdict.json`, `changed_rows.csv`, `per_file.json` | Is this selection worth committing? Net TBC change, gap fixes, regressions, no-ops, verdict band |
| **B — Tuple risk profile** | Engineer / tuning | `tuple_risk.csv`, `pattern_summary.csv` | Which added tuples or `(segment, stream, cat)` patterns are helpful vs harmful? |
| **Summary** | Analyst / agent | `summary.md` | Human-readable rollup of View A (+ View B when `--ablation`) — use this first when reporting results |

One metrics engine (`compare_allowlists_on_ndjson`), one NDJSON batch, two report views. View B requires `--ablation`.

**Entrypoint:** `tools/batch_allowlist_compare.py`  
**Plan:** [2026-06-09-batch-allowlist-impact-analysis.md](../../../docs/plans/2026-06-09-batch-allowlist-impact-analysis.md)

## Required inputs (the actual feature)

| Input | Required? | Role |
|-------|-----------|------|
| **NDJSON export(s)** | **Yes** | Raw tickets classified for all metrics (`--ndjson` or `--ndjson-dir`) |
| **Selected 5-tuples** | **Yes** | Candidate commit (`--merge-tuples`, `--merge-tuples-from`, and/or `--selected-tuples-json`) |
| **Current `doc/`** | **Yes** (implicit) | Baseline allow-list (`doc/Taxonomy.csv` + reference workbook) |
| **Classified `.xlsx` upload** | Optional | Exemplar rows + novel tuple discovery; **required for `--with-rules`** |

The classified workbook supplies **new tuples only** — it does not drive reclassification. All TBC metrics come from NDJSON.

## Primary command (View A + B)

From repo root:

```bash
.\.venv\Scripts\python.exe tools/batch_allowlist_compare.py \
  --ndjson-dir data/ \
  --merge-tuples-from path/to/upload.xlsx \
  --selected-tuples-json path/to/selected.json \
  --output-dir reports/run-20260609/ \
  --with-rules \
  --ablation
```

View A only (commit verdict): omit `--ablation`.  
View B only adds `--ablation` (still runs View A first).

### Outputs

| File | View | Key fields |
|------|------|------------|
| `summary.md` | A (+ B if ablation) | Verdict band, net TBC, outcome counts, changed tickets, tuple risk highlights, **Interpretation** (analysis + recommendations) |
| `commit_verdict.json` | A | `verdict_band`, `net_tbc_improvement`, `outcome_counts`, `gap_fix_by_mechanism`, `tuples_with_rules_count` |
| `changed_rows.csv` | A | Per-ticket `outcome_type` (`gap_fix`, `regression`, `reroute`), segment, TBC reasons |
| `tuple_risk.csv` | B | Per-tuple `tbc_delta`, outcome counts, `no_op`, `has_rule` |
| `pattern_summary.csv` | B | Rollup by `(segment, stream, cat)` |

## Agent workflow

When the user asks to **evaluate a Training commit** or run **batch impact analysis**:

1. **Gather inputs**
   - NDJSON path(s): user export or `data/*.ndjson`
   - Tuple selection: upload xlsx + optional selection json, or inline `--merge-tuples`
   - Whether to include generated rules: `--with-rules` (needs upload xlsx)

2. **Run batch CLI** — always execute; do not substitute pytest for this workflow.

3. **Summarize for the user**
   - Read `summary.md` first — it mirrors the agent summary format below
   - View A: `verdict_band`, net TBC improvement, gap_fix / regression / reroute counts, mechanism breakdown
   - View B (if `--ablation`): no-op tuples, high-regression tuples, pattern_summary hotspots
   - Flag `duplicate_ticket_ids` if exports overlap
   - Optionally expand from `commit_verdict.json` / `tuple_risk.csv` for ticket-level detail

4. **Interpret using plan guidance**
   - High gap_fix but flat `zero_candidate_*` → mostly scoring recoveries, not allow-list gaps
   - High no-op + `rules_needed` band → rules gap before allow-list helps
   - Net TBC can rise after valid commit (scoring competition) — not automatic rejection

## Spec-driven runs

Use `tools/run_allowlist_test.py` with `--batch-only` to run impact analysis from JSON:

```bash
.\.venv\Scripts\python.exe tools/run_allowlist_test.py \
  --spec .cursor/skills/batch-allowlist-test/specs/impact-analysis.json \
  --batch-only
```

Edit [specs/analyst-export.json](specs/analyst-export.json) for real paths. Schema: [reference.md](reference.md).

## Demo / smoke (no user files)

To **demonstrate the feature** without user NDJSON or upload, use the shipped probe fixture:

```bash
.\.venv\Scripts\python.exe tools/run_allowlist_test.py --profile impact-analysis --batch-only
```

This uses `tests/fixtures/training_tbc_probe.ndjson` + auto-generated upload. It proves the pipeline end-to-end but is **not** a substitute for evaluating a real candidate commit on a real export.

## pytest profiles (engine validation — not the feature)

pytest proves the compare engine and report writers work; it does **not** replace batch impact analysis on analyst data.

| Profile | Purpose |
|---------|---------|
| `impact-analysis` | Full View A + B on probe fixture (batch CLI only) |
| `batch-commit` | View A on probe fixture |
| `batch-ablation` | View A + B on probe fixture |
| `ci` | Regression gate — pytest only, no reports |

```bash
.\.venv\Scripts\python.exe tools/run_allowlist_test.py --profile ci
```

## Constraints

- **Do not conflate inputs** — xlsx = tuples; NDJSON = ticket metrics
- **`--with-rules` requires `--merge-tuples-from`** for exemplar rows
- **Ablation deltas ≠ commit simulation delta** when N > 1 (tuple interaction)
- **Do not mutate `doc/`** unless user explicitly requests portal commit Test B

## Related docs

- [testcase.md](../../../testcase.md) — manual portal flow
- [2026-06-09-allowlist-testing-architecture.md](../../../docs/plans/2026-06-09-allowlist-testing-architecture.md) — layered pytest architecture (supports, does not replace, this feature)
