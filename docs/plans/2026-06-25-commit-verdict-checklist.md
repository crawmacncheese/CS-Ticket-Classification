# Commit Verdict Checklist — Design Document

> **For implementer:** When you execute this plan, document steps and implementation notes in `docs/plans/2026-06-25-commit-verdict-checklist-notes.md`. This document describes *what* to build and *why*; that notes file describes *what you did*.

**Goal:** Make Training commit preview verdicts **explicit and auditable** by decomposing `classify_verdict_band()` into a structured binary checklist (Criteria Generator) and a band synthesizer (Verdict Generator), without changing classification behavior, verdict bands, or portal commit semantics.

**Users (from [prd.md](../prd.md)):**

| Persona | Primary flow | UX need |
|---------|--------------|---------|
| **CS analyst / team lead** | Training preview (`/training`) | Understand *why* the verdict banner says "Looks Good" vs "Caution" — not just the headline label |
| **Classifier maintainer** | `tools/run_allowlist_test.py`, batch CLI | Assert on specific failed gates in CI; debug verdict bands without re-reading Python |
| **Taxonomy owner** | Learn preview | Same checklist transparency when practicing allow-list updates |

**Architecture:** New pure module `commit_verdict_checklist.py` sits between `BatchCompareResult` (input) and existing consumers (`classify_verdict_band`, `write_batch_reports`, portal verdict banner). No changes to `run_commit_simulation()`, `compare_allowlists_on_ndjson()`, or the classifier hot path.

**Tech stack:** Python 3.11, dataclasses, existing `BatchCompareResult` / `AllowlistCompareResult`; optional portal HTML in `portal_training.py` / `portal_learn.py` (Phase 2).

**Depends on:** [2026-06-09-batch-allowlist-impact-analysis.md](./2026-06-09-batch-allowlist-impact-analysis.md) (verdict bands, `commit_verdict.json` contract), [2026-06-09-allowlist-testing-architecture.md](./2026-06-09-allowlist-testing-architecture.md) (metrics definitions), [2026-06-10-training-ux-wizard-and-impact-preview.md](./2026-06-10-training-ux-wizard-and-impact-preview.md) (verdict banner, no second recommendation system), [design.md](../design.md) (explainability principle).

**Inspiration:** Agent-as-a-Judge / Auto-Eval Judge research — modular evaluation via explicit binary criteria rather than opaque holistic scoring. This project adopts the **checklist decomposition pattern** only; it does **not** introduce LLM judges or trace evaluation of agent logs.

---

## Context

### Pain points (observed)

| Area | Problem | Impact |
|------|---------|--------|
| **Verdict opacity** | `classify_verdict_band()` returns a band + short reason strings like `default_review` | Analysts see "Review Changes" but cannot tell which gates passed or failed |
| **Implicit compound rules** | `risky` requires net TBC regression *and* unchanged zero-candidate *and* margin-loss increase | Maintainer must read source to understand the conjunction |
| **Diagnostic metrics orphaned** | `commit_verdict.json` already exposes `gap_fix_by_mechanism`, `margin_loss_*`, `below_threshold_*` | These inform interpretation but are not wired into the verdict narrative |
| **Test fragility** | `test_verdict_band_classification` asserts band only | Cannot assert *which* criterion failed when tuning thresholds |
| **Portal copy gap** | `VERDICT_MESSAGES` gives headline + one sentence | No structured "why" section under the banner |

### What already works (do not break)

- Four verdict bands: `strong_commit`, `review`, `rules_needed`, `risky`
- `VERDICT_MESSAGES` in `portal_training_copy.py` / `portal_learn_copy.py` — 1:1 band → analyst headline
- `classify_verdict_band()` evaluation order (first match wins)
- `commit_verdict.json` `schema_version: 1` fields consumed by `run_allowlist_test.py`
- Bands are **advisory only** — never block Training commit
- `BatchCompareResult` shape and `run_commit_simulation()` pipeline

### Current verdict logic (reference)

Today `classify_verdict_band()` in `batch_allowlist_analysis.py` evaluates gates in strict order:

1. `selection_no_op_rate >= 0.5` (only when `selection_no_op_count` is not `null`) → `rules_needed`
2. `tuples_with_rules_count < 0.5 * n_selected` → `rules_needed`
3. `net_tbc < 0` AND `zero_candidate_new == zero_candidate_old` AND `margin_loss_new > margin_loss_old` → `risky`
4. `net_tbc > 0` AND `gap_fix > 0` AND `regression <= gap_fix` → `strong_commit`
5. Else → `review`

