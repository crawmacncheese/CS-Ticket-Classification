# Classifier Coverage — Thread Enrichment & Rule Batch 4 — Implementation Plan

> **For implementer:** When you execute this plan (the actual coding), document your steps, process, and final design decisions in a separate markdown file (e.g. `docs/plans/2026-06-10-classifier-coverage-thread-and-rules-notes.md`) so the requester can review rationale, catch bugs early, and understand the code. This plan describes *what* to build; that notes file describes *what you did*.

**Goal:** Reduce avoidable **TBC (Manual Review)** on production Zendesk exports by (1) enriching reply-thread tickets with parent-ticket signals before classification, and (2) adding a fourth targeted rule batch for high-volume categories that remain `zero_candidate` after prior batches.

**Architecture:** Keep the existing weighted rule engine and allow-list contract. Add a **pre-classification enrichment pass** in `pipeline.py` that merges parent tags/subject into reply rows without changing `MASTER_COLUMNS`. Extend `_signals()` / computed rules and `classifier_rules.json` for new patterns. Measure impact with `tools/audit_classifier.py`, golden NDJSON bounds, and May 14 / May 18 export baselines before merge.

**Tech stack:** Python 3.11, stdlib, existing `classify.py` / `classifier_rules.json` / `pytest`. No ML.

**Depends on:** [2026-05-14-tier-classifier-improvements.md](./2026-05-14-tier-classifier-improvements.md) (shipped batches 1–3), [2026-06-09-training-rule-proposals.md](./2026-06-09-training-rule-proposals.md) (golden fixture + `tbc_reason` buckets).

**PRD alignment:** User story 9 (reply-thread classification), Phase 2 planned items (richer flattening, targeted rules).

**CONTEXT.md alignment:** Enrichment is scoring-only — does not change the **allow-list**, **5-tuple** output contract, **reference workbook**, or **Training** flow. New code lives in `thread_enrich.py` per code-preservation rule. Domain term documented in glossary as **Thread enrichment**.

---

## Context

### Current baseline (May 2026 exports)

After rule batches 1–3 (see implementation log in `2026-05-14-tier-classifier-improvements.md`):

| Export | Rows | TBC | TBC % |
|--------|------|-----|-------|
| May 14 (`export-2026-05-14-…`) | 634 | **60** | 9.5% |
| May 18 (`export-2026-05-18-…`) | 459 | **65** | 14.2% |

Most remaining TBC rows are **`zero_candidate`** — rules never fire, not margin/threshold failures.

### Explicitly unresolved (from audit log)

| Pattern | Est. volume | Root cause |
|---------|---------------|------------|
| `RE:` / `Re:` / `FW:` reply subjects | ~63 combined | Subject-only signal; parent tags absent |
| Activation failures | taxonomy leaf exists | No dedicated rule |
| Newsletter unsubscribe | taxonomy leaf exists | Partial coverage via `account.update_info` tags only |
| OFCA / regulatory | taxonomy leaf exists | No rule |
| Delivery resumption / missing delivery | backlog | No rule batch yet |
| AlipayHK auto-debit notices | mixed | Partial guard; needs label sprint before broad rules |
| `miscellaneous` / `other_departments` alone | high TBC correlation | Tagging hygiene + cautious rules |

### How classification reads signals today

```python
# classify._signals — tags, subject, description, url only
blob = f"{subject} {raw_subject} {description}"
```

Reply tickets often have empty or generic tags (`miscellaneous`) while the **parent** ticket carries `subscription_-_renew`, `existing_subscriber`, etc. Current reply handling only matches renewal phrases **in the reply subject** (`computed:reply_renewal_subject.b2c`).

### Code preservation

Per `CONTEXT.md`: add new functions/modules; extend `_signals` with optional enriched fields rather than rewriting `classify_row` or `flatten_ticket` wholesale.

---

## Design decisions

