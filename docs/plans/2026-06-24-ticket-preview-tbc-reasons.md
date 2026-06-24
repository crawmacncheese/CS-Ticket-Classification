# Ticket Preview & TBC Reason Visibility — Implementation Plan

> **For implementer:** When you execute this plan, document steps and design decisions in `docs/plans/2026-06-24-ticket-preview-tbc-reasons-notes.md`. This plan describes *what* to build; that notes file describes *what you did*.

**Goal:** After a **Categorize tickets** run or an **allowlist update preview**, analysts can (1) see *why* tickets landed in manual review (TBC) using the existing classifier reason buckets, (2) browse tickets in a compact preview with progressive disclosure, (3) click a ticket to read its content, and (4) filter the preview to TBC-only rows.

**Users (from [prd.md](../prd.md)):**

| Persona | Primary flow | UX need |
|---------|--------------|---------|
| **CS analyst / team lead** | Categorize (`/`) | Understand TBC mix; inspect sample tickets without scrolling a 25-column table |
| **Taxonomy owner** | Learn / Training preview | Same ticket browsing on changed rows; full TBC reason metrics |
| **Classifier maintainer** | Audit + portal | Bucket counts match `audit_classifier` and TBC trends dashboard |

**Architecture:** Presentation-layer changes plus lightweight metadata capture at classification time. Reuse `classify.tbc_reason()` — do not invent a parallel taxonomy. New `portal_ticket_preview.py` module; vanilla JS; shared CSS patterns from Training changed-tickets table.

**Tech stack:** FastAPI inline HTML builders, `static/ticket_preview.js`, `static/cs_tickets_theme.css`, existing `portal_stats.py` / `allowlist_compare.py`.

**Depends on:** [design.md](../design.md) §5.4 TBC reason buckets, §6 Portal; [CONTEXT.md](../../CONTEXT.md) code-preservation rule; [2026-06-10-portal-ux-improvement.md](./2026-06-10-portal-ux-improvement.md) UX principles; [2026-06-10-training-ux-wizard-and-impact-preview.md](./2026-06-10-training-ux-wizard-and-impact-preview.md) changed-tickets disclosure pattern.

**Related plans:**

- Portal UX Phase 4 backlog item “per-ticket why” — promoted to active scope here (classify flow).
- TBC trends dashboard — same `tbc_reason()` buckets; numbers on classify run should align.

---

## Context

### Pain points (observed)

| Area | Problem | Impact |
|------|---------|--------|
| **Classify results** | Headline TBC count only — no breakdown by reason | Analysts cannot tell if TBC is “no rules” vs “contested” |
| **Classify ticket preview** | All 25 `MASTER_COLUMNS` in a static table, truncated | Unreadable; no drill-down into subject/description |
| **Classify ticket preview** | No TBC filter | Hard to audit manual-review samples |
| **Learn/Training preview** | Metrics table omits `allowlist_filtered` and `other` buckets | Incomplete reason picture |
| **Learn/Training preview** | Changed tickets lack subject/description; not clickable | Cannot read ticket content during preview |
| **Disclosure inconsistency** | Training preview hides detail columns behind a checkbox; classify preview shows everything | Classify page feels noisier than allowlist update preview |

### What already works (do not break)

- TBC headline summary card (`classify_run_summary_html`) on classify results
- `compare_result_html()` aggregate metrics: margin-loss, below-threshold (old → new); zero-candidate row **will be re-scoped** in Phase 2 Task 2.1
- Training changed-tickets table: compact default + `#show-changed-details` checkbox (`training.js` + `.change-col-detail` CSS)
- `tbc_reason()` in `classify.py` — single source of truth for buckets
- `MASTER_COLUMNS` / Excel workbook contract
- Training commit/revert disk semantics
- Bad CSAT filter on classify and preview
- 200-row preview cap on classify results

### TBC reason buckets (normative)

