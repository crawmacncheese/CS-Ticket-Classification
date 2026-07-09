# TBC Queue — Review Focus, Session Continuity & Allow-List Gaps — Implementation Notes

**Date:** 2026-07-06  
**Implements:** [2026-07-06-christine-workflow-decisions.md](./2026-07-06-christine-workflow-decisions.md) Phase A–B, [2026-07-03-gemini-conversation-patterns.md](./2026-07-03-gemini-conversation-patterns.md) (TBC table + Christine batch review), [2026-07-03-explicit-rule-authoring.md](./2026-07-03-explicit-rule-authoring.md) §3.3.

## Summary

Extended the **manual review (TBC) queue** from a linear 10-ticket chunk viewer into a **Christine-style review session**: keyword/category **focus batches**, **natural-language focus** parsing, **session-persistent** suggestions and compiled rules, **batch rule compile/confirm**, clearer **skip/finish** flow, **allow-list rejection diagnostics** with optional **add exemplar**, and **LLM category retry** when the model returns TBC.

Static asset version: `tbc_queue.js?v=7`.

---

## Design decisions

### Allow-list rejection (category suggestion)

| Outcome | Cause code | Meaning | User action |
|---------|------------|---------|-------------|
| Not in taxonomy | `hallucinated` | Path not in Taxonomy.csv or allow-list | Pick a valid category manually |
| Close match | `typo_close_match` | Near-miss on allow-list (often Tier4 typo) | Use closest path shown |
| Known category, no exemplar | `taxonomy_not_allowlisted` | Taxonomy-valid path missing from workbook union | **Add to allow-list** (team lead) |

**Decisions:**

- Rejection is classified in `taxonomy.classify_allowlist_rejection()` using allow-list novelty + taxonomy CSV four-tuples + fuzzy Tier4 match (`difflib`, cutoff 0.8).
- `granular_new` or in-taxonomy paths → `can_add_to_allowlist=True`; tier1-new and hallucinated paths → no one-click add.
- Add flow uses `allowlist_training.commit_tbc_exemplar()`: snapshot `doc/`, append one workbook row from the TBC ticket, optional training rule — same safety model as Training commit.
- Requires `PORTAL_ALLOW_CONFIRM=1` and writable `doc/` (`training_available()`).

### AI category suggestion (compile-only LLM)

- **TBC tier rejected:** If the model returns manual review / TBC, retry up to **3** times (`_MAX_TBC_LLM_RETRIES`) before falling back to classifier top candidate.
- **Not in allow-list:** Surface classified cause (above) in API `allowlist_rejection` and UI; generic `"Model tier not in allow-list."` removed.

### Session continuity (chunk navigation)

| Stored in `sessionStorage` (`tbc-review-{run_id}`) | Purpose |
|----------------------------------------------------|---------|
| `suggest` | AI category suggestion per ticket — **no LLM re-call** when revisiting a chunk |
| `explain` | Explain JSON cache |
| `compiled` | Per-ticket compiled `RuleSpec` |
| `drafts` | Rule textarea text per ticket |
| `filters` | Contains / segment / category focus / NL text |
| `ruleTarget` | Parsed move-to category from NL focus (for batch rule draft) |
| `filterRuleDraft` / `filterBatchRule` | Batch rule panel draft + compiled rule |

**Decision:** Caches are **not** cleared on prev/next chunk (only panel rows close). Chunk size change resets offset to 0.

### Batch rule operations

| Feature | Scope | Endpoint / UI |
|---------|-------|----------------|
| Compile draft rules in chunk | Current chunk tickets with prefill/draft, not yet compiled | Client loops `POST /rules/compile` |
| Confirm all compiled | All compiled rules in current chunk | `POST /rules/confirm_batch` — single backup + version bump (`confirm_explicit_rules_batch`) |
| Draft rule for filter | Whole focus set | `POST /run/{id}/tbc_draft_rule_for_filter` → batch panel |

**Decision:** Batch confirm uses one live backup (not N confirms) to match `/learn` promote safety.

### Skip / finish flow

- **"Rest look fine"** renamed **"Skip chunk — no rule needed"** — acks ticket IDs, advances offset without resetting to chunk 1.
- **"Finish → run results"** always visible.
- When `total_pending_unfiltered === 0`, show **Review complete** panel with results + re-classify CTA.
- Ack response includes `queue_complete`, `total_pending` (filtered), `total_pending_unfiltered`, `next_offset` aligned to active filter.

### Review focus filtering (Christine batching)

**Structured filters** (applied server-side before chunking):

| Param | Matches |
|-------|---------|
| `q` | subject, description, tags, requester, id (substring) |
| `tier1` | `Tier1_Segment` exact |
| `categories` | Comma-separated substrings against assigned tier, top candidate, suggested tier |
| `tbc_reason` | Explain reason bucket |

