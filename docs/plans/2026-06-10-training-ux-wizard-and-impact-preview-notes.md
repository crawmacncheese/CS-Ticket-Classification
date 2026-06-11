# Training UX — Wizard & Impact Preview — Implementation Notes

**Date:** 2026-06-10  
**Plan:** [2026-06-10-training-ux-wizard-and-impact-preview.md](./2026-06-10-training-ux-wizard-and-impact-preview.md)  
**Parent:** [2026-06-10-portal-ux-improvement.md](./2026-06-10-portal-ux-improvement.md) Phase 2

---

## Shipped

| Area | Files |
|------|--------|
| Analyst copy | `portal_training_copy.py` |
| Wizard + verdict UI | `portal_training.py` |
| Preview wiring | `portal_app.py`, `batch_allowlist_analysis.py` |
| Plain-language compare table | `allowlist_compare.py` (`plain_language=True`) |
| Session state | `allowlist_training.py` — `preview_batch_result`, `preview_no_op_tuples` |
| Client UX | `static/training.js`, `static/cs_tickets_theme.css` |

## Behaviour

- **Wizard:** 3 steps (Upload → Review → Preview & save). Step 3 highlights after a successful preview.
- **Preview:** Single `run_commit_simulation` pass supplies both metrics table (`combined`) and verdict banner.
- **No-op analysis:** Optional checkbox — runs per-category ablation only when selected (slower).
- **Verdict banner:** Maps `classify_verdict_band()` output to analyst messages (`Looks good`, `Review changes`, `Low impact expected`, `Caution`).
- **No-op helper:** When verdict is `rules_needed` and no-op tuples are known, shows **Deselect categories with no impact** (client-side).
- **Changed tickets:** Default shows id + old/new category; checkbox reveals outcome, mechanism, TBC reason.
- **Golden hint:** Informational comparison to `tests/fixtures/golden_baseline.json` when present.
- **Commit confirm:** JS dialog before save; success copy says **Saved** not **Added**.
- **Terminology:** Primary labels use *category* / *reference categories* / *manual review (TBC)*; technical footnotes remain for maintainers.

## Design decisions

- `compare_result_html(..., plain_language=True)` for Training preview only — CLI/batch unchanged.
- `run_commit_simulation` gained `bad_satisfaction_only` so verdict stats match the filtered compare table.
- `BatchCompareResult.selection_no_op_tuples` populated from one ablation pass (count + deselect list).
- Circular import avoided: `allowlist_training` stores `preview_batch_result` as `Any`.

---

## Preview performance follow-up (same day)

### Problem observed after initial Phase 2 ship

The first portal preview wiring called four logical steps on every **Run preview**:

| Step | What | Cost |
|------|------|------|
| 1 | `compare_allowlists_on_ndjson` (all selected) | 1× full export pass |
| 2 | `run_commit_simulation` (all selected) | 1× full export pass (duplicate of step 1) |
| 3 | `compute_no_op=True` inside step 2 | N× full export passes (one per selected category) |
| 4 | `compute_selection_no_op_tuples` | N× again (duplicate of step 3, for deselect button list) |

For **N** selected categories this was ~**2 + 2N** classification runs. On a 634-ticket export with 24 tuples, preview felt noticeably slower than the pre–Phase 2 single-pass preview.

**No-op** (normative definition from batch plan): a selected category is no-op on an export when adding *only that category* to the reference list changes neither TBC count nor any ticket’s tier assignment (`tbc_delta == 0` and `changed_rows` empty). High no-op rate explains “Low impact expected” verdicts — e.g. 22/24 selected categories not affecting tickets on `run-20260528-export`.

**Deselect button** was always client-side only: it unchecks boxes from `data-no-op-tuples`; it does not re-run preview or update the verdict banner until the user clicks **Run preview** again.

### Thought process / why we changed it

1. **Steps 1 and 2 were redundant.** `run_commit_simulation` already calls `compare_allowlists_on_ndjson` internally and aggregates into `BatchCompareResult.combined`. The portal only needed that one call; the metrics table can render from `batch_result.combined` instead of a separate compare result.

2. **Steps 3 and 4 were redundant.** `compute_selection_no_op_count` already called `compute_selection_no_op_tuples` and took `len()`. Step 4 repeated the same per-tuple ablation only to get the tuple *list* for the deselect button. Fix: add `selection_no_op_tuples` on `BatchCompareResult` and derive count from `len(tuples)` in one pass.

3. **No-op analysis should be opt-in, not default.** Per-tuple ablation is O(N × tickets) — valuable when the analyst suspects many categories won’t matter (rules gap, wrong export), but too expensive for a quick “does this look OK?” preview. Matches the batch CLI pattern (`--compute-no-op` off by default). Analyst-facing checkbox: **“Check which categories have no impact on this export (slower)”** (`compute_no_op` form field, persisted on session as `preview_compute_no_op`).

4. **Verdict band without no-op.** When `compute_no_op=False`, `selection_no_op_count` is `null`; `classify_verdict_band` cannot use the ≥50% no-op rate rule but still uses rule-coverage and TBC/regression heuristics. Banner omits the “X of Y categories had no effect” line; deselect button hidden.

### What changed (files)

| File | Change |
|------|--------|
| `portal_app.py` | Preview uses only `run_commit_simulation`; `result = batch_result.combined`; `compute_no_op` from form |
| `batch_allowlist_analysis.py` | `selection_no_op_tuples` on `BatchCompareResult`; single ablation pass; `_sum_compare_results` copies `bad_satisfaction_only` |
| `allowlist_training.py` | `preview_compute_no_op` session field; `store_preview` reads no-op tuples from batch result |
| `portal_training.py` / `portal_training_copy.py` | Optional no-op checkbox + label |
| `tests/test_portal.py` | Assert checkbox present in preview HTML |

### Bug found while merging

Switching the metrics table to `batch_result.combined` dropped the “Preview limited to tickets with bad CSAT rating” note because `_sum_compare_results` did not copy `bad_satisfaction_only` from the per-file result. Fixed by setting `bad_satisfaction_only=first.bad_satisfaction_only` on the synthetic combined row.

### Preview cost after optimization

| Mode | Approx. export passes |
|------|------------------------|
| Default (no no-op checkbox) | **1** |
| With no-op checkbox, N categories selected | **1 + N** |

Still no shared classification cache between the full simulation and per-tuple ablation — future improvement if large exports remain slow with no-op enabled.

### No-op UX fix (impact column + deselect)

**Bugs:** (1) Deselect button did nothing when category paths contained spaces — no-op tuples were space-joined in `data-no-op-tuples`, so JS `split(/\s+/)` broke encoded values like `B2C|Service Task|...`. (2) No per-row indication of which categories were impactful vs no-op; deselect only appeared when verdict was `rules_needed`.

**Fix:** Add **Impact on export** column plus summary line. Mark no-op rows with `tr.tuple-row--no-op` at render time; deselect button unchecks checkboxes in those rows directly (avoids fragile string matching via `data-*` attributes when tier labels contain spaces or HTML entities).

## Tests

```bash
pytest tests/test_portal.py -q
pytest -q
```

## Not in this pass (Phase 2b)

- Per-tuple ablation in portal
- Multi-file NDJSON preview upload
- Snapshot history picker
