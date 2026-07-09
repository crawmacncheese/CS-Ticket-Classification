# Category Audit Workflow — Implementation Plan

> **Status:** Phase 0–3 complete (2026-07-07). Phases 4–5 not started. See [2026-07-07-category-audit-workflow-notes.md](./2026-07-07-category-audit-workflow-notes.md).  
> **For implementer:** When you execute this plan, document steps and design decisions in [2026-07-07-category-audit-workflow-notes.md](./2026-07-07-category-audit-workflow-notes.md). This plan describes *what* to build; that notes file describes *what you did*.
>
> **Source:** [2026-07-07-christine-category-audit-workflow.md](./2026-07-07-christine-category-audit-workflow.md) (Christine session excerpt + gap analysis).

**Goal:** After a **Categorize tickets** run, analysts can **audit already-classified category buckets** the way Christine does in Gemini: pick B2C categories, list **all tickets with full content**, run **validation sweeps** (Rosetta, ESP, Posties…), **propose rules** from matches, **Confirm** (lead), **reclassify**, and see updated bucket counts — without Excel or a separate chat session.

**Users (Model B — [2026-07-06-christine-workflow-decisions.md](./2026-07-06-christine-workflow-decisions.md)):**

| Persona | Primary flow | UX need |
|---------|--------------|---------|
| **CS analyst / team lead** | `/run` → category audit | Read every ticket in "Cancellation"; flag miscategorizations; draft rules from sweeps |
| **Classifier maintainer** | Audit + Confirm | Review sweep-suggested rules; reclassify run; verify bucket counts drop |
| **Taxonomy owner** | Audit edge cases | Ensure sweep targets resolve to allow-listed 5-tuples |

**Architecture:** Extend run results with a **Category Audit** panel (new route or anchored section). Reuse `category_rows` embedding, `TbcQueueFilter` shape, `tbc_filter_nl` parsing, `build_filter_batch_rule_prefill`, and `POST /run/{id}/reclassify`. Add **`category_audit_sweeps.py`** for named validation checks. **No LLM on `/run`**; compile-only LLM unchanged for rule authoring.

**Tech stack:** FastAPI inline HTML, vanilla JS (`category_audit.js`), shared CSS, `_RunRecord` in-memory store.

**Depends on:**

- [2026-07-02-category-review-and-drill-down.md](./2026-07-02-category-review-and-drill-down.md) — Phases 1–2 **done** (`category_rows`, explain, tier breakdown drill-down)
- [2026-07-06-christine-workflow-decisions.md](./2026-07-06-christine-workflow-decisions.md) — Model B, reclassify after Confirm
- [2026-07-06-tbc-queue-review-focus-notes.md](./2026-07-06-tbc-queue-review-focus-notes.md) — NL focus, batch rule draft (reuse patterns)
- [2026-07-03-explicit-rule-authoring.md](./2026-07-03-explicit-rule-authoring.md) — compile + Confirm gate

**Out of scope for this plan:**

- LLM batch categorization or narrative "insights" paragraphs (Phase 5 optional template only; no LLM v1)
- Cross-run persistence / saved audit sessions
- Phase 2 **run-scoped single-ticket relabel** (separate track in workflow decisions — audit corrections go through **rule + reclassify** in Phase 1–4 here)
- Authentication beyond existing `PORTAL_ALLOW_CONFIRM`
- Editing `classify.py` computed logic via UI (classifier fixes in Phase 0 are code changes, not portal UI)

---

## Context

### Two review loops

| Loop | Where today | This plan |
|------|-------------|-----------|
| **TBC queue** | `/run/{id}/tbc_queue` | Unchanged; share filter NL parser |
| **Category audit** | Partial — drill-down + explain only | **New** bulk list, sweeps, slice impact preview |

### Pain points (Christine session)

