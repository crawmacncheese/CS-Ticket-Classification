# Allowlist Training Fixes — Implementation Notes

**Plan:** `docs/plans/2026-06-08-allowlist-training-fixes.md`  
**Date:** 2026-06-08

## Summary

Fixed four Training-flow bugs: classified upload sheet resolution, B2B/B2C TBC preview split, file-format restrictions, and removal of the Step 1 workbook preview path.

## Task 1 — Classified upload sheet resolver

**Added** in `taxonomy.py`:

- `resolve_classified_upload_sheet()` — prefers `SCMP_Tickets_Master_Categorized`, then `Tickets`, then the sheet with the most ticket rows that has required tier columns
- `extract_classified_workbook_five_tuples()` and `count_classified_tickets_per_tuple()` — thin wrappers
- `_try_workbook_sheet_index()` and `_count_ticket_rows()` — helpers for single-pass resolution

**Wired** in `allowlist_training.create_session()` and `merge_tuples_into_workbook()` (source sheet only).

**Preserved:** `_load_workbook_tuples()` and `load_allowlist()` unchanged — reference workbook still requires `SCMP_Tickets_Master_Categorized`.

## Task 2 — B2B / B2C TBC split

**Extended** `AllowlistCompareResult` with `tbc_b2b_old/new` and `tbc_b2c_old/new`.

**Added** `_tbc_segment()` — buckets audit-style TBC rows by `Tier1_Segment`.

**Updated** `compare_result_html()` — separate B2B and B2C rows plus combined total.

**Preserved:** `_is_tbc()` logic unchanged; `run_metadata.count_tbc_rows()` untouched.

## Task 3 — File format restrictions

**Added** `_require_extension()` in `portal_app.py`.

| Route | Client `accept` | Server check |
|-------|-----------------|--------------|
| `/run` | `.json,.ndjson` | `_JSON_EXTENSIONS` |
| `/training/upload` | `.xlsx` | `_XLSX_EXTENSIONS` |
| `/training/preview` | `.json,.ndjson` | `_JSON_EXTENSIONS`; file required |

**Removed** Step 1 workbook checkbox, `.xlsx`/`.txt` preview paths, and `compare_allowlists_on_workbook` usage from `training_preview()`.

**Simplified** `training.js` — removed `useTrainingUpload` / `updatePreviewFileState()`.

## Tests

- `tests/test_allowlist_training.py` — sheet resolver, portal `Tickets` sheet, merge from classified source
- `tests/test_portal.py` — format rejection, preview with NDJSON, B2B/B2C labels in HTML
- `tests/test_allowlist_session.py` — B2B/B2C counter assertions on golden NDJSON

## Deviations from plan

None. All changes followed the "new functions over modifying existing ones" guidance in `CONTEXT.md`.
