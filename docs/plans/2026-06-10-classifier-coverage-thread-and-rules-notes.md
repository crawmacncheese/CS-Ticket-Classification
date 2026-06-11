# Classifier Coverage — Thread Enrichment — Implementation Notes

**Date:** 2026-06-10  
**Plan:** [2026-06-10-classifier-coverage-thread-and-rules.md](./2026-06-10-classifier-coverage-thread-and-rules.md)  
**Scope shipped:** Phase A (thread enrichment) only. Phase B rule batch deferred.

---

## CONTEXT.md alignment

- **Code preservation:** New module `thread_enrich.py`; minimal edits to `_signals()`, one computed block in `classify.py`, `strip_enrichment` wired in `attach_tiers` only.
- **Allow-list / 5-tuple / TBC:** Unchanged — enrichment affects scoring only; output tiers still constrained by allow-list.
- **Training / exemplar rows:** Unaffected — no `doc/` writes.
- **Glossary:** Added **Thread enrichment** entry to `CONTEXT.md`.

---

## What was built

### `src/cs_tickets/thread_enrich.py`

| Function | Role |
|----------|------|
| `build_ticket_index` | Lightweight `id → TicketThreadContext` (tags, subject, description) |
| `enrichment_for_row` | Internal keys for reply tickets with resolvable parent |
| `flatten_for_classify` | `flatten_ticket` + merge enrichment |
| `strip_enrichment` | Remove internal keys before master output |

**Parent resolution:** `via.source.from.ticket_id`, fallback `problem_id`.

**Reply detection:** `RE:` / `FW:` subject prefix, or `via.source.rel == "follow_up"`.

### Classifier changes

- `_signals()` reads `_enriched_tags` and `_thread_blob` when present.
- `_RowSignals.is_reply` drives reply-specific computed rules.
- `computed:reply_inherit_parent_tags.b2c` — subscriber/renewal tags on enriched replies → Rate or Renewal Inquiry.
- `attach_tiers` strips internal keys on return (CSV/XLSX never expose enrichment).

### Pipeline integration

All classification entry points use the same path:

- `pipeline.iter_master_rows` — index built from export, then classify
- `allowlist_compare.compare_allowlists_on_ndjson` — two-pass (index + classify)
- `batch_allowlist_analysis.build_old_classification_cache` — per-file index

### Justification for `attach_tiers` change

Stripping in `attach_tiers` ensures portal download and CLI output never leak `_enriched_*` keys, even if a caller forgets to strip. Single choke point; `flatten.py` untouched.

---

## Phase B

Not implemented in this pass (activation, unsubscribe, OFCA, delivery rules). Run `audit_classifier` after deploying Phase A to re-baseline TBC before rule batch 4.

---

## Tests

```bash
pytest tests/test_thread_enrich.py tests/test_classify.py::test_reply_inherits_parent_subscriber_tags -q
pytest -q
```

---

## A/B toggle

Thread enrichment is **on by default**. To disable:

```powershell
$env:CS_TICKETS_THREAD_ENRICHMENT = "0"
uvicorn cs_tickets.portal_app:app --reload --port 8777
```

Remove the env var to re-enable enrichment.

---

## Validate on real export (manual)

Inspect one `RE:` line in `data/*.ndjson` and confirm `via.source.from.ticket_id` matches the parent ticket id in the same file. Field shapes can vary by export job — adjust `parent_ticket_id()` only if a real sample differs.