Reuse `classify.tbc_reason(decision)` — same logic as `tools/audit_classifier.py` and `tbc_trends.py`:

| Code bucket | Analyst label (plain language) | Meaning |
|-------------|-------------------------------|---------|
| `zero_candidate` | No rules matched | No rules fired (or no score accumulated) |
| `below_threshold` | Weak signal | Best candidate score &lt; threshold (5.0) |
| `lost_margin` | Contested | Threshold met but runner-up within margin (2.0) |
| `allowlist_filtered` | Rules blocked | Rules fired but every target tuple outside allow-list |
| `other` | Other | Fallback with candidates failing the above checks |
| `not_tbc` | — | Not manual review; hide badge in UI |

Informal terms (“zero rules”, “weak rules”, “contested”) map to the rows above — do not add new bucket names in code.

### Counting contract (normative)

Portal bucket counts must match `tools/audit_classifier.py` on the same export. Use **one** shared helper (add to `classify.py` or `portal_stats.py`; document in notes):

```python
def _is_tbc_decision(decision) -> bool:
    """Same as allowlist_compare._is_tbc and tbc_trends._is_tbc."""
    return decision.fallback_used or "tbc" in decision.tier[3].lower()


def portal_reason_bucket(decision, *, output_row: dict | None = None) -> str:
    """Map a classification decision → display bucket code for portal / audit alignment."""
    if _is_tbc_decision(decision):
        reason = tbc_reason(decision)
        return "other" if reason == "not_tbc" else reason
    # Rare: attach_tiers coercion forced output to TBC after a non-fallback decision
    if output_row is not None and is_manual_review_row(output_row):
        return "other"
    return "not_tbc"
```

**Capture (Task 1.1):** In `attach_tiers_with_meta()`, call `classify_row_with_explanation()` once, apply the same coercion path as `attach_tiers()`, then set `reason = portal_reason_bucket(decision, output_row=out)`.

| Metric | Source | Notes |
|--------|--------|-------|
| **Headline TBC** (`classify_run_summary_html`) | `is_manual_review_row(output row)` | Unchanged; matches Excel tier pivot |
| **Reason buckets** (summary card, per-row badge) | `portal_reason_bucket(decision, output_row=out)` | Sum of the five display buckets = headline TBC when coercion edge cases map to `other` |
| **Audit / trends parity** | `_is_tbc_decision(decision)` + `portal_reason_bucket` | Manual test: `audit_classifier` bucket lines match portal summary on same file |
| **Per-row preview filter** | Stored `tbc_reasons[id]` | Filter TBC rows where stored reason ≠ `not_tbc` |

Do **not** count buckets with `is_manual_review_row(row)` alone while reading raw `tbc_reason(decision)` — that diverges from audit when `fallback_used` is false or coercion applies.

---

## Design decisions

| Topic | Decision | Rationale |
|-------|----------|-----------|
| Reason capture | `attach_tiers_with_meta()` → `(row, warn, reason)` via one `classify_row_with_explanation()` pass + `portal_reason_bucket()` | Avoids double scoring; `attach_tiers()` today calls `classify_row()` which re-runs explanation internally |
| Excel output | **Do not** add `tbc_reason` to `MASTER_COLUMNS` in Phase 1–2 | Preserves workbook contract; portal-only metadata in `_RunRecord` |
| Preview component | New `portal_ticket_preview.py` shared by classify + preview flows | Matches `portal_stats.py` / `portal_training.py` split; keeps `portal_app.py` thin |
| Classify table default | **Compact columns only** (id, subject, tier4) | Parity with Training changed-tickets default |
| Classify detail disclosure | Checkbox **“Show ticket details”** reveals extra table columns | Same pattern as `#show-changed-details` + `.change-col-detail` + `--expanded` class |
| Ticket content | **Click row** → detail pane (subject, description, tags, tier path, TBC reason) | Separate from column toggle; content pane below table |
| TBC filter | Checkbox **“Show manual review (TBC) only”** — client-side on server-capped slice | Cap applies first (`rows[:limit]`); filter second; meta line explains both |
| Preview row cap | **200** rows for classify and changed-tickets (shared default) | Replaces Training’s 50-row changed-ticket cap when adopting `ticket_preview_html()` |
| Preview flows | Extend `changed_rows` payload + complete bucket metrics | Reuse shared preview component on Learn/Training |
| JS | New `ticket_preview.js`; mirror `training.js` toggle logic | No framework; progressive enhancement |
| Copy | Labels in `portal_copy.py` | Plain language per CONTEXT.md / portal UX plan |