| Area | Problem | Impact |
|------|---------|--------|
| **Bulk read** | Must click row-by-row to read full thread | Cannot mirror "list all 8 Access Loop tickets with content" |
| **Validation sweeps** | No "scan Cancellation for Rosetta" button | 17 miscategorized tickets found only via chat re-scan |
| **Slice impact** | Batch rule draft exists for TBC focus, not classified buckets | Analyst cannot see "17 of 33 Cancellation match Rosetta" before Confirm |
| **Classifier gaps** | Posties, refund precedence, account deletion, invoice | Same tickets recur every batch until rules fixed |
| **Weekly report** | No export of audited slice | Falls back to Excel for stakeholder summary |

### What already works (reuse, do not break)

| Capability | Location |
|------------|----------|
| Full-export `category_rows` per tier4 | `portal_ticket_preview.py` |
| Tier breakdown → category filter | `ticket_preview.js` |
| Explain + rule evidence | `portal_explain.py` |
| NL review focus parse | `tbc_filter_nl.py` |
| Batch rule prefill for filter | `build_filter_batch_rule_prefill()` |
| Reclassify run | `POST /run/{id}/reclassify` |
| Rosetta / ESP partial rules | `classify.py`, `classifier_rules.json` |

### Terminology

| Term | Meaning |
|------|---------|
| **Category slice** | Tickets in the current run matching segment + category filter (assigned tier path) |
| **Validation sweep** | Named deterministic check (e.g. Rosetta footer) run against the slice |
| **Sweep match** | Ticket in slice whose blob matches sweep condition |
| **Suggested target** | Allow-listed 5-tuple the sweep says the ticket should move to |
| **Slice impact** | Count of sweep matches **within the active category slice** (not whole run) |

---

## Design decisions