The checklist design **preserves this exact semantics**. The refactor makes each gate visible; it does not change thresholds or ordering.

---

## Design decisions

### D1 — Separate Criteria Generator from Verdict Generator

| Decision | Rationale |
|----------|-----------|
| Two functions: `build_commit_checklist()` then `classify_verdict_from_checklist()` | Mirrors Agent-as-a-Judge modularity; allows portal to show full checklist even when band is `review` |
| `evaluate_commit_verdict()` composes both | Single entry point for `run_commit_simulation()` and tests |

**Rejected:** Inline checklist dict inside `classify_verdict_band()` — harder to test individual gates and serialize to JSON.

### D2 — New module file, not inline in `batch_allowlist_analysis.py`

| Decision | Rationale |
|----------|-----------|
| `src/cs_tickets/commit_verdict_checklist.py` | Keeps `batch_allowlist_analysis.py` focused on simulation/aggregation; checklist is a reusable evaluation layer |
| `batch_allowlist_analysis.classify_verdict_band()` becomes a thin wrapper | Zero call-site churn in portal and CLI |

**Rejected:** New package under `feedback/` — verdict evaluation is Training/batch concern, not feedback mining.

### D3 — Deterministic gates only; no LLM criteria generation

| Decision | Rationale |
|----------|-----------|
| All checklist items derived from `BatchCompareResult` numeric fields | Aligns with [prd.md](../prd.md) non-goal: no ML/LLM in production path |
| Questions are fixed strings keyed by stable `id` | Analyst-facing copy can evolve in `portal_training_copy.py` without breaking JSON consumers |

**Rejected (Phase 1):** Auto-generating per-tuple criteria from tier labels via LLM — valuable later for tuple-specific review, out of scope here.

**Future extension:** `build_tuple_criteria(selected_tuples, exemplar_rows)` as optional advisory layer on top of commit gates.

### D4 — Checklist evaluates ALL gates; verdict uses PRIORITY rules

| Decision | Rationale |
|----------|-----------|
| `build_commit_checklist()` returns every item with `pass` / `fail` / `skip` / `na` | Full transparency — analysts see margin-loss even when band is `rules_needed` |
| `classify_verdict_from_checklist()` applies **ordered priority**, not "most failures win" | Preserves existing first-match semantics; a `rules_needed` gate blocks `strong_commit` even if impact checks pass |

**Rejected:** Deriving band from pass/fail counts (e.g. majority vote) — would change behavior on mixed results.

### D5 — `skip` vs `na` for unavailable prerequisites

| Decision | Rationale |
|----------|-----------|
| `skip` — check not evaluated because prerequisite data is missing (e.g. `selection_no_op_count is null`) | Portal can show "Enable no-op analysis to evaluate this gate" |
| `na` — check does not apply (e.g. `n_selected == 0`, which should not occur in practice) | Distinguishes "we chose not to run" from "not applicable" |
| Skipped checks do **not** count as `failed` in summary counts | Avoids alarming analysts when optional analysis was not run |

### D6 — Stable check `id` values as API contract

| Decision | Rationale |
|----------|-----------|
| Machine ids like `rule_coverage_majority`, `net_tbc_regressed` | `run_allowlist_test.py` can assert `checklist.items[id=rule_coverage_majority].status == fail` |
| ids never renamed without `schema_version` bump | JSON consumers and CI fixtures depend on them |

**Rejected:** Numeric check indices — fragile when inserting new gates.

### D7 — Four check categories for grouping in UI

| Category | Contains | Portal display |
|----------|----------|----------------|
| `coverage` | Rule coverage, no-op rate | "Will these categories actually route tickets?" |
| `impact` | Net TBC, gap fixes, regressions, reroutes | "What changes on this export?" |
| `mechanism` | zero_candidate, margin_loss, below_threshold, gap_fix_by_mechanism | "Why did tickets move?" |
| `data_quality` | Export size, duplicate ticket IDs | "Is this preview trustworthy?" |

**Rationale:** Matches interpretation tree in [2026-06-09-allowlist-testing-architecture.md](./2026-06-09-allowlist-testing-architecture.md) — coverage vs impact vs mechanism.

### D8 — `severity` is informational; never blocks commit

| Decision | Rationale |
|----------|-----------|
| `severity: fail` on a check means "this gate can drive a negative band" | Not a hard failure — Training commit remains allowed |
| `severity: info` for diagnostic-only checks | e.g. `allowlist_gap_fixes` explains mechanism without affecting band |