### Progressive disclosure layout (classify ticket preview)

```text
┌─ Ticket Preview ─────────────────────────────────────────────┐
│  ☐ Show manual review (TBC) only                             │
│  ☐ Show ticket details                                       │
│                                                              │
│  ┌─ table (compact) ─────────────────────────────────────┐ │
│  │ id │ subject │ category (tier4) │ [detail cols hidden]  │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌─ detail pane (after row click) ─────────────────────────┐ │
│  │ Subject / Description / Tags / TBC reason              │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

**Default state:** detail columns hidden; detail pane shows placeholder (“Select a ticket to view its content”) or is collapsed until first click.

**“Show ticket details” checked:** table gains columns — tier1–tier3, granular, TBC reason badge, tags (truncated), `created_at` (exact set in Task 3.2).

**Reference implementation:** `training_changed_rows_html()` + `training.js` lines 149–159 + `.training-changed-table .change-col-detail` in `cs_tickets_theme.css`.

---

## Functional requirements

| ID | Requirement |
|----|-------------|
| FR-TP-01 | Classify result shows TBC reason **aggregate** breakdown (all five buckets) for manual-review tickets |
| FR-TP-02 | Classify ticket preview defaults to **compact** columns (id, subject, tier4) |
| FR-TP-03 | Classify ticket preview has **“Show ticket details”** checkbox that reveals additional columns (same disclosure pattern as Training changed tickets) |
| FR-TP-04 | Clicking a ticket row populates a **detail pane** with subject, description, tags, full tier path, and TBC reason (when applicable) |
| FR-TP-05 | Classify ticket preview has **“Show manual review (TBC) only”** filter (client-side, within preview cap) |
| FR-TP-06 | `tbc_reason` captured during classify run without changing CLI CSV output |
| FR-TP-07 | Learn/Training preview metrics include `allowlist_filtered` and `other` bucket counts |
| FR-TP-08 | Learn/Training changed-ticket rows include fields needed for detail pane; reuse shared preview component |
| FR-TP-09 | Bucket counts use `portal_reason_bucket()` — consistent with `audit_classifier` and TBC trends |
| FR-TP-10 | Plain-language labels in UI; technical bucket ids available in collapsed technical section or `title` attributes |
| FR-TP-11 | No change to classifier thresholds, allow-list, or Training commit/revert semantics |
| FR-TP-12 | `pytest` extended for new HTML fragments and bucket counting |

---

## Phased delivery

| Phase | Scope | Est. |
|-------|--------|------|
| **1** | Classify run: reason capture, summary card, interactive preview with disclosure + filter | 2–3 d |
| **2** | Preview parity: complete metrics, changed-row content, shared component on Learn/Training | 2 d |
| **3** | Polish: optional Excel column, bucket → filter shortcut, keyboard nav | 1 d (optional) |

Implement **Phase 1 → Phase 2** in order. Phase 3 is backlog unless requested.

---

## Phase 1 — Classify run

### Task 1.1 — Capture `tbc_reason` during classification

**Files:**

- `src/cs_tickets/classify.py` — add `portal_reason_bucket()`, `attach_tiers_with_meta()`
- `src/cs_tickets/pipeline.py` — add `iter_master_rows_with_meta()` (**portal-only**; leave `iter_master_rows()` unchanged for CLI per FR-TP-06)

**Behavior:**

```python
def attach_tiers_with_meta(row, allow) -> tuple[dict, str | None, str]:
    decision = classify_row_with_explanation(row, allow)
    # ... same coercion logic as attach_tiers ...
    reason = portal_reason_bucket(decision, output_row=out)
    return out, warn, reason
