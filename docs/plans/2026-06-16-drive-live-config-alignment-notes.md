# Drive Live Config Alignment — Implementation Notes

**Date:** 2026-06-16  
**Plan:** [2026-06-16-drive-live-config-alignment.md](./2026-06-16-drive-live-config-alignment.md)

## What was done

### `drive_live_config.py`

- Added `WORKBOOK_FILE` to `_LIVE_FILES` so granular 5-tuple merges survive K8s `emptyDir` pod restarts.
- Added `live_file_mime()` helper; backup/proposal directory uploads use it for xlsx/json/csv.
- Sync contract is now **4 files**: `Taxonomy.csv`, `classifier_rules.json`, `config_version.json`, `CS_ticket_new_categorizations.xlsx`.

### `runtime_config.py`

- `_seed_path()` checks `references/` before `doc/` (prod bootstrap order).
- `refresh_live_from_drive()` exists, but portal classification relies on `ensure_live_bootstrapped()` which syncs from Drive when enabled.
- `load_runtime_allowlist()`: prefers `runs/live/` artifacts, but falls back to `doc/` workbook if the live workbook is missing (matches prod behavior and keeps local dev usable).

### `portal_app.py`

- `_sync_runtime_classifier()` relies on `ensure_live_bootstrapped()` (which syncs from Drive when enabled) and then reloads active rule specs.
- Removed legacy `/training` POST routes (`upload`, `preview`, `commit`, `cancel`, `revert`).
- Kept `GET /training` → 307 `/learn`.
- Updated empty allow-list warning to mention `runs/live/` and Drive env vars.

### Tests

- New `tests/test_drive_live_config.py` — folder id, upload (4 files), download, env gate.
- Extended `tests/test_runtime_config.py` — references bootstrap, `refresh_live_from_drive`.
- Trimmed obsolete `/training` POST tests from `tests/test_portal.py`.
- Added prod snapshot tests: `tests/test_feedback_promote.py` (required `confirm_learn_proposals` compatibility wrapper).

### Docs / layout

- `references/README.md` — explains bootstrap seed role vs Drive runtime truth.
- Plan doc: `docs/plans/2026-06-16-drive-live-config-alignment.md`.

## Design decisions

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | Workbook on Drive | Hybrid `granular_new` writes live workbook; emptyDir wipes it without sync |
| 2 | Drive-on prefers live artifacts | Avoids stale `doc/` shadowing; doc fallback only when live workbook is missing |
| 3 | Drive sync happens via `ensure_live_bootstrapped()` | Two replicas share Drive; pod B picks up pod A's Confirm without restart |
| 4 | Keep `doc/training_rules.json` bootstrap merge | One-time local seed only; not a runtime overlay after live dir exists |

## Local dev vs GKE

| | Local (default) | GKE / Drive on |
|---|-----------------|----------------|
| Bootstrap | `references/` → `doc/` → defaults | Same, then Drive overlay |
| Confirm writes | `runs/live/` | `runs/live/` + Drive upload |
| Classify reads | `runs/live/` (+ doc workbook fallback) | `runs/live/` (+ doc workbook fallback if live workbook missing) |

## Exit criteria

- [x] Workbook in Drive sync
- [x] references/ bootstrap
- [x] Drive sync behavior matches prod pattern
- [x] `/training` POST routes removed
- [x] Tests added/updated
- [x] pytest green (verify below)

**Result:** 221 pytest tests pass.

## Next (prod reconciliation)

- Prod reconciliation completed:
  - Copied `portal_docs.py`, `resolve_live_folder.py`, `docs/prd-phase2-learning-feedback.md`
  - Copied `Dockerfile` and `k8s/*/deploy/*.yaml` + `k8s/sa.yaml` from prod
  - Copied `tests/test_feedback_promote.py` and added `confirm_learn_proposals` wrapper in `feedback/promote.py`
- Remaining: manual GKE checklist (Confirm → Drive → second pod classify), then create a commit/PR if desired.