Consistent with existing product rule: verdict bands are labels, not portal commit blockers.

### D9 — `observed` and `threshold` dicts on every item

| Decision | Rationale |
|----------|-----------|
| `observed` — raw values used in evaluation | Enables JSON-only debugging without re-running simulation |
| `threshold` — expected bound when applicable | Makes binary question auditable: "22 >= 11" for 50% rule coverage |
| `detail` — human sentence on `fail` or `warn` | Portal checklist row subtitle |

**Rejected:** Storing only `pass`/`fail` — loses the evidence trail (Agent-as-a-Judge "proof snippet" analogue at aggregate level).

### D10 — `schema_version: 2` additive JSON extension

| Decision | Rationale |
|----------|-----------|
| Keep `verdict_band`, `verdict_reasons`, all v1 fields | `run_allowlist_test.py` assertions on `verdict_band` unchanged |
| Add `checklist` object with `passed`, `failed`, `skipped`, `items[]` | New consumers opt in; old tools ignore unknown keys |
| Bump `schema_version` to `2` when `checklist` present | Explicit contract for parsers |

**Rejected:** Replacing `verdict_reasons` with checklist-only — breaks existing reports and markdown summaries.

### D11 — Verdict band derived from checklist, not duplicated logic

| Decision | Rationale |
|----------|-----------|
| `classify_verdict_from_checklist()` reads check statuses by `id` | Single source of truth for band rules |
| `verdict_reasons` populated from triggering check ids + legacy reason strings | Backward compatibility with `commit_verdict.json` consumers expecting `net_tbc_improved_with_gap_fixes` style strings |

Implementation pattern:

```python
def classify_verdict_from_checklist(checklist):
    by_id = {c.id: c for c in checklist}
    # Priority 1: rules_needed triggers
    if by_id["selection_mostly_no_op"].status == FAIL:
        return "rules_needed", ["selection_no_op_rate>=0.5"]
    if by_id["rule_coverage_majority"].status == FAIL:
        return "rules_needed", ["tuples_with_rules_count<..."]
    # ... same order as today
```

**Rejected:** Maintaining parallel if/else in two places — guaranteed drift.

### D12 — Mechanism checks are diagnostic by default

| Decision | Rationale |
|----------|-----------|
| `allowlist_gap_fixes`, `scoring_recovery_fixes`, `below_threshold_*` delta checks → `severity: info`, do not drive band alone | Already surfaced in metrics table; checklist adds yes/no framing |
| Only `margin_loss_increased` + `zero_candidate_unchanged` participate in `risky` compound | Matches current code exactly |

**Rationale:** The batch impact plan already warns analysts not to trust `gap_fix_count` alone — mechanism breakdown belongs in checklist for education, not automatic band escalation.

### D13 — Portal checklist is Phase 2; backend is Phase 1

| Decision | Rationale |
|----------|-----------|
| Phase 1: module + JSON + pytest parity | Unblocks CLI/CI immediately |
| Phase 2: `commit_checklist_html()` collapsible section under verdict banner | Presentation-only; reuses Training progressive-disclosure pattern from [2026-06-24-ticket-preview-tbc-reasons.md](./2026-06-24-ticket-preview-tbc-reasons.md) |

**Rejected:** Shipping portal UI before backend parity tests — risks displaying checklist that disagrees with band.

### D14 — No changes to `BatchCompareResult` dataclass

| Decision | Rationale |
|----------|-----------|
| Checklist computed on demand from existing fields | Avoids migration of `run_commit_simulation()` return type and all portal session code |

Optional: cache `CommitVerdict` on `BatchCompareResult` later if profiling shows repeated evaluation — not needed at current scale.

### D15 — Check item order is normative and stable

| Decision | Rationale |
|----------|-----------|
| Fixed order: data_quality → coverage → impact → mechanism | Snapshot tests and portal rendering depend on consistent ordering |
| Within category, order matches verdict priority where applicable | Coverage gates before impact gates |

---

## Module interface

### File: `src/cs_tickets/commit_verdict_checklist.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal

from cs_tickets.batch_allowlist_analysis import BatchCompareResult

CheckCategory = Literal["coverage", "impact", "mechanism", "data_quality"]
CheckSeverity = Literal["info", "warn", "fail"]


class CheckStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    NA = "na"