```

Keep `attach_tiers()` as a thin wrapper (code preservation per CONTEXT.md). Portal `POST /run` switches from `iter_master_rows` to `iter_master_rows_with_meta`; CLI and CSV output stay on the existing iterator.

### Task 1.2 — Store reasons in run record

**Files:** `src/cs_tickets/portal_app.py`

Extend `_RunRecord`:

```python
@dataclass
class _RunRecord:
    rows: list[dict]
    tbc_reasons: dict[str, str]  # ticket id → bucket code
    # ... existing fields ...
```

Populate during `POST /run` via `iter_master_rows_with_meta()`. Store `tbc_reasons[str(row["id"])] = reason` for every row. Strip `tbc_reason` before `build_run_workbook_bytes()` — workbook unchanged.

### Task 1.3 — TBC reason summary card

**Files:** `src/cs_tickets/portal_stats.py`, `src/cs_tickets/portal_copy.py`

Add:

- `tbc_reason_counts(tbc_reasons: dict[str, str]) -> Counter[str]` — count values where key ≠ `not_tbc` (exclude `not_tbc` from the five-bucket display)
- `tbc_reason_summary_html(tbc_reasons: dict[str, str], *, headline_tbc: int) -> str`

Render below `classify_run_summary_html()` on result page. Use analyst labels from `portal_copy.py` (e.g. `TBC_REASON_LABELS` dict). Acceptance: sum of the five displayed buckets equals `headline_tbc` from `classify_run_counts()` (coercion edge cases land in `other` per counting contract).

### Task 1.4 — Shared ticket preview module

**Files (new):**

- `src/cs_tickets/portal_ticket_preview.py`
- `src/cs_tickets/static/ticket_preview.js`

**API sketch:**

```python
def ticket_preview_html(
    tickets: list[dict],
    *,
    tbc_reasons: dict[str, str] | None = None,
    limit: int = 200,
    table_id: str = "classify-ticket-preview",
    mode: str = "classify",  # "classify" | "changed"
) -> str:
    ...
```

**Preview cap (server-side):** Slice `tickets[:limit]` before rendering and before embedding JSON. Default `limit=200` for classify and changed-tickets (Phase 2 upgrades Training from 50).

**TBC filter (client-side):** `#show-ticket-preview-tbc-only` filters the embedded slice only — not the full export. When checked, show meta, e.g. “Showing 12 of 47 manual review tickets in this preview (first 200 rows of export).” Add `TICKET_PREVIEW_TBC_FILTER_META` to `portal_copy.py`.

Embed ticket data with `json.dumps(..., ensure_ascii=False)` in `<script type="application/json" id="...-data">` — do not hand-build JSON strings.

**Default visible columns:** `id`, `subject`, `Tier4_Type`

**Detail columns (hidden until checkbox):** `Tier1_Segment`, `Tier2_Stream`, `Tier3_Cat`, `Granular_Tech_UI_Type`, TBC reason badge, `tags` (truncated), `created_at`

Use CSS classes `ticket-preview-table`, `preview-col-detail`, `ticket-preview-table--expanded` — parallel to Training naming.

### Task 1.5 — Detail pane on row click

**Files:** `portal_ticket_preview.py`, `ticket_preview.js`, `cs_tickets_theme.css`

- Clickable rows: `cursor: pointer`, `.ticket-preview-row--selected` highlight
- Detail pane `#ticket-preview-detail` below table
- Fields: subject, description, tags (formatted), full tier path, TBC reason label + one-line bucket explanation
- Use a **non-truncating** escape helper for description (do **not** reuse `portal_app._esc`, which caps at 500 chars); mirror `portal_training._esc` or add `portal_ticket_preview._esc_detail`
- Empty state copy: `TICKET_PREVIEW_SELECT_HINT` in `portal_copy.py`

