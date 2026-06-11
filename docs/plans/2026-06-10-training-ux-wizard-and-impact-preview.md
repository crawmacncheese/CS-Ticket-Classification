# Training UX — Analyst Wizard & Impact Preview — Implementation Plan

> **For implementer:** When you execute this plan (the actual coding), document your steps, process, and final design decisions in a separate markdown file (e.g. `docs/plans/2026-06-10-training-ux-wizard-and-impact-preview-notes.md`) so the requester can review rationale, catch bugs early, and understand the code. This plan describes *what* to build; that notes file describes *what you did*.

**Goal:** Make the **Training** portal flow usable for non-technical CS analysts by replacing jargon with plain language, adding a guided step wizard, and surfacing **commit verdict** insights from `batch_allowlist_analysis` directly in the preview step — so users know *whether* to commit before writing to `doc/`.

**Architecture:** Keep existing Training backend (`allowlist_training.py`, `allowlist_compare.py`, commit/revert semantics). Refactor **presentation only** in `portal_training.py`, `portal_app.py`, `static/training.js`, and `static/cs_tickets_theme.css`. Reuse `run_commit_simulation()` / `classify_verdict_band()` from `batch_allowlist_analysis.py` for preview enrichment — no duplicate verdict logic.

**Tech stack:** FastAPI HTML templates (inline strings, existing pattern), vanilla JS, existing `batch_allowlist_analysis` module.

**Depends on:** [2026-06-06-allowlist-training-feature.md](./2026-06-06-allowlist-training-feature.md) (shipped), [2026-06-09-training-rule-proposals.md](./2026-06-09-training-rule-proposals.md) (coverage badges + rule preview), [2026-06-09-batch-allowlist-impact-analysis.md](./2026-06-09-batch-allowlist-impact-analysis.md) (View A verdict bands — shipped in `batch_allowlist_analysis.py`).

**Related brief:** [`allowlistupdatefeature.md`](../../allowlistupdatefeature.md) Phase 2 UI simplification.

---

## Context

### What analysts struggle with today

| Pain point | Evidence |
|------------|----------|
| Jargon ("5-tuple", "allow-list") | Phase 2 backlog in training feature plan |
| Single long page | Steps 1–3 rendered sequentially without progress context |
| Preview metrics without recommendation | `compare_result_html` shows TBC delta but not verdict band |
| High no-op tuple commits | `reports/run-20260528-export/summary.md`: **92% selection no-op rate** on 24 tuples |
| Changed tickets lack outcome context | Portal shows id + Tier4 only; batch tool has `gap_fix` / `regression` / `lost_margin` |
| No golden baseline context | Analysts cannot tell if preview TBC is "good" vs historical norm |

### What already works (do not break)

- Training gating: local writable `doc/` only
- Commit → exemplar rows + `training_rules.json`; Revert restores snapshot
- Preview simulates candidate allow-list **and** `rule_specs_new`
- Stale preview banner when selection changes
- Coverage badges: "Already routable" / "Needs routing rule"

### Real impact data (June 2026 runs)

| Run | Tickets | Verdict | Net TBC Δ | No-op rate |
|-----|---------|---------|-----------|------------|
| `run-20260528-export` (634 rows, 24 tuples) | 634 | `rules_needed` | 0 | 92% |
| `run-export-batch-view-a-20260528` (39k rows, 22 tuples) | 39684 | `strong_commit` | +6 | — |

The UI must communicate: **"TBC unchanged but 22/24 categories won't affect any ticket — consider deselecting or adding rules."**

---

## Design decisions

| Topic | Decision | Rationale |
|-------|----------|-----------|
| Terminology | **"Category"** = 5-tuple; **"Reference categories"** = allow-list | Plain language per `CONTEXT.md` glossary intent |
| Wizard | 3 steps: Upload → Review & select → Preview & commit | Maps to existing routes; no new session state machine |
| Progress indicator | CSS stepper in page header; highlight current step | No JS framework |
| Verdict in preview | Call `run_commit_simulation(..., compute_no_op=True)` on preview NDJSON | Reuses batch module; single-file preview is degenerate batch |
| Ablation in portal | **Defer** per-tuple ablation (View B) to Phase 2b of this plan | Expensive on large NDJSON; CLI remains available |
| Golden badge | Compare preview `tbc_new / total` to `golden_baseline.json` rate on fixture scale | Directional hint only — not a commit gate |
| Granular variant badge | Show when Tier1–Tier4 ∈ allow-list with granular `N/A` but upload adds non-`N/A` granular | Deferred from Training Phase 1 |
| Row enrichment | Opt-in "Show details" expands changed-ticket table with outcome + mechanism | Matches batch `enrich_changed_row` fields |
| Copy source | New `portal_training_copy.py` constants dict | Keeps HTML builders readable; no i18n framework |
| Mobile | Responsive tables (horizontal scroll); wizard stacks vertically | Analysts may use laptop only — minimal effort |
| Hosted Training | **Out of scope** | Still local-only per `training_available()` |

