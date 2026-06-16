# Hybrid Allowlist Update — Phase 1 Implementation Notes

**Date:** 2026-06-12  
**Plan:** [2026-06-12-hybrid-allowlist-update.md](./2026-06-12-hybrid-allowlist-update.md)

## What was done

### New modules

- `live_config.py` — artifact names + `config_version.json` read/write (no `feedback/` dependency yet).
- `runtime_config.py` — `ensure_live_bootstrapped()`, `load_runtime_allowlist()`, `load_runtime_rule_specs()`, cache invalidation.
- `drive_live_config.py` — Drive sync helpers for `runs/live/` (ported from production; **currently deferred in plan**).

### Extended modules

- `drive_upload.py` — added `build_drive_service`, `find_child_file`, `upload_or_update_bytes`, etc. for live config sync.
- `classifier_rules.py` — added `set_active_rule_specs()` for portal runtime override.
- `portal_app.py` — `/run` uses `load_runtime_allowlist()` + `load_runtime_rule_specs()` via `_sync_runtime_classifier()`.
- `cli.py` — default paths use runtime config when `--taxonomy` / `--workbook` not passed.

### Bootstrap behavior

On first access, `runs/live/` is created and seeded from:

| File | Source |
|------|--------|
| `Taxonomy.csv` | `doc/Taxonomy.csv` |
| `CS_ticket_new_categorizations.xlsx` | `doc/CS_ticket_new_categorizations.xlsx` |
| `classifier_rules.json` | package core + `doc/training_rules.json` merged |
| `config_version.json` | version `1`, proposal_id `bootstrap` |

Drive sync was implemented as part of the port, but the plan is now to **defer using it** until later.

### Training unchanged

`/training` still reads/writes `doc/` directly. After a Training commit, delete `runs/live/` locally to re-bootstrap, until Phase 2 writes live config on Confirm.

### Tests

`tests/test_runtime_config.py` — bootstrap parity, idempotency, rule cache, Drive disabled by default.

All **171** pytest tests pass.

## Exit criteria (Phase 1)

- [x] Port `runtime_config.py`, `drive_live_config.py`
- [x] Portal classify uses `load_runtime_allowlist` + `load_runtime_rule_specs`
- [x] CLI uses runtime config by default
- [x] `test_runtime_config.py`
- [x] README notes for `runs/live/` (Drive sync deferred)

## Next (Phase 2)

Implement `confirm_hybrid_proposals()` with novelty routing (CSV vs workbook) and post-merge allow-list validation.

---

## Phase 2 — Hybrid promote router (2026-06-12)

### New modules

- `feedback/models.py` — `RuleProposal`, `TaxonomyProposal`
- `feedback/promote.py` — `confirm_hybrid_proposals()`, CSV/rules merge, backup/restore, post-merge validation

### Extended modules

- `taxonomy.py` — `novelty_type_for_tuple()`, `split_taxonomy_proposals()`, `TIER1_NOVELTY`

### Hybrid confirm behavior

| Novelty | Write target |
|---------|--------------|
| `tier4_new`, `tier3_new`, `tier1_new` | `runs/live/Taxonomy.csv` |
| `granular_new` | `runs/live/CS_ticket_new_categorizations.xlsx` (exemplar row) |
| `path_new` | CSV + workbook when granular ≠ `N/A` |

After merges: validate every accepted 5-tuple is in recomputed `load_allowlist()`; on failure restore `backup/{version}/`.

Rule fallback: `generate_rule_from_exemplar()` for accepted tuples still lacking rule targets.

### Tests

`tests/test_allowlist_promote.py` — granular, tier4, combined confirm, validation rollback, split routing.

All **180** pytest tests pass.

## Exit criteria (Phase 2)

- [x] Port `feedback/promote.py`, extend with workbook merge branch
- [x] Novelty split + post-merge validation in `confirm_hybrid_proposals()`
- [x] `novelty_type_for_tuple` in `taxonomy.py`
- [x] Unit tests for granular, tier4, both, validation failure

## Next (Phase 3)

Port Learn UI (`/learn` routes) and wire Confirm to `confirm_hybrid_proposals()` (no Drive sync yet).

---

## Phase 3 — Learn UI (2026-06-15)

### New modules (ported from production)

- `feedback/ids.py`, `feedback/parse.py`, `feedback/mine_rules.py`, `feedback/mine_taxonomy.py`
- `portal_learn.py` — CS proposal tables, confirm success, revert footer

### Portal routes

| Route | Behavior |
|-------|----------|
| `GET /learn` | Upload form + optional revert |
| `POST /learn/process` | Parse workbook, mine proposals, show tables |
| `POST /learn/confirm` | `confirm_hybrid_proposals()` → `_sync_runtime_classifier()` |
| `POST /learn/revert` | `revert_latest_live_backup()` |
| `GET /training` | 307 redirect to `/learn` |

Upload workbook kept in temp dir until confirm (required for granular workbook merge).

### Promote fixes (review amendments)

- Recompute `novelty_type` at Confirm from live allow-list
- `tier4_new` + granular ≠ `N/A` → CSV + workbook
- `_validate_rule_targets()` — block rules for tuples not in allow-list ∪ accepted taxonomy

### Tests

`test_portal_learn.py`, `test_feedback_mine.py`, `test_feedback_parse.py`, `test_portal_learn_html.py` — **207** pytest tests pass.

## Exit criteria (Phase 3)

- [x] `/learn` process + confirm + revert
- [x] Confirm writes `runs/live/` only
- [x] Next `/run` sees new config after confirm

## Next (Phase 4)

NDJSON impact preview via `build_candidate_live_config()` + `POST /learn/preview`.

---

## Phase 4 — Learn preview (2026-06-15)

### Backend

- `build_candidate_live_config()` + `release_candidate_live_config()` in `feedback/promote.py`
- Shared `_prepare_accepted_selection()` and `_apply_hybrid_merges_to_dir()` used by Confirm and preview
- `rule_proposal_to_spec()` helper

### Portal

- `POST /learn/preview` — NDJSON + selected `rule_ids` / `tax_ids`
- `learn_preview_panel_html()` — collapsed `<details>` with verdict banner + changed tickets
- JS mirrors checkbox selection from confirm form into preview POST

### Tests

209 pytest tests pass (`test_build_candidate_live_config_matches_confirm_granular`, `test_learn_preview_ndjson`).

## Exit criteria (Phase 4)

- [x] Preview uses hybrid candidate config (CSV + workbook + rules), not doc/-only
- [x] Metrics engine matches Training (`run_commit_simulation`)
- [x] Rules-only preview works (allow-list unchanged)

## Next (Phase 5)

Migration cleanup: remove legacy `/training` POST routes, migrate `doc/training_rules.json` overlay.
