# Category Review & Drill-Down — Implementation Notes

**Date:** 2026-07-02  
**Plan:** [2026-07-02-category-review-and-drill-down.md](./2026-07-02-category-review-and-drill-down.md) (Phases 1–2 complete; plan amended 2026-07-03)

## Summary

Implemented **Phase 1** (category filter + tier-breakdown drill-down) and **Phase 2** (on-demand classification explanation). Phase 3 polish items deferred.

## Design decisions

| Topic | Decision |
|-------|----------|
| Category index | Full 5-tuple keys in `category_index()`; dropdown disambiguates duplicate tier4 labels with path prefix |
| Filter scope | Client-side; category filter uses full-export `category_rows` (like `tbc_rows`); default table still capped at 200 |
| Tier breakdown click | Sets category `<select>` by tier4, scrolls to `#ticket-preview`, highlights active row |
| Explain endpoint | `GET /run/{run_id}/explain/{ticket_id}?format=json` re-runs `classify_row_with_explanation` with current rules |
| Explain storage | None — lazy fetch only; Excel contract unchanged |

## Files changed

### Phase 1

- `src/cs_tickets/portal_stats.py` — `category_index()`, clickable `tier_stats_table_html()` rows with `data-tier*` attrs
- `src/cs_tickets/portal_copy.py` — category/subject/tag filter labels and meta copy
- `src/cs_tickets/portal_ticket_preview.py` — filter controls, extended JSON (`categories`, `tier4`, `tags_list`), `run_id` on root
- `src/cs_tickets/static/ticket_preview.js` — unified filter pipeline, tier-breakdown drill-down handler
- `src/cs_tickets/static/cs_tickets_theme.css` — filter + selectable tier row + explain panel styles
- `src/cs_tickets/portal_app.py` — wire `category_index`, `#ticket-preview` anchor, `data-run-id`

### Phase 2

- `src/cs_tickets/portal_explain.py` — **new** `explain_ticket_payload()` helper
- `src/cs_tickets/portal_app.py` — explain route; detail pane button in JS
- `src/cs_tickets/static/ticket_preview.js` — fetch + render classification details

### Tests

- `tests/test_portal_stats.py` — `category_index`, selectable tier rows
- `tests/test_portal.py` — filter controls, `data-run-id`, explain endpoint parity

## Verification

```bash
pytest -q
```

Full suite: 242 passed at implementation time.

## Not implemented (Phase 3 backlog)

- Full 5-tuple category match toggle
- `created_at` date range filter
- Random sample button
- Training/Learn preview category filter on `new_tier4`
- Deep link `?category=…` on result URL

## Open questions resolved

| # | Resolution |
|---|------------|
| 1 | Tier4 default in dropdown/filter; full path disambiguation in option labels only |
| 2 | Requester email deferred |
| 3 | Explain uses current `classifier_rules.json` / live config |
| 4 | Preview cap stays 200; meta line shows in-run vs in-slice counts |