### Verdict band → analyst-facing message

| Band | UI label | Recommended action |
|------|----------|-------------------|
| `strong_commit` | **Looks good** | Proceed with commit |
| `review` | **Review changes** | Check changed tickets table before commit |
| `rules_needed` | **Low impact expected** | Many selected categories may not affect tickets; deselect no-ops or ask maintainer about rules |
| `risky` | **Caution** | TBC increased via margin competition; do not commit without maintainer review |

Map `classify_verdict_band()` output 1:1 — do not invent a second verdict system.

### Wizard step mapping

| Step | Route(s) | Visible when |
|------|----------|--------------|
| 1 — Upload | `GET/POST /training/upload` | Index + upload form |
| 2 — Review | `POST /training/upload` → review page | `new_tuples` non-empty |
| 3 — Preview & commit | Same page (preview section + commit) | After upload; preview optional |

Success / cancel / revert pages show stepper with all steps complete or reset.

---

## Functional requirements

| ID | Requirement |
|----|-------------|
| FR-U1 | All user-facing Training copy avoids "5-tuple" and "allow-list" in primary labels (footnotes may mention for maintainers) |
| FR-U2 | Wizard stepper shows current step and completed steps |
| FR-U3 | Step 2 table header uses "Category path" instead of five separate tier column headers (values unchanged) |
| FR-U4 | Granular variant badge when `tier[:4]` allowed with `N/A` granular and upload tuple has specific granular |
| FR-U5 | Preview calls `run_commit_simulation` and renders verdict band + plain-language recommendation |
| FR-U6 | Preview shows `selection_no_op_count / n_selected` when `compute_no_op=True` |
| FR-U7 | Preview shows gap-fix vs regression counts from `outcome_counts` |
| FR-U8 | Changed tickets table: default id + old→new tier4; opt-in expand shows `outcome_type`, `gap_fix_mechanism`, `tbc_reason_new` |
| FR-U9 | Golden hint badge: "Preview TBC X% vs golden fixture baseline Y%" (informational) |
| FR-U10 | Commit button label: **"Save selected categories"**; confirm dialog restates rows + rules count |
| FR-U11 | No change to commit/revert/cancel disk semantics |
| FR-U12 | `pytest tests/test_portal.py` extended for new HTML fragments |

---

## Phase 1 — Copy & wizard shell

### Task 1 — Copy constants module

**Files (new):**

- `src/cs_tickets/portal_training_copy.py`

**Content (examples):**

```python
TRAINING_TITLE = "Update categories"
STEP_LABELS = ("Upload file", "Review new categories", "Preview & save")
VERDICT_MESSAGES = {
    "strong_commit": ("Looks good", "Saving these categories should improve or maintain classification."),
    "review": ("Review changes", "Some tickets would change — review the list below before saving."),
    "rules_needed": ("Low impact expected", "Many selected categories may not change any tickets on this export."),
    "risky": ("Caution", "Manual review tickets increased — talk to a classifier maintainer before saving."),
}
```

### Task 2 — Wizard stepper component

**Files (modify):**

- `src/cs_tickets/portal_training.py` — `training_wizard_html(current_step: int, *, completed: int)`
- `src/cs_tickets/static/cs_tickets_theme.css` — `.training-wizard`, `.wizard-step`, `.wizard-step--active`, `.wizard-step--done`

**Markup pattern:**

```html
<nav class="training-wizard" aria-label="Training progress">
  <ol>
    <li class="wizard-step wizard-step--done">1. Upload file</li>
    <li class="wizard-step wizard-step--active">2. Review new categories</li>
    <li class="wizard-step">3. Preview & save</li>
  </ol>
</nav>
```

Insert at top of every Training page body via `training_page_shell(..., wizard=...)`.

### Task 3 — Plain-language page rewrites

**Files (modify):**

- `src/cs_tickets/portal_training.py` — checklist, preview controls, footer
- `src/cs_tickets/portal_app.py` — index copy, success/cancel/revert messages

**Replacements (minimum):**

| Before | After |
|--------|-------|
| Allow-list Training | Update categories |
| new tier combination(s) | new categor(ies\|y) not in the reference list |
| Select tier combinations to add to the allow-list | Select categories to add |
| Commit selected | Save selected categories |
| Step 3 — Preview changes (optional) | Check impact on a ticket export (optional) |
| Undo last update | Undo last save |

