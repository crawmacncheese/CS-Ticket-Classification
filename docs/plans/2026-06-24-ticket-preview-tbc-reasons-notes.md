# Ticket Preview & TBC Reasons — Implementation Notes

**Date:** 2026-06-24  
**Plan:** [2026-06-24-ticket-preview-tbc-reasons.md](./2026-06-24-ticket-preview-tbc-reasons.md)

## Summary

Implemented **Phase 1** and **Phase 2** of the ticket preview and TBC reason visibility plan.

## Design decisions

| Topic | Decision |
|-------|----------|
| Reason capture | `attach_tiers_with_meta()` in `classify.py` — single `classify_row_with_explanation()` pass; `attach_tiers()` delegates to it |
| Bucket mapping | `portal_reason_bucket()` in `classify.py` (uses `is_manual_review_row` from `portal_stats` for coercion edge cases) |
| Portal pipeline | `iter_master_rows_with_meta()` in `pipeline.py`; CLI unchanged on `iter_master_rows()` |
| Run storage | `_RunRecord.tbc_reasons: dict[str, str]` — not written to Excel |
| Preview component | New `portal_ticket_preview.py` + `static/ticket_preview.js` |
| Compare metrics | `allowlist_compare` zero_candidate scoped via `_count_tbc_bucket`; added `allowlist_filtered_*` and `other_*` |

## Files changed

### Phase 1

- `src/cs_tickets/classify.py` — `portal_reason_bucket`, `attach_tiers_with_meta`
- `src/cs_tickets/pipeline.py` — `iter_master_rows_with_meta`, refactored `_iter_classified_tickets`
- `src/cs_tickets/portal_app.py` — `tbc_reasons` on run record, reason summary, shared preview, `ticket_preview.js` on result page
- `src/cs_tickets/portal_stats.py` — `tbc_reason_counts`, `tbc_reason_summary_html`
- `src/cs_tickets/portal_copy.py` — TBC labels and preview copy constants
- `src/cs_tickets/portal_ticket_preview.py` — **new**
- `src/cs_tickets/static/ticket_preview.js` — **new**
- `src/cs_tickets/static/cs_tickets_theme.css` — preview + TBC summary styles

### Phase 2

- `src/cs_tickets/allowlist_compare.py` — five TBC-scoped bucket counters; changed-row content fields; metrics table rows
- `src/cs_tickets/portal_training.py` — `training_changed_rows_html` wraps `ticket_preview_html(mode="changed")`; `ticket_preview.js` on training shell
- `src/cs_tickets/portal_learn.py` — unchanged import path (uses `training_changed_rows_html` wrapper)
- `src/cs_tickets/static/training.js` — removed `#show-changed-details` toggle (migrated to shared preview JS)
- `src/cs_tickets/portal_app.py` — learn page loads `ticket_preview.js`

### Tests

- `tests/test_classify.py` — `portal_reason_bucket`, `attach_tiers_with_meta` parity
- `tests/test_portal_stats.py` — bucket summary counts
- `tests/test_portal.py` — classify result preview markup and script

## Verification

```bash
pytest tests/test_portal.py tests/test_portal_stats.py tests/test_classify.py tests/test_allowlist_session.py tests/test_golden_classifier.py -q
```

Full suite: `pytest -q` — all passed at implementation time.

## Not implemented (Phase 3 backlog)

- Excel `tbc_reason` column
- Click bucket in summary → filter shortcut
- Keyboard row navigation

## Known follow-ups

- Portal run still classifies export twice (`iter_master_rows_with_meta` + `try_append_portal_snapshot`); captured reasons could be reused for trends later.
- `training_changed_rows_html` kept as thin wrapper for backward compatibility; callers can migrate to `ticket_preview_html` directly.
