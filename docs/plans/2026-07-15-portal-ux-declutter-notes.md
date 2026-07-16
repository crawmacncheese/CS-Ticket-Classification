# Portal UX Declutter — Notes

**Plan:** [2026-07-15-portal-ux-declutter.md](./2026-07-15-portal-ux-declutter.md)  
**Status:** Phase A + B1 done

## Log

| Date | Phase | Notes |
|------|-------|-------|
| 2026-07-15 | — | Plan authored from live UI review (home, rules, dashboard, results/TBC/audit builders). |
| 2026-07-15 | A + B1 | Implemented results CTA hierarchy, layout parity, workbook hint → technical details, ticket preview filter merge. |
| 2026-07-16 | B3 / dock | Review chat dock on `/rules`; removed duplicate NL “Apply focus” fields where the dock already provides NL (rules, category audit, ticket preview Advanced). |

## Decisions (fill as you go)

- NL focus default home: Advanced vs Review dock only — **Review chat dock only** on pages that have the dock (rules, results, audit, TBC). Structured filters remain for precise browsing.
- Excel header `COUNTA of id` — keep vs rename — *pending* (Phase C)
- Category audit sweeps — wire vs remove — *pending* (Phase E)

## Phase A + B1 summary

### A — Results hierarchy + layout parity
- Primary CTA: **Start manual review (N)** when pending TBC; else **Download Excel Workbook**
- Removed **Run History** from `.run-actions` (remains in top nav only)
- Workbook sheets hint moved into collapsed technical details
- POST `/run` success now uses review dock + `wide=True` + same workbench scripts as GET `/results`

### B1 — Ticket preview filters
- Default bar: **Search tickets** + **Segment** + **Category**
- Removed separate Subject / Tag / Contains fields (search covers subject+body+tags)
- NL focus + Category keywords behind **More filters** (`ticket-preview-advanced`)
- JS: `ticket-preview-search-filter`; review-chat focus events write into search
- Cache bumps: `ticket_preview.js?v=14`, `cs_tickets_theme.css?v=7`

### Tests
- `tests/test_portal.py` updated for CTA, dock/wide, search filter, no subject/contains in HTML
- `pytest tests/test_portal.py tests/test_portal_ticket_preview.py tests/test_review_chat.py tests/test_portal_layout.py` → 34 passed