Keep `<code>doc/</code>` references in maintainer footnotes only.

---

## Phase 2 — Impact preview integration (View A)

### Task 4 — Preview endpoint uses commit simulation

**Files (modify):**

- `src/cs_tickets/portal_app.py` — `training_preview` route

**Change:**

After existing `compare_allowlists_on_ndjson` call (keep for backward compat in session), also run:

```python
from cs_tickets.batch_allowlist_analysis import run_commit_simulation

batch = run_commit_simulation(
    [preview_path],
    allow_old,
    allow_new,
    selected_tuples=selected,
    rule_specs_new=rule_specs_new,
    compute_no_op=True,
    enrich_changed_rows=True,
)
store_preview(session, result, selected, batch_result=batch, ...)
```

Extend `_TrainingSession` / `store_preview` to hold optional `BatchCompareResult` alongside `AllowlistCompareResult`.

**Performance:** For portal preview, cap changed-row HTML at 50 rows; full count in summary. Add `limit` param only if preview &gt;30s on 634-row export — measure in notes.

### Task 5 — Verdict banner HTML

**Files (modify):**

- `src/cs_tickets/portal_training.py` — `training_verdict_banner_html(batch: BatchCompareResult)`

**Renders:**

- Colored banner (`verdict--strong`, `verdict--review`, `verdict--rules-needed`, `verdict--risky`)
- Headline from `VERDICT_MESSAGES[batch.verdict_band]`
- Bullet stats: net TBC Δ, gap fixes, regressions, reroutes, no-op tuples
- Footnote when `rules_needed`: link to maintainer doc anchor (README Training section)

### Task 6 — Enriched changed-rows table

**Files (modify):**

- `src/cs_tickets/portal_training.py` — replace inline sample in `compare_result_html` usage OR extend `compare_result_html` with `detailed=False` default

**Prefer:** New `training_changed_rows_html(changed_rows, *, expanded: bool)` in `portal_training.py` to avoid breaking CLI/batch consumers of `compare_result_html`.

**Columns (expanded):**

| id | outcome | old tier4 | new tier4 | why (tbc_reason) |

**JS toggle:** `#show-changed-details` checkbox reveals mechanism column.

### Task 7 — Golden baseline hint

**Files (modify):**

- `src/cs_tickets/portal_training.py`
- Read `tests/fixtures/golden_baseline.json` at module load or via small helper

**Display:**

```text
Golden fixture reference: ≤40% TBC (5 tickets). Your preview: 9.5% TBC on 634 tickets.
```

Only show when fixture file exists (dev/CI); hide silently in deployed image if missing.

**Do not block commit** on golden comparison — preview NDJSON ≠ golden fixture.

---

## Phase 3 — Checklist UX polish

### Task 8 — Granular variant badge

**Files (modify):**

- `src/cs_tickets/allowlist_training.py` or `portal_training.py` — helper `granular_variant_hint(tup, allow: AllowList) -> str | None`
- Logic: `(tup[:4] + ("N/A",)) in allow.tuples` and `tup[4] != "N/A"`

**UI:** Badge **"Adds detail level"** next to category path.

### Task 9 — Category path column

Collapse five tier columns into one **"Category path"** column:

```text
B2C → Service Task → Sales Leads → Rate or Renewal Inquiry
```

Granular shown on second line when not `N/A`.

Keeps checkbox + tickets count + coverage badge columns.

### Task 10 — Commit confirmation dialog

**Files (modify):**

- `src/cs_tickets/static/training.js`

On `#training-commit-btn` click:

```javascript
const n = selectedCheckboxes().length;
if (!confirm(`Save ${n} categor${n === 1 ? 'y' : 'ies'} to the reference workbook? This updates files in doc/ until you undo.`)) {
  event.preventDefault();
}
```

### Task 11 — Select low-impact helper (optional quick win)

When `batch_result.verdict_band === "rules_needed"` and `selection_no_op_count` known:

Show button **"Deselect categories with no impact"** — client-side only, checks tuples that preview metadata marks as no-op (pass list from server as `data-no-op-tuples` on review page).

**Server:** include `no_op_tuples: list[str]` (encoded) on review page when preview has been run.

---

## Phase 2b — Deferred (document only)

| Feature | Why deferred |
|---------|--------------|
| Per-tuple ablation (View B) in portal | Slow on large NDJSON; use `tools/batch_allowlist_compare.py --ablation` |
| Multi-file NDJSON upload in preview | Batch CLI handles; portal stays single-file |
| Snapshot history picker | Separate plan |
| Taxonomy.csv auto-sync | Separate plan |

