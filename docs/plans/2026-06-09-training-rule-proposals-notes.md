# Training Rule Proposals — Implementation Notes

**Date:** 2026-06-09  
**Plan:** [2026-06-09-training-rule-proposals.md](./2026-06-09-training-rule-proposals.md)

## Summary

Implemented Phase 2a–2c of the training rule proposals plan (Phase 3 exemplar fallback deferred). Training Commit now writes exemplar rows **and** upserted entries in `doc/training_rules.json`. Preview simulates candidate allow-list **and** in-memory generated rules via `rule_specs_new`.

## Key design decisions

### Classifier rule injection

- Added `rule_specs: tuple[RuleSpec, ...] | None = None` to `classify_row_with_explanation` / `_score_tiers`.
- Preview passes `rule_specs_new=build_candidate_rule_set(...)` — no temp file or cache clear for preview.

### Repo paths

- `repo_paths.resolve_repo_root()` shared by portal and `load_rule_specs()` for `doc/training_rules.json`.
- Training commit/snapshot/revert use `session.repo_root / doc/training_rules.json` (not global cwd).

### Coverage APIs

- `tuple_rule_coverage()` — audit only (allow-list membership).
- `training_routing_badge()` — Step 2 checklist (rule-target check only).
- `scored_targets_from_source()` moved to `rule_coverage.py`; audit tool imports shared helper.

### Rule generator fixes during implementation

- Do **not** set `any_url` when tags/subject are primary signals — NDJSON rows often lack `url`.
- Only add URL path fragments to `any_blob` when they appear in exemplar text, not only in the `url` field.

### Commit atomicity

- Snapshot before write; `upsert_training_rules` failure calls `revert_snapshot`.
- Rules generated only for tuples with resolved exemplar rows.

## Files added

| File | Role |
|------|------|
| `src/cs_tickets/repo_paths.py` | `resolve_repo_root()`, `training_rules_path()` |
| `src/cs_tickets/rule_coverage.py` | Coverage audit + training badges + AST scrape |
| `src/cs_tickets/rule_generator.py` | Exemplar → `RuleSpec`, atomic upsert |
| `tests/test_rule_coverage.py` | Coverage module tests |
| `tests/test_rule_generator.py` | Generator tests |
| `tests/test_classifier_rules.py` | Training rules loader + reload |
| `tests/test_golden_classifier.py` | Golden baseline + probe tests |
| `tests/fixtures/golden_export.ndjson` | Copy of `five_tickets.ndjson` (baseline TBC=2, zero_candidate=2) |
| `tests/fixtures/golden_baseline.json` | Upper-bound regression snapshot |

## Files modified

- `classifier_rules.py` — `RuleSpec` metadata fields, merge training rules, `reload_rule_specs()`
- `classify.py` — `rule_specs` kwarg, `tbc_reason()`
- `allowlist_training.py` — `CommitResult`, rule generation on commit, snapshot/revert for rules
- `allowlist_compare.py` — `rule_specs_old/new`, margin-loss / below-threshold metrics
- `portal_training.py` — coverage badges, updated copy
- `portal_app.py` — preview rules, commit message, `resolve_repo_root`
- `taxonomy.py` — `resolve_exemplars_for_tuples()`
- `tools/audit_classifier.py` — TBC buckets, margin-loss pairs
- `docs/design.md`, `README.md`

## Test results

- **99 passed** (full suite)
- **1 pre-existing failure:** `test_system_payment_report_classifies_system_report` (expects `Invoices and PO request`, classifier returns `System Report` — unchanged by this work)

## Follow-ups (out of scope)

- Phase 3 exemplar similarity fallback
- Taxonomy.csv auto-sync on commit
- Promote strong training rules to `classifier_rules.json` manually after review