| Topic | Decision | Rationale |
|-------|----------|-----------|
| Enrichment location | `pipeline.py` two-pass over export file | Parent ticket must exist in same NDJSON; no API calls |
| Output schema | **No new `MASTER_COLUMNS`** for Phase 1 | Avoid workbook/portal churn; enrichment is classifier-internal |
| Enrichment storage | Ephemeral dict keys on row passed to `attach_tiers` | `_enriched_tags`, `_parent_id`, `_thread_blob` — stripped before CSV/XLSX emit |
| Parent resolution | `via.source.from.ticket_id` → index lookup; fallback `problem_id` | Standard Zendesk export fields |
| Tag merge | Union parent tags + child tags (deduped, lowercased) | Child tags preserved; parent fills gaps |
| Thread blob | `parent_subject + parent_description + child blob` capped at 1200 | Gives `any_blob` rules parent context without new RuleSpec fields |
| Reply detection | `subject` starts with `re:` / `fw:` OR `via.source.rel == "follow_up"` | Covers subject-less follow-ups |
| Missing parent | No-op — classify child as today | Export may omit parent ticket |
| Rule batch scope | JSON rules + small computed guards only | Explainable; audit before merge |
| Thresholds | **Do not** change `SCORE_THRESHOLD`, `MIN_SCORE_MARGIN`, `HIGH_CONFIDENCE_SCORE` | Isolate coverage gains from gate tuning |
| B2B paths | Mirror B2C rules where taxonomy has B2B siblings | Use `requires_b2b_print_context` when printsupport signals present |
| AlipayHK | **Hold** broad automation; extend `_is_alipayhk_auto_debit_notice` only if sampled | PRD risk: mis-route system notices |
| Golden fixture | Extend `golden_export.ndjson` + tighten `golden_baseline.json` ceilings | Catch regressions; do not freeze allow-list |

### Parent ticket resolution (normative)

```text
1. Parse export once → dict[id → ticket_json]
2. For each ticket:
   a. parent_id = ticket.get("via", {}).get("source", {}).get("from", {}).get("ticket_id")
      OR ticket.get("problem_id")  # when via missing but problem link present
   b. If parent_id and parent_id in index:
      - merged_tags = union(child.tags, parent.tags)
      - thread_blob = f"{parent.subject} {parent.description} {child.subject} {child.description}"[:1200]
   c. Pass enrichment dict into flatten → classify path
3. strip_internal_enrichment(row) before yielding master row
```

**Validate against a real export** in `data/` during Task 1 — field names vary slightly across Zendesk export jobs. Document actual JSON paths in implementer notes.

---

## Functional requirements

| ID | Requirement |
|----|-------------|
| FR-C1 | `enrich_ticket_from_export_index(ticket, index)` returns optional enrichment metadata |
| FR-C2 | `iter_master_rows` performs index build + per-ticket enrichment before `attach_tiers` |
| FR-C3 | `_signals()` uses merged tags when `_enriched_tags` present on row |
| FR-C4 | `_signals()` exposes `thread_blob` (or extends `blob`) for rules matching parent context |
| FR-C5 | Enrichment keys never appear in CLI CSV or portal XLSX output |
| FR-C6 | `classify_row(row, allow)` signature unchanged for external callers |
| FR-C7 | New rules target only allow-listed 5-tuples |
| FR-C8 | Each new rule has a focused pytest in `test_classify.py` |
| FR-C9 | `audit_classifier` report unchanged in shape; TBC % improves on May 14 export |
| FR-C10 | Golden NDJSON test still passes with updated ceilings documented in notes |

---

## Phase A — Thread enrichment

### Task 1 — Export index and enrichment module

**Files (new):**

- `src/cs_tickets/thread_enrich.py`

**Files (modify):**

- `src/cs_tickets/pipeline.py` — build index, enrich, strip internal keys
- `tests/test_thread_enrich.py` (new)

**API sketch:**

```python
INTERNAL_ENRICHMENT_KEYS = frozenset({"_enriched_tags", "_parent_ticket_id", "_thread_blob", "_is_reply"})

def build_ticket_index(tickets: Iterable[dict]) -> dict[int, dict]: ...

def enrich_ticket(ticket: dict, index: dict[int, dict]) -> dict:
    """Return ticket copy with optional internal enrichment keys."""

def strip_enrichment(row: dict) -> dict: ...
```

**Tests:**

- Parent tags merged into `_enriched_tags` when child is `RE:` reply
- Missing parent → no enrichment keys
- `strip_enrichment` removes all internal keys from output row

