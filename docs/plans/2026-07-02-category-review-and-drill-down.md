# Category Review & Drill-Down — Implementation Plan

> **Status:** Phases **1–2 complete** (2026-07-02). Phase 3 backlog open. See [2026-07-02-category-review-and-drill-down-notes.md](./2026-07-02-category-review-and-drill-down-notes.md).
>
> **For implementer:** When you execute this plan, document steps and design decisions in `docs/plans/2026-07-02-category-review-and-drill-down-notes.md`. This plan describes *what* to build; that notes file describes *what you did*.

**Goal:** After a **Categorize tickets** run, analysts can **browse tickets in a chosen category**, **filter by ticket details** (subject, tags, dates, etc.), and **inspect individual tickets** with enough context to spot-check whether a category bucket looks correct — without downloading Excel or re-uploading the export.

**Users (from [prd.md](../prd.md)):**

| Persona | Primary flow | UX need |
|---------|--------------|---------|
| **CS analyst / team lead** | Categorize (`/`) → results | Audit a specific category bucket (e.g. “Rate or Renewal Inquiry”); sample tickets for quality |
| **Classifier maintainer** | Categorize + audit | Find miscategorized-looking tickets in a category before changing rules |
| **Taxonomy owner** | Learn / Training preview (secondary) | Same drill-down on changed rows when verifying allowlist impact |

**Architecture:** Extend the existing ticket preview component (`portal_ticket_preview.py`, `ticket_preview.js`) with **category-scoped filtering** and richer **detail inspection**. Wire the tier breakdown table into the preview as a navigation entry point. Optional lazy **classification explanation** on row select (re-run `classify_row_with_explanation` server-side) — no new persistence layer in Phase 1.

**Tech stack:** FastAPI inline HTML builders, vanilla JS, shared CSS from `cs_tickets_theme.css`, existing `_RunRecord` in-memory run store.

**Depends on:** [design.md](../design.md) §6 Portal; [2026-06-24-ticket-preview-tbc-reasons.md](./2026-06-24-ticket-preview-tbc-reasons.md) (ticket preview, TBC filter, detail pane — **must be complete or in place before this plan**); [2026-06-10-portal-ux-improvement.md](./2026-06-10-portal-ux-improvement.md) progressive-disclosure principles.

**Out of scope for this plan** (separate plans):