### Task 1.6 — Disclosure and filter controls

**Files:** `portal_ticket_preview.py`, `ticket_preview.js`, `portal_copy.py`

| Control | Element id | Behavior |
|---------|------------|----------|
| Show ticket details | `#show-ticket-preview-details` | Toggles `ticket-preview-table--expanded` |
| TBC only | `#show-ticket-preview-tbc-only` | Filters embedded JSON rows client-side |

Copy constants:

```python
SHOW_TICKET_PREVIEW_DETAILS_LABEL = "Show ticket details"
SHOW_TICKET_PREVIEW_TBC_ONLY_LABEL = "Show manual review (TBC) only"
TICKET_PREVIEW_SELECT_HINT = "Select a ticket above to view its content."
TICKET_PREVIEW_TBC_FILTER_META = "Showing {visible} of {tbc_in_slice} manual review tickets in this preview (first {limit} rows of export)."
```

Mirror `SHOW_CHANGE_DETAILS_LABEL` wording style from `portal_training_copy.py`.

### Task 1.7 — Wire into classify result page

**Files:** `src/cs_tickets/portal_app.py`

Replace inline 25-column preview table with `ticket_preview_html()`. The classify **result** page currently renders static HTML with **no** `extra_scripts` — add explicitly:

```python
return portal_page_html(
    title="Categorization results",
    active="categorize",
    body=body,
    extra_scripts=["/static/ticket_preview.js?v=1"],
)
```

Do not rely on global script loading; `classify.js` is only on the upload form today.

### Task 1.8 — Tests

**Files:** `tests/test_portal_stats.py`, `tests/test_portal.py`, `tests/test_classify.py`

- `portal_reason_bucket` maps `not_tbc` → `other` when `_is_tbc_decision`; coercion-only TBC → `other`
- `attach_tiers_with_meta` returns same tiers as `attach_tiers`
- `tbc_reason_summary_html` counts match fixture decisions / `audit_classifier` buckets
- Result HTML contains preview checkboxes, compact table, embedded JSON, no longer all 25 columns by default
- Detail columns use `preview-col-detail` class
- Classify result page includes `ticket_preview.js` in `extra_scripts`

---

## Phase 2 — Learn / Training preview parity

### Task 2.1 — Complete TBC bucket metrics

**Files:** `src/cs_tickets/allowlist_compare.py`, `AllowlistCompareResult`

**Fix existing counter:** Replace the current `zero_candidate_old/new` increment (`if not old_dec.candidates`) with `_count_tbc_bucket(old_dec, "zero_candidate")` (and same for `new`). The old logic counted all no-candidate rows and conflated `zero_candidate` with `allowlist_filtered`; the metrics table must show **five TBC-scoped buckets** that partition manual-review tickets the same way as `audit_classifier`.

Add counters: `allowlist_filtered_old/new`, `other_old/new` (mirror existing `margin_loss_*` pattern using `_count_tbc_bucket`).

Extend `compare_result_html()` plain-language rows — all five rows are TBC-scoped and labeled “(manual review)”:

| Metric | Old | New | Δ |
|--------|-----|-----|---|
| No rules matched (manual review) | … | … | … |
| Rules blocked (manual review) | … | … | … |
| Weak signal (manual review) | … | … | … |
| Contested (manual review) | … | … | … |
| Other manual review | … | … | … |

Rename the existing “Zero-candidate tickets” row to “No rules matched (manual review)” when updating labels. Update any tests that assert `zero_candidate_old` semantics (e.g. `test_golden_classifier.py`).

### Task 2.2 — Row content for preview drill-down

**Files:** `src/cs_tickets/allowlist_compare.py`

When building `changed_rows`, include base fields needed by detail pane:

