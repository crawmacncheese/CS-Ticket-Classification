# Category Audit Workflow — Implementation Notes

**Date:** 2026-07-07  
**Plan:** [2026-07-07-category-audit-workflow.md](./2026-07-07-category-audit-workflow.md)

## Summary

**Phase 0 complete** — classifier rule alignment (Christine June 24 session).

**Phase 1 complete** — category audit entry, slice filter, NL focus, entry points.

**Phase 2 complete** — paginated ticket cards with expandable full content, Explain + Propose rule per card.

**Phase 3 complete** — six validation sweeps, JSON API, draft rule panel, open in rules editor via sessionStorage.

**Phase 4 complete** — inline compile/preview/confirm on audit page; reclassify with `snapshot_audit`; before/after slice banner.

**Phase 5 complete** — slice CSV export, representative examples block, possible-duplicates sweep (7th sweep).

## Design decisions

| Topic | Decision |
|-------|----------|
| Phase 0 rules | Refund > cancel, Posties/ESP → B2B, account deletion, Rosetta guards, invoice |
| Slice filter | `CategoryAuditFilter`; local TBC check (no circular import with `portal_stats`) |
| Pagination | Server-side `offset` / `limit` (default 10) on audit page |
| Full content | `<details>` per ticket card; description not truncated |
| Sweeps | `audit_signals.py` + `category_audit_sweeps.py`; 6 built-in checks on active slice |
| Draft rule | `POST /category_audit/draft_rule` → textarea; compile/preview/confirm inline or sessionStorage → `/rules/new` |
| Reclassify snapshot | `POST /reclassify` body `{snapshot_audit, ...filter}` stores slice before/after; banner on `?reclassified=1` |
| Confirm gate | `portal_allow_confirm()` — analysts see lead note, no Confirm button |
| CSV export | `GET /category_audit/export.csv` — full slice with description + 5-tuple |
| Representative examples | `pick_representative_examples()` — up to 3 diverse tickets in audit header |
| Duplicate sweep | 7th sweep `possible_duplicates` — groups by requester + normalized subject |
| Explain | Lazy fetch per card (same endpoint as ticket preview) |

## Files changed

| File | Phase |
|------|-------|
| `src/cs_tickets/audit_signals.py` | 3 — **new** |
| `src/cs_tickets/category_audit_sweeps.py` | 3 — **new** |
| `src/cs_tickets/portal_category_audit.py` | 1–3 — cards, sweeps panel, pagination |
| `src/cs_tickets/static/category_audit.js` | 1–4 — sweeps, draft rule, compile/confirm/reclassify loop |
| `src/cs_tickets/static/rules.js` | 3 — sessionStorage prefill |
| `src/cs_tickets/portal_app.py` | sweeps, draft_rule, reclassify snapshot, banner |
| `src/cs_tickets/portal_copy.py` | 4 — reclassify banner + lead note copy |
| `src/cs_tickets/category_audit_duplicates.py` | 5 — **new** |
| `src/cs_tickets/category_audit_export.py` | 5 — **new** |
| `src/cs_tickets/category_audit_filters.py` | 5 — `pick_representative_examples` |
| `src/cs_tickets/category_audit_sweeps.py` | 5 — duplicate sweep |
| `tests/test_category_audit_duplicates.py` | 5 — **new** |
| `tests/test_category_audit_export.py` | 5 — **new** |

## Verification

```bash
pytest -q tests/test_category_audit_sweeps.py tests/test_category_audit_filters.py tests/test_category_audit_duplicates.py tests/test_category_audit_export.py tests/test_portal_category_audit.py tests/test_classify.py
```

## Not implemented / deferred

- Phase 5.4 — batch-over-batch tier4 count comparison (optional)