**Step 0 (manual):** Inspect one real NDJSON line for a `RE:` ticket; record JSON path to parent id in implementer notes.

### Task 2 — Wire enrichment into classifier signals

**Files (modify):**

- `src/cs_tickets/classify.py` — `_signals()` reads `_enriched_tags` / `_thread_blob`
- `tests/test_classify.py` — reply with parent `existing_subscriber` classifies without relying on reply subject alone

**Signal change (minimal):**

```python
def _signals(row: dict[str, Any]) -> _RowSignals:
    tags_cell = row.get("_enriched_tags") or row.get("tags")
    ...
    thread = row.get("_thread_blob") or ""
    blob = f"{subject} {raw_subject} {desc} {thread}".strip()
```

**Computed rule (new):**

- `computed:reply_inherit_parent_tags.b2c` — when `_is_reply` and parent tags contain renewal/subscriber tokens, apply existing renewal/subscriber weights at weight 10 (same tuples as `computed:chat_account_subscriber.b2c` path)

Do **not** duplicate every JSON rule for replies — inheritance handles the bulk case.

### Task 3 — Streaming index without full-memory load (if needed)

If May exports fit in memory (~40k tickets × ~2KB ≈ 80MB), a single-pass buffer is acceptable for Phase 1.

If memory is a concern:

- **Option A (preferred):** Two-pass — pass 1 builds id→tags/subject/description index only (lightweight); pass 2 classifies
- **Option B:** Defer — document in notes

**Acceptance:** May 14 export processes without OOM on a single pod (NFR-03).

---

## Phase B — Rule batch 4 (targeted categories)

Run `tools/audit_classifier` on May 14 export **after Phase A** to rank remaining `zero_candidate` tags/subjects. Implement rules in priority order below; skip any category with &lt;5 tickets in sample unless unambiguous language.

### Task 4 — Activation failures

**Target tuples:**

- `B2C / Complaint / Technical Bug / Not able to activate the account / N/A`
- `B2B / Complaint / Technical Bug / Not able to activate the account / N/A` (if in allow-list)

**`classifier_rules.json`:**

```json
{
  "id": "tech.activation_failure.b2c",
  "tier": ["B2C", "Complaint", "Technical Bug", "Not able to activate the account", "N/A"],
  "weight": 12.0,
  "any_blob": [
    "not able to activate",
    "unable to activate",
    "cannot activate my account",
    "can't activate",
    "activation email",
    "activate the account"
  ],
  "exclude_blob": ["unsubscribe", "cancel"]
}
```

**Computed guard:** skip when `_is_non_renewal_intent` or cancel/refund tags present.

### Task 5 — Newsletter unsubscribe / email change

**Target:** `B2C / Service Task / Account Management / Unable to Unsubscribe from Email / N/A`

**Rules:**

- `account.unsubscribe.b2c` — `any_blob`: unsubscribe, opt out, stop receiving emails, remove from mailing list
- `account.newsletter_email_change.b2c` — extend existing newsletter tuple paths with unsubscribe-adjacent phrases not covered by `account.contact_change`

**Guard:** exclude `"subscribe"` without `"unsubscribe"` (avoid renewal false positives).

### Task 6 — OFCA / regulatory

**Target:** `B2C / Service Task / Regulatory / Admin / OFCA / N/A`

**Rule:**

- `regulatory.ofca.b2c` — `any_subject` / `any_blob`: `ofca`, `office of the communications authority` (weight 14 — high confidence proper noun)

### Task 7 — Delivery resumption / missing delivery

**Targets (verify allow-list membership first):**

- `B2C / Service Task / Logistics / Print Subs - Suspension and Resume confirmation / N/A`
- Related logistics tuples if audit shows volume

**Rules (data-driven):**

- `logistics.delivery_resumption.b2c` — resume delivery, restart delivery, suspension lifted
- `logistics.missing_delivery.b2c` — missing issue, not received, delivery delay (audit top subjects)

Use weight 11–12; require logistics-related tags where available (`delivery`, `print_subs`).

### Task 8 — Unreachable allow-list audit pass

**Files (modify):**

- `tools/audit_classifier.py` — already reports unreachable tuples

**Process (manual, not code):**