- `subject`, `description`, `tags`
- `new_tier4` / `old_tier4` (already present)
- `new_tbc_reason` / `old_tbc_reason` (already in enriched rows)

Avoid bloating compare for unchanged rows — changed rows only.

### Task 2.3 — Reuse preview component on Learn/Training

**Files:** `src/cs_tickets/portal_training.py`, `src/cs_tickets/portal_learn.py`, `static/training.js`, `static/ticket_preview.js`

Replace `training_changed_rows_html()` with `ticket_preview_html(..., mode="changed", limit=200)`.

**`mode="changed"` layout:**

| Area | Compact columns (default) | Detail columns (checkbox) |
|------|---------------------------|---------------------------|
| Table | id, old tier4, new tier4 | outcome, mechanism, old TBC reason, new TBC reason |

**Detail pane on row click (`mode="changed"`):**

| Field | Source |
|-------|--------|
| Subject, description, tags | Flattened row (`subject`, `description`, `tags`) — same for old/new |
| Category change | `old_tier4` → `new_tier4`; full tier path when `old_tuple` / `new_tuple` present |
| TBC reasons | Show **both** when applicable: `old_tbc_reason` (if `old_tbc`) and `new_tbc_reason` (if `new_tbc`), with analyst labels via `TBC_REASON_LABELS` |
| Outcome | `outcome_type`, `gap_fix_mechanism` when present |

**JS migration (Phase 2, not Phase 3):** Training/Learn preview pages load `ticket_preview.js` (with `#show-ticket-preview-details`) and **remove** the `#show-changed-details` toggle block from `training.js`. Do not maintain dual checkbox ids or dual-binding — one shared disclosure control.

Ensure Learn preview changed-tickets collapsible section benefits from click-to-view content.

### Task 2.4 — Tests

**Files:** `tests/test_portal.py`, `tests/test_allowlist_session.py` (if compare counters asserted)

- Metrics HTML includes all five TBC-scoped bucket rows
- `zero_candidate_old` counts only TBC `zero_candidate` bucket (not all no-candidate rows)
- Changed-row payload includes `subject` / `description`
- Shared preview renders on training preview page with `mode="changed"`

---

## Phase 3 — Optional polish

| Item | Files | Notes |
|------|-------|-------|
| TBC reason column in Excel | `schema.py`, `portal_workbook.py` | Product decision; add only if analysts need offline audit |
| Click bucket in summary → enable TBC filter + reason sub-filter | `ticket_preview.js` | Deep-link within page via `data-tbc-reason` on rows |
| Keyboard navigation (↑/↓ between rows) | `ticket_preview.js` | Accessibility enhancement |

---

## Implementation order

```text
Phase 1
  1.1 portal_reason_bucket + attach_tiers_with_meta + iter_master_rows_with_meta (portal-only)
  1.2 _RunRecord.tbc_reasons
  1.3 tbc_reason_summary_html + copy labels
  1.4 portal_ticket_preview.py (table + checkboxes + JSON embed + cap meta)
  1.5 Detail pane HTML + non-truncating esc helper
  1.6 ticket_preview.js (toggle, filter, row click) + CSS
  1.7 portal_app.py integration (extra_scripts on result page)
  1.8 tests

Phase 2
  2.1 allowlist_compare bucket counters (fix zero_candidate scope) + compare_result_html
  2.2 changed_rows content fields
  2.3 portal_training.py + portal_learn.py + ticket_preview.js mode=changed; remove training.js toggle
  2.4 tests
```

---

## Acceptance criteria

### Phase 1 (Classify)

- [ ] Result page shows TBC reason breakdown; sum of five buckets equals headline TBC count (`classify_run_counts().tbc`)
- [ ] Bucket counts match `audit_classifier` on the same export (counting contract)
- [ ] Ticket preview shows **id, subject, tier4** by default — not all 25 columns
- [ ] **“Show ticket details”** checkbox reveals additional columns (Training-style toggle)
- [ ] Clicking a row shows full subject, description, and tags in detail pane (not truncated to 500 chars)
- [ ] **“Show manual review (TBC) only”** filters within the capped preview slice; meta explains cap + filter
- [ ] Classify result page loads `ticket_preview.js` via `extra_scripts`
- [ ] Excel download unchanged (no new columns unless Phase 3 opted in)
- [ ] `pytest` passes