| Topic | Decision | Rationale |
|-------|----------|-----------|
| Entry point | **"Audit category"** CTA on run results + tier breakdown row action | Obvious next step after drill-down; does not replace preview |
| Route | `GET /run/{run_id}/category_audit` with query params `tier1`, `categories`, `tier4` | Dedicated panel; share filter state with preview via query string |
| Slice filter model | **`CategoryAuditFilter`** — same fields as `TbcQueueFilter` minus `tbc_reason`; default **excludes TBC** (`fallback_used` false) unless checkbox | Audit targets confident classifications |
| Bulk list | Server renders first chunk (10); client "Show more" or expand-all; **full description** in expandable `<details>` per row | Matches Christine's numbered list; avoids 500-row DOM blow-up |
| Sweeps | **Built-in catalog** in `category_audit_sweeps.py`; extensible list, not LLM-generated | Deterministic, testable, matches Christine's named scans |
| Sweep output | Per sweep: `match_count`, `ticket_ids[]`, `suggested_tier`, `rule_prefill` text | Drives "Draft rule" CTA |
| Rule path | Sweep → prefill → compile → preview on **whole run** → Confirm → reclassify → return to audit with updated counts | Same as TBC batch rule flow |
| NL focus on audit page | Reuse `parse_review_focus_nl`; parse targets **category labels** on classified rows | "review B2C 1. access loop 2. cancellation" |
| Classifier fixes | **Phase 0** ships before or in parallel with UI | Sweeps are useless if engine disagrees after reclassify |
| CSV export | Phase 5 — current slice columns + full description | Weekly report handoff |
| Duplicate detection | Phase 5 — same `requester_email` + normalized `subject` within slice | Webhook retry pattern (#169855 + #169856) |

### Progressive disclosure layout (target)

```text
┌─ Run results ──────────────────────────────────────────────────┐
│  Tier breakdown …  [Audit this category] on row click/menu      │
└────────────────────────────────────────────────────────────────┘

┌─ Category Audit — Cancellation (B2C) ──────────────────────────┐
│  NL focus: [review B2C cancellation____________] [Apply]        │
│  16 tickets in slice · 33 in run before last reclassify         │
│  [Export CSV]  [Re-classify run]                                │
├─ Validation sweeps ──────────────────────────────────────────────┤
│  ☐ Rosetta System Email        0 matches  [Draft rule]          │
│  ☐ ESP / Print                 2 matches  [Show IDs] [Draft rule] │
│  ☐ Posties / Young Post        0 matches  [Draft rule]          │
│  ☐ Account deletion            1 match    [Show IDs] [Draft rule]│
│  ☐ Invoice request             0 matches  [Draft rule]          │
│  ☐ Refund + cancel combo       1 match    [Show IDs] [Draft rule] │
├─ Tickets in slice (chunk 1 of 2) ──────────────────────────────┤
│  #169894  Auto-renewal disabled for SCMP.com                    │
│           ▼ Full content (description + comments if present)    │
│  #169942  AlipayHK Subscriber Auto Debit Cancellation …         │
│  …                                                              │
│  [Skip chunk — looks fine]  [Next 10]                           │
└────────────────────────────────────────────────────────────────┘
```

---

## Phase 0 — Classifier rule alignment (pre-requisite)

**Goal:** Reclassify after audit sweeps produces the same outcomes Christine applied. Ship with tests; can merge before UI.

### Task 0.1 — Refund > Cancellation precedence

**Files:** `src/cs_tickets/classify.py`, `tests/test_classify.py`

When `has_refund` and cancel language both present in B2C context:

- **Current:** `computed:refund_cancel.b2c` adds Cancellation at weight 22
- **Target:** Prefer `Complaint > Refund > Refund Request` at weight ≥24; Cancellation only when no refund intent

Align with [gemini-conversation-patterns.md](./2026-07-03-gemini-conversation-patterns.md) and Christine session (#170151, #170156).

### Task 0.2 — Posties / Young Post → B2B segment

**Files:** `classify.py` (`_apply_segment_remap` or new helper), `classifier_rules.json`, `tests/test_classify.py`

- Add `_is_posties_young_post_context(sig)` — `any_blob` mentions `posties`, `young post`
- After tier pick, remap B2C winner to B2B sibling tuple when allow-list has B2B path (same pattern as `_apply_esp_b2b_segment`)
- Broaden or replace narrow `complaint.cancel_posties.b2c` rule

### Task 0.3 — Account deletion sweep target

**Files:** `classifier_rules.json`, `rule_compile_corpus.py`, `tests/test_classify.py`

New rule:

```json
{
  "id": "account.delete_request.b2c",
  "any_blob": ["delete my account", "account deletion", "personal data erasure", "remove all of my information"],
  "tier": ["B2C", "Service Task", "Account Management", "Request to delete account", "N/A"]
}
```

Validate tier against allow-list; adjust path if workbook differs.

### Task 0.4 — Invoice request rule

**Files:** `classifier_rules.json`, `tests/test_classify.py`

New rule for invoice demand (e.g. `发票`, `invoice` + payment context) → `Billing & Admin > Invoices and PO request`. Use `exclude_blob` for pure subscription-cancel wording.

### Task 0.5 — Rosetta golden reclassify acceptance

**Files:** `tests/test_classify.py`, `tests/fixtures/` (June 24 cancellation subset if available)

- Fixture: tickets with Rosetta footer classified as Cancellation → after rules, System Report
- Close acceptance item in [2026-07-06-christine-workflow-decisions.md](./2026-07-06-christine-workflow-decisions.md)

---

## Phase 1 — Category audit entry + slice filter

**Goal:** Analyst can open an audit session for a classified category with correct ticket set.

### Task 1.1 — `CategoryAuditFilter` + row matching

**Files:** new `src/cs_tickets/category_audit_filters.py`, `tests/test_category_audit_filters.py`

```python
@dataclass(frozen=True)
class CategoryAuditFilter:
    q: str = ""
    tier1: str = ""
    categories: tuple[str, ...] = ()
    tier4: str = ""  # explicit tier4 from breakdown click
    include_tbc: bool = False  # default: classified-only audit
```

- `match_row(row, filt)` — tier1 exact; category substrings on assigned tier path (same as `tbc_queue_filters._row_matches_categories`)
- `filter_rows(rows, filt)` → list
- `slice_stats(rows, filt)` → `{ total_in_run, total_in_slice, tier4_label }`

### Task 1.2 — Audit route + HTML shell

**Files:** `portal_category_audit.py` (new), `portal_app.py`, `portal_copy.py`

```python
GET /run/{run_id}/category_audit?tier1=B2C&categories=Cancellation&tier4=Cancellation+Request
```

- Load `_RunRecord.rows`
- Render header: slice count, link back to run results, link to ticket preview with same filter
- Embed JSON payload: `tickets[]` (full rows for slice, not 200 cap), `filter`, `run_id`, `sweeps_catalog` ids

### Task 1.3 — Entry points from run results

**Files:** `portal_stats.py`, `portal_app.py`, `ticket_preview.js`

- Tier breakdown row: add **"Audit"** link → `category_audit` with `tier4` + `tier1` pre-filled
- Run results summary: CTA **"Category audit"** when run complete
- Ticket preview: **"Open audit view"** when category filter active

### Task 1.4 — NL focus on audit page

**Files:** `portal_app.py`, `category_audit.js`

- `POST /run/{run_id}/category_audit_parse_focus` — body `{ "text" }` → reuse `parse_review_focus_nl` → `{ filter, rationale }`
- Apply filter → reload audit page with query params
- Copy tweak in `tbc_filter_nl` system prompt: mention **classified category audit** as well as TBC queue

### Task 1.5 — Tests

- Filter matches B2C Cancellation only
- `include_tbc=false` excludes manual-review rows
- Audit route 404 on bad run_id; returns slice count matching manual filter

---

## Phase 2 — Bulk ticket content list

**Goal:** Read all tickets in slice without per-row click hunting.

### Task 2.1 — Bulk list component

**Files:** `portal_category_audit.py`, `category_audit.js`, `cs_tickets_theme.css`

Per ticket card:

| Field | Source |
|-------|--------|
| Ticket # | `id` |
| Subject | `subject` |
| Requester | `requester_email` if present |
| Assigned tier | 5-tuple path |
| Full content | `description` + `comments` if in row (full escape, no 80-char cap) |
| Tags | parsed list |

- Chunk size default **10**; query `offset`, `limit`
- **"Next 10"** / **"Previous"** pagination within slice
- **"Skip chunk — looks fine"** — session ack only (no relabel); advances offset (parity with TBC chunk ack)

### Task 2.2 — Row actions

Per ticket card:

- **Explain** — inline fetch `GET /run/{id}/explain/{ticket_id}?format=json` (collapsed by default)
- **Propose rule** — link to `/rules/new?run_id=&ticket_id=` (existing)

### Task 2.3 — Tests

- HTML includes ticket id + subject for all slice members across pages
- Full description present in DOM (not truncated)
- Pagination `offset` does not drop tickets

---

## Phase 3 — Validation sweeps

**Goal:** Named scans against the active slice; show matches + suggested target tier.

### Task 3.1 — Sweep catalog

**Files:** new `src/cs_tickets/category_audit_sweeps.py`, `tests/test_category_audit_sweeps.py`

```python
@dataclass(frozen=True)
class AuditSweep:
    id: str
    label: str
    description: str
    suggested_tier: tuple[str, str, str, str, str]  # validated against allow-list at load
    match_row: Callable[[dict[str, Any]], bool]
    rule_prefill: str  # Christine-style "Update: Map …" text
```

**Built-in sweeps (v1):**

| id | Match condition | Suggested target |
|----|---------------|------------------|
| `rosetta_system_email` | `rosetta system email` in blob | Billing & Admin > System Report |
| `esp_print` | `ESP-OPP`, `ESP-Inv`, or `_b2b_print_context` | B2B segment (tier resolved per row) |
| `posties_young_post` | `posties`, `young post` in blob | B2B segment |
| `account_deletion` | delete account / GDPR / erasure phrases | Request to delete account |
| `invoice_request` | invoice / 发票 demand patterns | Invoices and PO request |
| `refund_and_cancel` | refund + cancel language; assigned tier is Cancellation | Refund Request |

- `run_sweeps(rows, allow) -> list[SweepResult]` with `matched_ids`, `match_count`, `suggested_tier`, `rule_prefill`
- ESP/Posties: use same helpers as `classify.py` where possible (import shared detection functions — extract to `audit_signals.py` if needed to avoid circular imports)

### Task 3.2 — Sweep API

**Files:** `portal_app.py`

```python
GET /run/{run_id}/category_audit/sweeps?tier1=...&categories=...
→ { sweeps: [{ id, label, match_count, matched_ids[], suggested_tier, rule_prefill }] }
```

- Applies `CategoryAuditFilter` first, then runs each sweep on slice only
- `matched_ids` capped at 50 in JSON; `match_count` always full

### Task 3.3 — Sweep panel UI

**Files:** `portal_category_audit.py`, `category_audit.js`

- Load sweeps on page init (or "Run sweeps" button for large slices)
- Row per sweep: label, count, expand matched IDs, **Draft rule** → opens inline compile panel (reuse `tbc_queue.js` patterns) or navigates to `/rules/new` with prefill query param
- Highlight sweeps with `match_count > 0` (warning style)

### Task 3.4 — Tests

- Rosetta sweep finds Christine fixture tickets
- Sweep on empty slice returns 0 matches
- Suggested tiers are allow-listed

---

## Phase 4 — Sweep → rule → reclassify loop

**Goal:** Close the loop: fix pattern, Confirm, see bucket shrink.

### Task 4.1 — Slice impact on rule draft

**Files:** `portal_app.py`, extend `tbc_filter_nl.build_filter_batch_rule_prefill` or add `build_sweep_rule_prefill(sweep, matched_count, examples)`

```python
POST /run/{run_id}/category_audit/draft_rule
Body: { "sweep_id": "rosetta_system_email", ...filter fields }
→ { prefill, matched_count_in_slice, matched_count_in_run, example_tickets[] }
```

- `matched_count_in_slice` — primary number shown to analyst ("17 of 16 Cancellation — wait, 17 in run total in category before fix")
- Include up to 3 example ticket subjects in prefill

### Task 4.2 — Inline compile + confirm panel

**Files:** `category_audit.js`, reuse `POST /rules/compile`, `POST /rules/confirm` or `confirm_batch`

- Same flow as TBC queue batch rule panel
- After Confirm: auto-prompt **Re-classify run**
- `POST /run/{id}/reclassify` → redirect back to audit page with banner: `Cancellation: 33 → 16 tickets`

### Task 4.3 — Before/after slice counts

**Files:** `portal_category_audit.py`, `reclassify_run_rows` metadata

- Store on `_RunRecord`: `last_reclassify_at`, optional `reclassify_history[]` with `{ tbc_before, tbc_after, category_counts_snapshot }`
- Audit header: "16 in slice (was 33 before reclassify)"

### Task 4.4 — Tests

- Draft rule endpoint returns non-zero `matched_count_in_slice` for Rosetta fixture
- Reclassify reduces Cancellation count in golden fixture
- Analyst without Confirm can compile but not confirm (existing gate)

---

## Phase 5 — Reporting & efficiency (backlog within plan)

**Goal:** Weekly report handoff and hygiene checks.

### Task 5.1 — Category slice CSV export

```python
GET /run/{run_id}/category_audit/export.csv?tier1=...&categories=...
```

Columns: `id`, `subject`, `requester_email`, full `description`, assigned 5-tuple, tags, `created_at`.

### Task 5.2 — Representative examples (template)

**Files:** `category_audit_filters.py` or `portal_stats.py`

- `pick_representative_examples(rows, n=3)` — diversify by subject length, sender domain, tag set
- Render in audit header as "Examples for weekly report" copy block (static text, no LLM)

### Task 5.3 — Duplicate detection within slice

**Files:** `category_audit_sweeps.py` or `category_audit_duplicates.py`

- Group by `(requester_email, normalize_subject(subject))` where count > 1
- Show as optional sweep row: **"Possible duplicates"** with ticket id groups

### Task 5.4 — Batch-over-batch comparison (optional)

- Defer unless `_RunRecord` history or exported run summaries exist
- Show tier4 count delta vs previous run if `sessionStorage` or server stores last summary JSON

---

## API summary

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/run/{run_id}/category_audit` | Audit page HTML |
| POST | `/run/{run_id}/category_audit_parse_focus` | NL → filter |
| GET | `/run/{run_id}/category_audit/sweeps` | Run validation sweeps on slice |
| POST | `/run/{run_id}/category_audit/draft_rule` | Sweep → rule prefill + match counts |
| GET | `/run/{run_id}/category_audit/export.csv` | Phase 5 — slice download |
| POST | `/run/{run_id}/reclassify` | Existing — refresh after Confirm |

Existing reuse: `/rules/compile`, `/rules/confirm`, `/rules/confirm_batch`, `/run/{id}/explain/{ticket_id}`.

---

## Files (expected)

| File | Role |
|------|------|
| `src/cs_tickets/category_audit_filters.py` | Slice filter + stats |
| `src/cs_tickets/category_audit_sweeps.py` | Sweep catalog + runners |
| `src/cs_tickets/portal_category_audit.py` | HTML builders |
| `src/cs_tickets/static/category_audit.js` | Pagination, sweeps, compile panel |
| `tests/test_category_audit_filters.py` | Filter tests |
| `tests/test_category_audit_sweeps.py` | Sweep tests |
| `tests/test_portal_category_audit.py` | Route + integration |

**Modified:** `portal_app.py`, `portal_stats.py`, `portal_copy.py`, `classify.py`, `classifier_rules.json`, `cs_tickets_theme.css`, `ticket_preview.js` (audit link).

---

## Implementation order

```text
Phase 0 (classifier) ──can ship first──┐
                                       ├── Phase 3 (sweeps) depends on Phase 0 for meaningful reclassify
Phase 1 (entry + filter) ──► Phase 2 (bulk list) ──► Phase 3 ──► Phase 4
                                                                       └── Phase 5 (export, duplicates)
```

**Suggested MVP:** Phase 0 + Phase 1 + Phase 3 + Phase 4 (no bulk list pagination polish) — analyst can audit via sweeps + match IDs even before Phase 2 UX is polished.

---

## Acceptance criteria

### Phase 0

- [x] Refund + cancel → Refund Request (B2C) in tests
- [x] Posties / Young Post mention → B2B segment in tests
- [x] Account deletion phrases → Request to delete account
- [x] Rosetta footer → System Report; not Cancellation

### Phase 1–2

- [x] Analyst can open audit for a tier breakdown category with correct slice count
- [x] NL focus `"review B2C cancellation"` sets filter on audit page
- [x] All tickets in slice listed with full description (paginated, expandable cards)
- [x] Default slice excludes TBC unless opted in

### Phase 3–4

- [x] Six built-in sweeps return match lists for active slice
- [x] Sweep with matches offers Draft rule with `matched_count_in_slice` and `matched_count_in_run`
- [x] Inline compile/preview/confirm on audit page; reclassify with snapshot after Confirm
- [x] Audit page shows before/after count banner post-reclassify (`?reclassified=1`)
- [x] Analyst without Confirm can compile but not confirm (lead gate on page + `/rules/confirm` 403)

### Phase 5

- [x] CSV export downloads full slice with descriptions
- [x] Duplicate groups surfaced for webhook-style repeats (7th sweep)
- [x] Representative examples block for weekly report handoff
- [ ] Batch-over-batch tier4 comparison (deferred)

---

## Verification

```bash
# Phase 0
pytest -q tests/test_classify.py -k "rosetta or posties or refund_cancel or account_delete"

# Phase 1–4
pytest -q tests/test_category_audit_filters.py tests/test_category_audit_sweeps.py tests/test_portal_category_audit.py

# Regression
pytest -q tests/test_portal_tbc_queue.py tests/test_portal_ticket_preview.py
```

Manual: Run June 24 export → audit B2C Cancellation → Rosetta sweep → Confirm rule → reclassify → expect ~16 genuine cancellations (per Christine session).

---

## Related documents

- [2026-07-07-christine-category-audit-workflow.md](./2026-07-07-christine-category-audit-workflow.md) — session excerpt + rules locked
- [2026-07-06-christine-workflow-decisions.md](./2026-07-06-christine-workflow-decisions.md) — Model B, Phase C items promoted here
- [2026-07-03-gemini-conversation-patterns.md](./2026-07-03-gemini-conversation-patterns.md) — sweep patterns + precedence
- [2026-07-02-category-review-and-drill-down-notes.md](./2026-07-02-category-review-and-drill-down-notes.md) — drill-down foundation
