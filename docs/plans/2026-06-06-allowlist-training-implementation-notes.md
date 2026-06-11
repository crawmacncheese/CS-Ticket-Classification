# Allowlist Training — Implementation Notes

Implemented Phase 1 per [2026-06-06-allowlist-training-feature.md](./2026-06-06-allowlist-training-feature.md).

## What was built

### Task 1 — `taxonomy.py` helpers

Added complete-tuple filtering and workbook merge utilities:

- `_is_complete_five_tuple`, `iter_workbook_master_rows`, `extract_workbook_five_tuples`, `count_tickets_per_tuple`, `diff_against_allowlist`, `merge_tuples_into_workbook`

**Design deviation:** Row skip logic uses the **`id`** column (when present) instead of only `url` (column 0). Synthetic/test rows and merged exemplar rows often have an empty `url`; skipping on `row[0] is None` dropped them from tuple extraction. Updated both `iter_workbook_master_rows` and `_load_workbook_tuples` for consistency.

### Task 2 — `allowlist_training.py`

Session lifecycle, snapshot/revert under `doc/.snapshots/` (max 5 retained), candidate allow-list via temp workbook copy.

### Task 3 — `allowlist_compare.py`

`compare_allowlists_on_ndjson` with audit-style TBC detection (`fallback_used` or `"tbc" in tier[3].lower()`), zero-candidate counts, and HTML summary fragment.

### Task 4 — Portal

Routes: `GET /training`, `POST /training/upload|preview|commit|cancel|revert`. UI helpers in `portal_training.py`; select-all/none in `static/training.js`. Training link on index when `training_available()` passes (`os.access` on `doc/` and reference workbook).

### Task 5 — Docs

- `.gitignore`: `doc/.snapshots/`
- `README.md`: Training section (local-only, git vs disk commit, revert scope)

## Tests

- `tests/test_allowlist_training.py` — tuple extract/diff/merge
- `tests/test_allowlist_session.py` — NDJSON compare, commit/revert round-trip
- `tests/test_portal.py` — training gating and index link

All 67 tests pass (`pytest -q`).

## Phase 2 deferred (unchanged)

Taxonomy.csv auto-sync, granular-variant badge, golden NDJSON CI baseline, hosted Training on writable deploy paths.

## Manual verification

1. `uvicorn cs_tickets.portal_app:app --reload --port 8777`
2. Open `/` — confirm **Training** link when `doc/` is writable
3. Upload classified `.xlsx` with new 5-tuples → checklist with ticket counts
4. Optional NDJSON preview → TBC old/new table
5. Commit → `git diff doc/CS_ticket_new_categorizations.xlsx`
6. **Undo last update** → workbook restored from snapshot