### Phase 2 (Preview)

- [ ] Preview metrics show all five TBC-scoped reason buckets (old → new); `zero_candidate_*` uses `_count_tbc_bucket`
- [ ] Changed tickets use shared preview at **200-row** cap (not 50)
- [ ] Changed tickets in Learn/Training preview support click-to-view content per `mode="changed"` detail pane spec
- [ ] Disclosure uses `#show-ticket-preview-details` only (no `#show-changed-details` on preview pages)

### Non-regression

- [ ] Full `pytest` suite passes
- [ ] Headline TBC definition unchanged (`is_manual_review_row` on output rows)
- [ ] Training commit/revert behaviour unchanged
- [ ] Bucket counts align with `audit_classifier` on same export (`portal_reason_bucket`)

---

## Test plan

### Automated

```bash
pytest tests/test_portal.py tests/test_portal_stats.py tests/test_classify.py tests/test_allowlist_session.py -q
```

### Manual checklist

1. **Classify:** Upload NDJSON → verify TBC reason summary → confirm compact preview → check “Show ticket details” → click a TBC row → read description → enable TBC-only filter.
2. **Disclosure parity:** Compare classify preview toggle with Training “Show Ticket Change Details” — same interaction model.
3. **Preview:** Run Learn/Training preview → verify five bucket rows in metrics → click changed ticket → view content.
4. **Consistency:** Run `python -m tools.audit_classifier` on same file; bucket counts match portal summary.

Append scenarios to [`testcase.md`](../../testcase.md) as “Ticket preview & TBC reasons”.

---

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| TBC summary disagrees with Excel tier pivot | Headline TBC stays `is_manual_review_row()` on output rows; buckets use `portal_reason_bucket()` — coercion edge cases map to `other` |
| 200-row cap + TBC filter shows few rows | Cap first, filter second; meta: “Showing N of M manual review tickets in this preview (first 200 rows of export)” |
| Duplicate JS toggle logic | Phase 2 removes `#show-changed-details` from `training.js`; single `ticket_preview.js` disclosure helper |
| `attach_tiers_with_meta` drift from `attach_tiers` | Single coercion code path; test parity |
| Large description XSS / truncation | Non-truncating `_esc` in detail pane; `json.dumps` for embedded row JSON |
| Preview changed-rows memory | Only attach content fields for changed rows (already bounded) |
| Portal run classifies export twice | Accept for Phase 1 (`iter_master_rows_with_meta` + `try_append_portal_snapshot`); note in notes file if reusing captured reasons for trends later |

---

## Out of scope

- Per-rule evidence drill-down (`ClassificationDecision.evidence`)
- Run persistence across pod restarts
- Classifier threshold or rule changes
- React / Jinja template rewrite
- Showing all TBC tickets on 39k-row exports without cap
- Authentication / SSO

---

## References

- [prd.md](../prd.md) — TBC as success metric
- [design.md](../design.md) §5.4 TBC reason buckets, §6.3 Stats
- [CONTEXT.md](../../CONTEXT.md) — code preservation, glossary
- [2026-06-10-portal-ux-improvement.md](./2026-06-10-portal-ux-improvement.md) — progressive disclosure, plain language
- [2026-06-10-training-ux-wizard-and-impact-preview.md](./2026-06-10-training-ux-wizard-and-impact-preview.md) — Task 6 changed-rows disclosure
- `src/cs_tickets/portal_training.py` — `training_changed_rows_html()`
- `src/cs_tickets/static/training.js` — `#show-changed-details` toggle
- `tools/audit_classifier.py` — bucket reporting reference