**Facets:** First queue load (`include_facets=1`) returns counts for tier1, tier4, top candidates, TBC reasons → **quick focus chips** in UI.

**Decision:** Filter persists across chunks (session + query params). Progress shows `N in focus · M total` when filtered.

### Natural-language review focus

Christine-style utterances → structured filter + optional rule target:

| Example input | Parsed result |
|---------------|---------------|
| `anything contains sherina move under Print` | `q=sherina`, categories includes Print, `rule_target=Print` |
| `review B2C 1. access loop 2. cancellation` | `tier1=B2C`, categories from numbered list + taxonomy token match |

**Pipeline:** `tbc_filter_nl.parse_review_focus_deterministic()` first; if fail and `RULE_COMPILE` configured → `parse_review_focus_nl()` LLM JSON.

**Batch rule prefill:** `build_filter_batch_rule_prefill()` — Christine `Update: Map …` + matched count + up to 3 example tickets.

**Decision:** NL parse is **filter-only** (not `/run` classify). No batch LLM categorization (NG-01).

---

## API additions / changes

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/run/{run_id}/tbc_queue` | Query: `q`, `tier1`, `categories`, `tbc_reason`, `include_facets=1` |
| POST | `/run/{run_id}/tbc_parse_focus` | Body `{ "text" }` → `{ filter, rule_target, rationale, source }` |
| POST | `/run/{run_id}/tbc_draft_rule_for_filter` | Body filter fields + `rule_target` → `{ prefill, matched_count }` |
| POST | `/run/{run_id}/add_allowlist_tuple/{ticket_id}` | Body `{ tier: [5] }` — exemplar commit (lead) |
| POST | `/rules/confirm_batch` | Body `{ rules: [...] }` — multi-rule confirm |
| POST | `/run/{run_id}/tbc_chunk/ack` | Body adds filter fields for correct `next_offset` |

Existing: `POST /run/{id}/suggest_category/{ticket_id}`, `POST /run/{id}/reclassify`, `/rules/compile`, `/rules/confirm`.

---

## Files added

| File | Role |
|------|------|
| `src/cs_tickets/tbc_queue_filters.py` | `TbcQueueFilter`, row matching, facets |
| `src/cs_tickets/tbc_filter_nl.py` | NL parse + batch rule prefill |
| `tests/test_allowlist_rejection.py` | Rejection classification |
| `tests/test_tbc_queue_filters.py` | Filter matching |
| `tests/test_tbc_filter_nl.py` | NL parse + prefill |

## Files changed (main)

| File | Changes |
|------|---------|
| `src/cs_tickets/category_suggest.py` | TBC retry; `allowlist_rejection` on suggest result |
| `src/cs_tickets/taxonomy.py` | `AllowlistRejectionInfo`, `classify_allowlist_rejection`, `append_exemplar_row` |
| `src/cs_tickets/allowlist_training.py` | `commit_tbc_exemplar` |
| `src/cs_tickets/feedback/promote.py` | `confirm_explicit_rules_batch` |
| `src/cs_tickets/portal_tbc_queue.py` | Filter bar, NL row, batch rule panel, completion panel |
| `src/cs_tickets/portal_app.py` | New routes; filter params on queue |
| `src/cs_tickets/static/tbc_queue.js` | Session, batch, filters, NL, completion UX |
| `src/cs_tickets/static/cs_tickets_theme.css` | Filter / batch / completion styles |
| `tests/test_portal_tbc_queue.py` | Filter + parse + draft endpoints |

---

## Permissions

| Action | Requires |
|--------|----------|
| Apply focus, skip chunk, compile, preview | Any user |
| Confirm live / confirm batch / add allow-list | `PORTAL_ALLOW_CONFIRM=1` + writable `doc/` (for allow-list add) |

---

## Verification

```bash
pytest -q tests/test_allowlist_rejection.py tests/test_tbc_queue_filters.py tests/test_tbc_filter_nl.py tests/test_portal_tbc_queue.py tests/test_category_suggest.py
```

---

## Not implemented (backlog)

- NL focus → auto-run compile (user still clicks Draft rule → Compile)
- Filtered ack scoped only to focus set across entire run in one click (today: per chunk)
- `GET /rules/export` (Phase B item 6 in workflow decisions)
- Rules version hash on run metadata
- Phase 2 run-scoped single-ticket relabel

---

## References

- [2026-07-03-gemini-conversation-patterns.md](./2026-07-03-gemini-conversation-patterns.md) — core loop, TBC table shape, Update: Map phrasing
- [2026-07-06-christine-workflow-decisions.md](./2026-07-06-christine-workflow-decisions.md) — Model B roles, re-classify after confirm