@dataclass(frozen=True)
class CommitCheckItem:
    id: str
    question: str
    status: CheckStatus
    category: CheckCategory
    severity: CheckSeverity
    observed: dict[str, Any]
    threshold: dict[str, Any] | None = None
    detail: str | None = None


@dataclass(frozen=True)
class CommitVerdict:
    band: str
    band_reasons: list[str]
    checklist: tuple[CommitCheckItem, ...]
    passed: int
    failed: int
    skipped: int


def build_commit_checklist(result: BatchCompareResult) -> tuple[CommitCheckItem, ...]: ...

def classify_verdict_from_checklist(
    checklist: tuple[CommitCheckItem, ...],
) -> tuple[str, list[str]]: ...

def evaluate_commit_verdict(result: BatchCompareResult) -> CommitVerdict: ...

def checklist_to_dict(verdict: CommitVerdict) -> dict[str, Any]: ...
```

### Integration points

| Consumer | Change |
|----------|--------|
| `batch_allowlist_analysis.classify_verdict_band()` | Delegate to `evaluate_commit_verdict(result)` |
| `batch_allowlist_analysis.write_batch_reports()` | Add `checklist` key; set `schema_version: 2` |
| `portal_training.py` | Phase 2: render `commit_checklist_html(evaluate_commit_verdict(batch))` |
| `portal_learn.py` | Phase 2: same helper |
| `tests/test_batch_allowlist_analysis.py` | Parity tests + optional per-check assertions |
| `tools/run_allowlist_test.py` | Optional `assertions.checklist` block (Phase 3) |

---

## Check catalog (normative)

### Data quality

| `id` | Question | PASS | FAIL | SKIP/NA | Severity | Drives band |
|------|----------|------|------|---------|----------|-------------|
| `export_has_tickets` | Did the preview classify at least one ticket? | `combined.total > 0` | `total == 0` | — | info | No |
| `no_duplicate_ticket_ids` | Were duplicate ticket IDs avoided across files? | `duplicate_ticket_ids == []` | list non-empty | — | warn | No |

### Coverage

| `id` | Question | PASS | FAIL | SKIP | Severity | Drives band |
|------|----------|------|------|------|----------|-------------|
| `rule_coverage_majority` | Do at least half of selected categories have routing rules? | `tuples_with_rules_count >= ceil(0.5 * n_selected)` | below threshold | `n_selected == 0` → NA | fail | **Yes → rules_needed** |
| `selection_not_mostly_no_op` | Did most selected categories change tickets on this export? | `no_op_rate < 0.5` | `no_op_rate >= 0.5` | `selection_no_op_count is null` | fail | **Yes → rules_needed** |

Note: `selection_mostly_no_op` is the **fail** condition id used internally by verdict priority (alias of inverted `selection_not_mostly_no_op`).

### Impact

| `id` | Question | PASS | FAIL | Severity | Drives band |
|------|----------|------|------|----------|-------------|
| `net_tbc_improved` | Did manual-review (TBC) count decrease? | `tbc_old > tbc_new` | else | info | Contributes to **strong_commit** |
| `net_tbc_regressed` | Did manual-review (TBC) count increase? | `tbc_old < tbc_new` | else | info | Contributes to **risky** |
| `has_gap_fixes` | Did any TBC tickets receive a concrete tier? | `gap_fix > 0` | `gap_fix == 0` | info | Contributes to **strong_commit** |
| `regressions_within_gap_fixes` | Are mis-routes no worse than fixes? | `regression <= gap_fix` | `regression > gap_fix` | warn | Contributes to **strong_commit** |
| `has_regressions` | Did any tickets move into TBC? | `regression > 0` | `regression == 0` | info | No (diagnostic) |
| `has_reroutes` | Did any classified tickets change tier without TBC transition? | `reroute > 0` | `reroute == 0` | info | No |

### Mechanism

| `id` | Question | PASS | FAIL | Severity | Drives band |
|------|----------|------|------|----------|-------------|
| `zero_candidate_unchanged` | Did allow-list-gap TBC count stay the same? | `zero_candidate_new == zero_candidate_old` | differ | info | Contributes to **risky** |
| `margin_loss_increased` | Did contested TBC (lost margin) increase? | `margin_loss_new > margin_loss_old` | else | info | Contributes to **risky** |
| `allowlist_gap_fixes_present` | Were any fixes from missing categories? | `allowlist_gap > 0` | `== 0` | info | No |
| `scoring_recovery_fixes_present` | Were any fixes from scoring competition? | `scoring_recovery > 0` | `== 0` | info | No |
| `below_threshold_improved` | Did weak-signal TBC decrease? | `below_threshold_new < below_threshold_old` | else | info | No |
| `allowlist_filtered_improved` | Did rules-blocked TBC decrease? | `allowlist_filtered_new < allowlist_filtered_old` | else | info | No |

---

## Verdict synthesis rules (normative)

Evaluate in order; **first matching rule wins**:

| Priority | Band | Condition (all must hold) | `band_reasons` entry |
|----------|------|---------------------------|----------------------|
| 1 | `rules_needed` | `selection_not_mostly_no_op` == FAIL (not SKIP) | `selection_no_op_rate>=0.5` |
| 2 | `rules_needed` | `rule_coverage_majority` == FAIL | `tuples_with_rules_count<...` |
| 3 | `risky` | `net_tbc_regressed` == PASS AND `zero_candidate_unchanged` == PASS AND `margin_loss_increased` == PASS | `net_tbc_regression_with_margin_loss_increase` |
| 4 | `strong_commit` | `net_tbc_improved` == PASS AND `has_gap_fixes` == PASS AND `regressions_within_gap_fixes` == PASS | `net_tbc_improved_with_gap_fixes` |
| 5 | `review` | default | `default_review` |

**Important:** For priority 3, `zero_candidate_unchanged` PASS means the counts are equal (the check id names the condition required for risky, not the failure mode). For priority 4, `net_tbc_improved` PASS means TBC went down.

---

## JSON schema (`commit_verdict.json` v2)

```json
{
  "schema_version": 2,
  "verdict_band": "strong_commit",
  "verdict_reasons": ["net_tbc_improved_with_gap_fixes"],
  "checklist": {
    "passed": 9,
    "failed": 1,
    "skipped": 2,
    "items": [
      {
        "id": "rule_coverage_majority",
        "question": "Do at least half of selected categories have routing rules?",
        "status": "pass",
        "category": "coverage",
        "severity": "fail",
        "observed": {
          "tuples_with_rules_count": 22,
          "selected_tuple_count": 22
        },
        "threshold": { "min_fraction": 0.5 },
        "detail": null
      }
    ]
  },
  "combined_is_synthetic": true,
  "net_tbc_improvement": 4
}
```

All v1 fields remain present. Parsers should check `schema_version >= 2` before reading `checklist`.

---

## Portal UX (Phase 2)

### Layout

```text
┌─ Verdict banner (unchanged) ─────────────────────────────────┐
│  Looks Good — Saving these categories should improve…          │
└────────────────────────────────────────────────────────────────┘
┌─ Why this verdict? [collapsed by default] ─────────────────────┐
│  Coverage                                                     │
│    ✓ At least half of selected categories have routing rules │
│    — Most selected categories changed tickets (not analyzed) │
│  Impact                                                       │
│    ✓ Manual-review count decreased (18 → 14)                 │
│    ✓ TBC tickets received concrete tiers (4 fixes)           │
│  …                                                            │
└───────────────────────────────────────────────────────────────┘
```

### Design decisions (portal)

| Decision | Rationale |
|----------|-----------|
| Collapsed by default | Avoids banner + checklist competing for attention ([2026-06-10-portal-ux-improvement.md](./2026-06-10-portal-ux-improvement.md)) |
| Reuse `training.js` checkbox/disclosure pattern | Consistency with changed-tickets detail toggle |
| Status icons: ✓ / ✗ / — for pass / fail / skip | No new chart library |
| Copy from checklist `question` field, not re-derived in portal | Single source of truth |
| Do not add a fifth verdict band or override `VERDICT_MESSAGES` | Explicit non-goal from Training UX plan |

---

## Testing strategy

### Parity tests (required)

Extend `tests/test_batch_allowlist_analysis.py`:

1. Existing `test_verdict_band_classification` parametrized cases must pass via `evaluate_commit_verdict().band`.
2. New `test_checklist_triggers_match_band` — for each parametrized case, assert the triggering check ids match the priority table above.
3. `test_checklist_stable_order` — snapshot of item `id` sequence.

### Fixture cases (from existing tests)

| tbc_old | tbc_new | gap_fix | regression | margin | rules | expected | Triggering checks |
|---------|---------|---------|------------|--------|-------|----------|-------------------|
| 3 | 2 | 2 | 1 | 0→0 | 5/5 | `strong_commit` | net_tbc_improved, has_gap_fixes, regressions_within_gap_fixes |
| 2 | 5 | 0 | 1 | 2→5 | 5/5 | `risky` | net_tbc_regressed, zero_candidate_unchanged, margin_loss_increased |
| 1 | 1 | 0 | 0 | 0→0 | 1/5 | `rules_needed` | rule_coverage_majority |
| 1 | 1 | 0 | 0 | 0→0 | 5/5 | `review` | default (no priority match) |

### JSON round-trip

`test_checklist_to_dict_schema` — `checklist_to_dict(evaluate_commit_verdict(fixture))` contains required keys and valid statuses.

---

## Implementation phases

### Phase 1 — Backend (this plan)

| Task | Module |
|------|--------|
| Add `commit_verdict_checklist.py` with types + evaluation | new file |
| Refactor `classify_verdict_band()` to delegate | `batch_allowlist_analysis.py` |
| Emit `checklist` in `write_batch_reports()` | `batch_allowlist_analysis.py` |
| Parity + trigger tests | `tests/test_batch_allowlist_analysis.py` |

### Phase 2 — Portal presentation

| Task | Module |
|------|--------|
| `commit_checklist_html()` | `portal_training.py` or new `portal_verdict.py` |
| Collapsible section + CSS | `static/cs_tickets_theme.css`, `static/training.js` |
| Learn preview parity | `portal_learn.py` |

### Phase 3 — CI assertions (optional)

| Task | Module |
|------|--------|
| `assertions.checklist` in YAML test configs | `tools/run_allowlist_test.py` |

---

## Non-goals

- LLM-generated criteria or Agent-as-a-Judge trace evaluation
- Per-ticket proof snippets in checklist (belongs to ticket preview / `RuleEvidence` — separate Artifact Parser track)
- Blocking Training commit based on checklist failures
- Changing verdict band thresholds or adding new bands
- Modifying `AllowlistCompareResult`, classifier, or allow-list merge semantics
- Human gold-set alignment metrics (future Phase 3 feedback loop per [prd.md](../prd.md))

---

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Checklist and band logic drift | Single `classify_verdict_from_checklist()`; parity parametrized tests |
| Analyst overload from too many checks | Group by category; collapse by default; severity hides info-only rows optionally |
| `schema_version` confusion | Document v1 vs v2; v1 fields unchanged |
| Skipped no-op check misread as pass | Distinct `skip` status + portal copy "Not analyzed — enable no-op check" |
| Combined synthetic metrics misinterpreted | `export_has_tickets` + duplicate ID warn checks in data_quality category |

---

## Future extensions (out of scope)

| Extension | Agent-as-a-Judge module | Project touchpoint |
|-----------|-------------------------|-------------------|
| Per-tuple criteria from tier labels + exemplars | Criteria Generator (LLM) | `rule_generator.py`, Training upload |
| Proof snippets per changed ticket | Artifact Content Parser | `portal_ticket_preview.py`, `RuleEvidence` |
| Factual vs logical check routing | Criteria Check Composer | `classifier_rules.json` vs `classify.py` computed blocks |
| Analyst gold-set alignment | Human evaluation | `feedback/` loop, new `tools/eval_alignment.py` |

---

## Success criteria

1. `evaluate_commit_verdict(result).band` matches `classify_verdict_band(result)` for all existing parametrized fixtures.
2. `commit_verdict.json` with `schema_version: 2` includes `checklist` with stable item ids and correct pass/fail/skip counts.
3. `run_allowlist_test.py` default assertions on `verdict_band` unchanged.
4. No change to classification output, Training commit disk semantics, or portal band headlines.
5. Phase 2: portal checklist rows match JSON emitted for the same `BatchCompareResult`.

---

## References

- [design.md](../design.md) — explainability principle, architecture
- [prd.md](../prd.md) — non-goals (no ML hot path)
- [2026-06-09-batch-allowlist-impact-analysis.md](./2026-06-09-batch-allowlist-impact-analysis.md) — verdict bands, `commit_verdict.json`
- [2026-06-09-allowlist-testing-architecture.md](./2026-06-09-allowlist-testing-architecture.md) — metrics contract
- [2026-06-10-training-ux-wizard-and-impact-preview.md](./2026-06-10-training-ux-wizard-and-impact-preview.md) — verdict banner rules
- `src/cs_tickets/batch_allowlist_analysis.py` — `classify_verdict_band()`, `write_batch_reports()`
- `reports/run-1/commit_verdict.json` — example v1 output