---

## Implementation tasks (ordered)

| Order | Task | Est. |
|-------|------|------|
| 1 | Task 1 — copy module | 0.25 d |
| 2 | Task 2 — wizard stepper CSS/HTML | 0.5 d |
| 3 | Task 3 — plain-language rewrites | 0.5 d |
| 4 | Task 4 — preview + `run_commit_simulation` wiring | 1 d |
| 5 | Task 5 — verdict banner | 0.5 d |
| 6 | Task 6 — enriched changed rows + JS toggle | 1 d |
| 7 | Task 7 — golden hint | 0.25 d |
| 8 | Task 8 — granular variant badge | 0.5 d |
| 9 | Task 9 — category path column | 0.5 d |
| 10 | Task 10 — commit confirm dialog | 0.25 d |
| 11 | Task 11 — deselect no-ops button (optional) | 0.5 d |

**Total:** ~5–6 days

---

## Portal UI mock (structural)

```text
┌─────────────────────────────────────────────────────────┐
│  Update categories                                       │
│  [1 Upload ✓] — [2 Review ●] — [3 Preview & save]         │
├─────────────────────────────────────────────────────────┤
│  Found 24 new categories not in the reference list.      │
│                                                          │
│  ┌─ Looks good / Review / Low impact / Caution ─────┐   │
│  │  Preview on 634 tickets: TBC 60 → 60 (no change)  │   │
│  │  22 of 24 selected categories had no effect        │   │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
│  [table: select | category path | tickets | coverage]    │
│                                                          │
│  Check impact (optional): [file] [Run preview]           │
│  [ ] Show ticket change details                          │
│                                                          │
│  [Save selected categories]  [Cancel]                      │
└─────────────────────────────────────────────────────────┘
```

---

## Acceptance criteria

### Copy & wizard

- [ ] No primary UI label contains "5-tuple"
- [ ] Wizard stepper visible on all Training pages with correct active step
- [ ] Success page uses "saved" not "committed" in analyst-facing text

### Impact preview

- [ ] Preview renders verdict band matching `classify_verdict_band()` for same inputs as CLI
- [ ] `rules_needed` shown when `run-20260528-export` scenario reproduced (high no-op rate)
- [ ] `strong_commit` shown when net TBC improves with gap fixes
- [ ] Stale banner still appears when selection changes after preview
- [ ] `compute_no_op=True` does not run on initial upload (preview only)

### Checklist

- [ ] Granular variant badge appears for controlled test tuple
- [ ] Category path column readable for non-technical reviewer

### Non-regression

- [ ] `pytest tests/test_portal.py tests/test_allowlist_session.py -q` passes
- [ ] Training cancel/commit/revert disk behavior unchanged
- [ ] `compare_result_html` still works for sessions without `batch_result`

---

## Test plan

### Automated

**`tests/test_portal.py` additions:**

```python
def test_training_review_shows_wizard_step_2(client, writable_doc_env): ...
def test_training_preview_shows_verdict_banner_rules_needed(client, ...): ...
def test_training_checklist_granular_variant_badge(client, ...): ...
```

Use existing fixtures from `test_allowlist_session.py` and `training_tbc_probe.ndjson`.

### Manual (`testcase.md` appendix)

1. Upload `20260528_-_CS_ticket_new_categorizations.xlsx` (or synthetic with novel tuples)
2. Select all → preview May 14 NDJSON
3. Verify verdict banner + no-op count
4. Toggle "Show ticket change details"
5. Save → Undo last save → confirm disk restored

---

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Preview latency doubles (compare + simulation) | Reuse single classification pass where possible; share caches between compare and simulation in Task 4 refactor |
| Verdict confuses analysts | Plain-language labels + recommended action; footnote links to README |
| `rules_needed` feels like failure | Copy: "Low impact expected" not "Error"; explain rules vs categories |
| Golden hint misleading on different export | Label as "fixture reference only" |
| HTML duplication | Copy constants module; single wizard helper |

---

## Out of scope

- Hosted Training on read-only deploys
- Taxonomy.csv auto-sync
- Full View B ablation in browser
- Authentication / SSO
- React/Vue frontend rewrite

---

## Related documents

- [2026-06-09-batch-allowlist-impact-analysis.md](./2026-06-09-batch-allowlist-impact-analysis.md) — View A verdict semantics
- [2026-06-06-allowlist-training-feature.md](./2026-06-06-allowlist-training-feature.md) — Phase 2 UI backlog (superseded by this plan)
- [testcase.md](../../testcase.md) — manual Training checklist
- [CONTEXT.md](../../CONTEXT.md) — domain terms