1. Run audit → list unreachable 5-tuples with COUNTA &gt; 0 in Taxonomy.csv
2. For each tuple with ≥10 historical tickets in workbook sample, add a rule **or** document as intentional TBC
3. Cap batch at **10 new rules** to keep review manageable

---

## Phase C — Measurement & regression

### Task 9 — Baseline audit script

**Before/after table** (implementer runs and pastes into notes):

```bash
PYTHONPATH=src python -m tools.audit_classifier --input data/export-2026-05-14-....json
PYTHONPATH=src python -m tools.audit_classifier --input data/export-2026-05-18-....json
pytest -q tests/test_classify.py tests/test_thread_enrich.py tests/test_golden_classifier.py
```

**Target (directional, not a hard gate):**

| Export | TBC before | TBC after (goal) |
|--------|------------|------------------|
| May 14 | 60 | ≤45 (−15 min) |
| May 18 | 65 | ≤50 |

Adjust goals after Phase A measurement — thread enrichment alone may capture most reply-thread TBC.

### Task 10 — Golden fixture update

**Files (modify):**

- `tests/fixtures/golden_export.ndjson` — add 2–3 reply tickets with parent index entries in same file
- `tests/fixtures/golden_baseline.json` — update `tbc_max` if net TBC decreases on fixture

---

## Implementation tasks (ordered)

| Order | Task | Est. |
|-------|------|------|
| 1 | Task 1 — `thread_enrich.py` + index | 1–1.5 d |
| 2 | Task 2 — `_signals` + reply inheritance rule | 1 d |
| 3 | Task 3 — two-pass streaming (if needed) | 0.5 d |
| 4 | Task 4 — activation rules | 0.5 d |
| 5 | Task 5 — unsubscribe rules | 0.5 d |
| 6 | Task 6 — OFCA rule | 0.25 d |
| 7 | Task 7 — delivery rules | 0.5–1 d |
| 8 | Task 8 — unreachable tuple audit (manual + ≤10 rules) | 1 d |
| 9 | Task 9 — baseline audit | 0.25 d |
| 10 | Task 10 — golden fixture | 0.5 d |

**Total:** ~6–8 days

---

## Acceptance criteria

### Phase A (thread enrichment)

- [ ] `RE:` ticket with untagged child + tagged parent classifies using parent tags
- [ ] Output CSV/XLSX rows contain only `MASTER_COLUMNS` (no `_enriched_*` keys)
- [ ] `classify_row(row, allow)` works on rows without enrichment keys (backward compatible)
- [ ] May 14 export: measurable TBC decrease vs 60 baseline

### Phase B (rules)

- [ ] Each new rule has pytest with positive + negative case
- [ ] No new coercion warnings on sample export
- [ ] All rule targets ∈ `load_allowlist()`
- [ ] `pytest -q` passes

### Non-regression

- [ ] Training preview / commit unchanged
- [ ] `compare_allowlists_on_ndjson` metrics comparable before/after (same TBC definition)
- [ ] Confidence thresholds unchanged

---

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Parent ticket not in same export | Document limitation; enrichment no-op; future: sidecar parent export |
| Over-broad `any_blob` on activation | `exclude_blob` guards; weight 12 not 15; audit changed rows |
| Reply inheritance double-counts weights | Single computed inheritance rule; don't also fire child-only duplicates |
| Zendesk `via` shape differs | Task 1 validates real export; fallback `problem_id` |
| Memory on 40k+ exports | Lightweight index (tags/subject/desc only); two-pass |
| Mis-route unsubscribe as renewal | Unsubscribe rules require unsubscribe phrases; exclude subscribe-only |

---

## Out of scope

- ML / LLM classification
- Zendesk API live parent fetch
- New `MASTER_COLUMNS` for parent id on workbook output
- AlipayHK bulk automation (label sprint first)
- Changing scoring thresholds globally
- Taxonomy.csv edits (rules only)

---

## Related documents

- [design.md](../design.md) §11 Extension points, §12 Limitations
- [prd.md](../prd.md) Phase 2 planned items
- [2026-05-14-tier-classifier-improvements.md](./2026-05-14-tier-classifier-improvements.md) — prior batches and audit baselines