- LLM / Gemini-assisted re-categorization or batch TBC review
- Rules / guidance context CRUD and injection into prompts — **client “type rules like an LLM” ask; see [Amendments §2026-07-03](#amendments-2026-07-03)**
- Feedback loop for retiring outdated rules
- Cross-run persistence, saved filter presets, or authentication
- Storing or diffing against the client’s Gemini master prompt at runtime

---

## Amendments (2026-07-03)

Post-implementation re-review after client context: **explicit rule authoring** ([agent transcript](ff71cee6-d071-4134-9936-7d853200e16c)) and **Gemini master prompt** as business spec (not production classifier).

### What changed in the plan

| Area | Original plan | Amended |
|------|---------------|---------|
| **Implementation status** | All phases pending | **Phases 1–2 done**; Phase 3 optional backlog |
| **Category filter data scope** | Client-side on **200-row preview slice** only; meta explains cap | Category selected → **`category_rows`** embeds **all tickets in that tier4** from full export (same pattern as `tbc_rows`); default “All categories” still capped at 200 |
| **Category filter meta copy** | Always shows in-slice vs in-run counts | When showing full export: `Showing {visible} of {matched_total} in "{category}" (full export).` |
| **Open Q4 (preview cap)** | Keep 200; Excel for exhaustive category audit | **Resolved:** category drill-down no longer requires Excel for full-bucket review; Excel still needed for cross-run work and columns outside preview |
| **Open Q2 (`requester_email`)** | Defer to Phase 1 | **Still deferred in this plan**; **elevated priority** for a follow-on *rule authoring* plan (client wants sender-based rules) |
| **Open Q3 (explain rules frozen?)** | Current live rules | Unchanged; add UX note: explain on an old run reflects **current** `runs/live/` rules, not rules at classify time |
| **Phase 3 priority** | Flat optional list | **Reordered** by maintainer value (random sample first) |
| **Acceptance criteria** | Unchecked | Phases 1–2 marked **complete** in checklist below |
| **Follow-on work** | Not specified | Audit loop continues in sibling plans: Gemini spec gap rules + explicit rule authoring UI |

### What did not change

- **No LLM in classification hot path** — still out of scope; aligns with [prd.md](../prd.md) and Phase 2 PRD NG-01.
- **Explain pane shows rule-engine evidence**, not Gemini reasoning.
- **Re-review ≠ re-categorize** — drill-down is spot-check only.

### Sibling plans (not yet drafted)

| Plan | Purpose |
|------|---------|
| `2026-07-03-explicit-rule-authoring.md` | Conversational input → LLM compile → `RuleSpec` → Confirm → `runs/live/` | **Drafted** |
| `2026-07-03-gemini-spec-gap-checklist.md` | Map client business spec → `RuleSpec` / computed-rule fixes | Not yet drafted |

---

**Related backlog items:**

- [2026-06-24-ticket-preview-tbc-reasons.md](./2026-06-24-ticket-preview-tbc-reasons.md) Phase 3 — “Click bucket in summary → enable TBC filter” — **promoted and generalized** here to any category path, not only TBC reason buckets. **Done** via clickable tier breakdown rows.

---

## Context

### Pain points (client workflow)

| Area | Problem | Impact |
|------|---------|--------|
| **Category audit** | Tier breakdown shows counts only; no path from a count → the tickets behind it | ~~Analysts download Excel to inspect a category~~ **Addressed** — drill-down + full `category_rows` |
| **TBC-only filter** | Preview can filter manual review, but not “show me everything in category X” | ~~Cannot spot-check non-TBC buckets~~ **Addressed** |
| **Detail search** | No way to narrow by subject keyword, tag, or date within a category | Hard to investigate recurring senders/patterns when requester email is not in `BASE_COLUMNS` |
| **“Why this category?”** | Detail pane shows tier path + TBC reason; non-TBC tickets lack rule evidence | ~~Offline audit tooling~~ **Addressed** — lazy explain endpoint |
| **Re-review after rule changes** | No in-portal way to re-check a sample without a full re-upload | Maintainer falls back to CLI / `audit_classifier` for spot checks |

### What already works (do not break)

- `tier_stats_table_html()` pivot on classify results page
- `ticket_preview_html()` compact table + “Show ticket details” + “TBC only” + row-click detail pane
- `_RunRecord.rows` + `_RunRecord.tbc_reasons` for the full classified export in memory
- `classify_row_with_explanation()` — deterministic re-classification with evidence and candidate scores
- Excel download and `MASTER_COLUMNS` workbook contract
- 200-row preview cap for **default** “All categories” view; category/TBC filters use full-export row sets (`category_rows`, `tbc_rows`)

### Terminology

| Term | Meaning in this plan |
|------|----------------------|
| **Category** | Assigned tier path; filter UI defaults to **Tier4_Type** with optional full 5-tuple match |
| **Re-review** | Human spot-check of tickets already in a category (browse + inspect). **Not** automatic recategorization. |
| **Drill-down** | Navigate from tier breakdown → filtered preview → ticket detail pane |
| **Explanation** | Classifier output: rules fired, scores, margin — shown on demand, not stored on every row at run time |

---

## Design decisions

| Topic | Decision | Rationale |
|-------|----------|-----------|
| Filter scope | **Client-side** on embedded JSON. **Default view:** first 200 rows. **Category filter:** full export via `category_rows` (tier4 → all rows). **TBC filter:** full export via `tbc_rows`. Meta line distinguishes cap vs full export. | Matches TBC-only pattern; exhaustive category audit without Excel or pagination API |
| Category row payload | Embed `category_rows: dict[tier4, rows]` built in one pass over full `tickets` in `ticket_preview_html()` | Same embedding strategy as `tbc_rows`; avoids per-category API |
| Category match | Default: `Tier4_Type` exact match; advanced: full 5-tuple (`Tier1`…`Granular`) | Tier4 is how analysts speak; full path disambiguates duplicate tier4 labels across segments |
| Tier breakdown link | Click count row → set category filter + scroll to preview | Obvious entry point; no new page |
| Detail filters | Subject contains (case-insensitive), tag contains, optional `created_at` date range | Available in `BASE_COLUMNS`; no requester-email filter until flatten adds it |
| TBC + category | Filters are **AND** composable: category + TBC-only + detail filters | Supports “TBC in Billing” and “non-TBC in Renewal” |
| Classification “why” | **Lazy** `GET /run/{run_id}/explain/{ticket_id}` re-runs classifier on the stored row | Avoids bloating `_RunRecord`; uses **current** `runs/live/` rules (not frozen at run time — document in UI) |
| Explanation storage | Do **not** add evidence columns to Excel in Phase 1 | Preserves workbook contract |
| Training preview | Reuse same filter controls on `mode="changed"` where category = `new_tier4` | Secondary surface; Phase 2 |
| Copy | Labels in `portal_copy.py` | Consistent with portal UX plan |

### Progressive disclosure layout (classify results)

```text
┌─ Tier breakdown (existing) ────────────────────────────────────┐
│  B2C → … → Rate or Renewal Inquiry          [42]  ← clickable │
└───────────────────────────────────────────────────────────────┘

┌─ Ticket Preview ─────────────────────────────────────────────┐
│  Category: [All ▼]  Tier4 quick-pick from run counts          │
│  Subject contains: [________]  Tag contains: [________]       │
│  ☐ Show manual review (TBC) only   ☐ Show ticket details      │
│  Meta: Showing 38 of 42 in “Rate or Renewal…” (full export)     │
│  ┌ id │ subject │ tier4 ┐                                      │
│  └ … clickable rows …   ┘                                      │
│  ┌ Detail pane ─────────────────────────────────────────────┐  │
│  │ subject, description, tags, tier path, TBC reason        │  │
│  │ [Show classification details] → rules, scores (lazy)     │  │
│  └──────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────┘
```

---

## Phase 1 — Category filter + tier-breakdown drill-down ✅

**Status:** Complete (2026-07-02). Post-ship: `category_rows` full-export embedding added same day.

### Task 1.1 — Category index for a run

**Files:** `src/cs_tickets/portal_stats.py`

Add helper to derive distinct categories from classified rows:

```python
def category_index(rows: list[dict]) -> list[dict]:
    """Distinct tier paths with counts, sorted by count desc then tier4."""
    # Each entry: tier4, full tuple, count
```

Use for populating `<select>` options and validating filter keys client-side.

### Task 1.2 — Extend ticket preview payload

**Files:** `src/cs_tickets/portal_ticket_preview.py`

- Add to embedded JSON per row: `tier4`, `tier_tuple` (5 strings), `created_at` (already present), parsed `tags` list
- Add top-level `categories: category_index(rows)` when `mode="classify"`
- Add top-level `category_rows: dict[str, list]` — all JSON rows per tier4 from **full** export (not only preview slice)
- Add `filter_labels` / empty-state copy keys from `portal_copy.py`

New copy constants (examples):

```python
CATEGORY_FILTER_LABEL = "Category"
CATEGORY_FILTER_ALL = "All categories"
SUBJECT_FILTER_LABEL = "Subject contains"
TAG_FILTER_LABEL = "Tag contains"
TICKET_PREVIEW_CATEGORY_FILTER_META = (
    'Showing {visible} of {matched_in_slice} in "{category}" '
    "(first {limit} rows of export; {matched_total} total in run)."
)
TICKET_PREVIEW_CATEGORY_FILTER_META_FULL = (
    'Showing {visible} of {matched_total} in "{category}" (full export).'
)
TICKET_PREVIEW_NO_MATCH = "No tickets match the current filters in this preview slice."
```

### Task 1.3 — Category + detail filter controls (UI)

**Files:** `portal_ticket_preview.py`, `ticket_preview.js`, `cs_tickets_theme.css`

| Control | Behavior |
|---------|----------|
| Category `<select>` | Options from `categories`; “All” clears tier filter |
| Subject input | Debounced (~200ms) case-insensitive substring on `subject` |
| Tag input | Case-insensitive match against parsed tag list |
| TBC only (existing) | AND with category + text filters |
| Show details (existing) | Unchanged |

Filter order: `getBaseRows()` → category filter uses `category_rows[tier4]` when set, else TBC uses `tbc_rows`, else `rows` slice → apply subject → tag → re-render tbody. Preserve row click / detail pane behavior on visible rows.

### Task 1.4 — Clickable tier breakdown rows

**Files:** `portal_stats.py` (`tier_stats_table_html`), `portal_app.py`, `ticket_preview.js`

- Add `data-tier4`, `data-tier1`…`data-granular` on breakdown `<tr>` (blank cells inherit from pivot row context — use full tuple from `tier_stats_display_rows` source data, not display blanks)
- Add class `tier-stats-row--selectable` + `cursor: pointer`
- On click: set preview category `<select>`, scroll to `#ticket-preview` anchor, apply filter
- Highlight selected breakdown row (`.tier-stats-row--active`)

**Files:** `portal_app.py` — ensure preview block has `id="ticket-preview"` wrapper.

### Task 1.5 — Wire classify results page

**Files:** `portal_app.py`

Pass full `rows` into `category_index` for the select options (not only the 200-row slice). Preview embed still uses `tickets[:limit]` for JSON `rows`, but `categories` and `matched_total` counts come from the full run.

Meta line must distinguish:

- tickets in category **in full run** (`matched_total`)
- tickets in category **in embedded slice** (`matched_in_slice`)
- tickets **visible after all filters** (`visible`)

### Task 1.6 — Tests

**Files:** `tests/test_portal_stats.py`, `tests/test_portal.py`

- `category_index` counts match manual grouping on fixture rows
- Result HTML includes category `<select>`, subject/tag inputs
- Tier breakdown rows have `data-tier4` (and full tuple attrs)
- `tests/test_portal_ticket_preview.py` — `category_rows` includes tickets beyond 200-row slice
- Filter meta placeholders render without error

---

## Phase 2 — Classification explanation on demand (“why this category?”) ✅

**Status:** Complete (2026-07-02).

### Task 2.1 — Explain endpoint

**Files:** `portal_app.py`, new `portal_explain.py` (thin helper)

```python
@router.get("/run/{run_id}/explain/{ticket_id}")
def explain_ticket(run_id: str, ticket_id: str) -> HTMLResponse | JSONResponse:
    ...
```

- Load row from `_RUNS[run_id].rows` by `id`
- Call `classify_row_with_explanation(row, allow)` with current allow-list + merged rule specs (same as pipeline)
- Return JSON: `tier`, `fallback_used`, `candidates` (top 3), `evidence` (rule ids + matched snippets), `tbc_reason` when applicable

Support `?format=json` for JS fetch; default HTML fragment for no-JS fallback (optional).

### Task 2.2 — Detail pane integration

**Files:** `ticket_preview.js`, `portal_ticket_preview.py`, `portal_copy.py`

- Add button **“Show classification details”** in detail pane (non-TBC and TBC)
- On click: `fetch(/run/{runId}/explain/{ticketId}?format=json)` — `runId` from `data-run-id` on preview root
- Render: winning tier path, score, margin note, bullet list of fired rules, collapsed “Other candidates” if contested
- Loading / error states; do not block subject/description display

Pass `run_id` into preview root: `data-run-id="{run_id}"` on classify results page.

### Task 2.3 — Tests

**Files:** `tests/test_portal.py`, `tests/test_classify.py` (if explanation shape asserted)

- Explain endpoint 404 for unknown run/ticket
- JSON contains `evidence` and `tier` matching direct `classify_row_with_explanation` on same row
- Detail pane HTML includes explain button and `data-run-id`

---

## Phase 3 — Optional polish (backlog)

**Re-prioritized 2026-07-03** after client rule-authoring / Gemini spec context. Highest value for maintainers auditing buckets before rule changes.

| Priority | Item | Files | Notes |
|----------|------|-------|-------|
| **P0** | Random sample button | `ticket_preview.js` | “Show random 10” from current filtered set — spot-check large buckets vs business spec |
| **P1** | Full 5-tuple category match toggle | `ticket_preview.js` | When tier4 collisions exist across B2B/B2C (e.g. Posties, ESP paths) |
| **P2** | Training / Learn preview | `portal_training.py` | Category filter on `new_tier4` in `mode="changed"` |
| **P3** | `created_at` date range filter | `ticket_preview.js` | ISO date compare on row field |
| **P3** | Deep link `?category=…` on result URL | `portal_app.py` | Shareable audit link within same run session |
| **P4** | Keyboard: Enter on breakdown row | `ticket_preview.js` | Accessibility — **partially done** (Enter/Space on tier rows) |

---

## Implementation order

```text
Phase 1 ✅
  1.1 category_index helper
  1.2 Extended JSON payload + copy (+ category_rows post-ship)
  1.3 Filter controls + JS filter pipeline
  1.4 Clickable tier breakdown + scroll-into-view
  1.5 portal_app wiring + meta counts
  1.6 tests

Phase 2 ✅
  2.1 GET /run/{run_id}/explain/{ticket_id}
  2.2 Detail pane fetch + render
  2.3 tests

Phase 3 (optional, re-prioritized)
  P0 random sample → P1 full 5-tuple → P2 training preview → P3 date/deep link
```

---

## Acceptance criteria

### Phase 1 ✅

- [x] Classify results page: category dropdown lists all tier4 (or paths) present in the run with counts
- [x] Selecting a category filters the ticket preview table; composes with existing TBC-only filter
- [x] Subject and tag filters further narrow results; empty state copy when no matches
- [x] Clicking a tier breakdown row selects that category and scrolls to the preview
- [x] Meta line states cap + in-slice vs in-run counts clearly (full-export meta when category selected)
- [x] Excel download unchanged
- [x] `pytest` passes

### Phase 2 ✅

- [x] “Show classification details” loads rule evidence and top candidates for the selected ticket
- [x] Explanation matches `classify_row_with_explanation` for the same row (no stale cached decision)
- [x] Works for non-TBC and TBC tickets

### Non-regression ✅

- [x] Existing TBC reason summary, detail pane, and “Show ticket details” behavior unchanged
- [x] Training commit/revert and Learn flows unchanged (until Phase 3 opt-in)
- [x] Headline tier breakdown totals still match Excel tier sheet

---

## Test plan

### Automated

- `category_index` unit tests on synthetic rows (duplicate tier4 across tier1, empty granular)
- Portal integration: result HTML contains filter controls + `data-run-id` (Phase 2)
- Explain endpoint JSON parity with `classify_row_with_explanation`
- JS-free: category `<select>` options rendered server-side (filtering requires JS — document in UI copy)

### Manual

1. Upload export with diverse tier4 buckets (include one TBC and one high-volume non-TBC category).
2. Click a tier breakdown row → preview filters to that category; count meta is plausible.
3. Add subject substring → table narrows; clear filters restores slice.
4. Enable TBC only + category → intersection only.
5. Click a ticket → detail pane; Phase 2: classification details show expected rule ids for a known fixture ticket.
6. Download Excel → unchanged columns.

---

## Open questions (resolved)

| # | Question | Resolution |
|---|----------|------------|
| 1 | Filter by tier4 only vs always full 5-tuple? | **Tier4 default**; full path disambiguation in dropdown labels; **5-tuple toggle → Phase 3 P1** |
| 2 | Include `requester_email` in flatten for sender-based drill-down? | **Deferred here**; elevated for follow-on **rule authoring** plan (not drill-down) |
| 3 | Should explain endpoint use rules frozen at run time vs current `classifier_rules.json`? | **Current live rules**; UI should note re-explain on old runs ≠ original classify-time decision |
| 4 | Raise preview cap above 200 for category audit? | **Resolved via `category_rows`:** full bucket in-portal when category selected; default “All” stays at 200 |

---

## References

- [prd.md](../prd.md) — users, tier taxonomy
- [design.md](../design.md) — portal, classification, `ClassificationDecision`
- [2026-06-24-ticket-preview-tbc-reasons.md](./2026-06-24-ticket-preview-tbc-reasons.md) — preview component baseline
- `src/cs_tickets/portal_ticket_preview.py`, `static/ticket_preview.js` — extension points
- `tools/audit_classifier.py` — offline precedent for per-ticket explanation
