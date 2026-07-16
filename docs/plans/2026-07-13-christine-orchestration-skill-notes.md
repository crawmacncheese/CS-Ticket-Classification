# Christine Orchestration Skill — Implementation Notes

**Date:** 2026-07-13 (plan refinements recorded 2026-07-14; Phase E UI 2026-07-14)  
**Plan:** [2026-07-13-christine-orchestration-skill.md](./2026-07-13-christine-orchestration-skill.md)

## Summary

Phases **A–E** (first ship) complete. Review chat is embedded as a **Cursor-style side dock** on run results, category audit, TBC queue, and **Routing Rules** (`/rules`); `GET /run/{id}/review_chat` still pops out to `/rules/new?mode=orch`. On `/rules` with no bound run, Pop out goes to `/rules/new`.

- **Phase A:** session profile + session MD writer.
- **Phase B:** Session Metadata Package + runner + Cursor skill (terminal clarify, optional package pause).
- **Phase C:** taxonomy inject into compile, post-compile shield warnings, preview overlap, bounded retry + human clarify UX.
- **Phase D:** Confirm freshness gate, reclassify soft-fail, `config_version_after` in session MD, version-guarded revert CTA on `/rules` + `/learn`.
- **Phase E:** Side-panel Review chat on workbench pages (collapse + Pop out); profile/sweep cards via existing `rules.js`.
- **2026-07-16:** Same Review chat dock on `/rules` list (optional run context / last-run from sessionStorage); profile focus filters the rules table.

## Design decisions

| Topic | Decision |
|-------|----------|
| `CLARIFY` / `ZERO_MATCHES` | Terminal Phase B — empty queue; runner not invoked |
| Compile failure after retry | Human-readable `clarify_message`; raw errors in API/session MD |
| Confirm vs stale run | Fresh preview on living run; Confirm API stays live-only |
| Reclassify 404 | Soft-fail after successful Confirm |
| Taxonomy inject | Global precedence + scoped MD + shield weight table (not weights-only JSON) |
| Revert v1 | Global backup + `config_version` / `expected_version` match guard |
| Revert later | Targeted rule / session soft-delete (P2) |
| Package review | Optional pause between B and C |
| Sweep id alias | Taxonomy `rosetta_footer` → portal `rosetta_system_email` |
| Analyst mode | Queue ends at `QUEUE_FOR_CONFIRMATION`; no Confirm |
| Empty `rule_specs=()` | Intentional sandbox (do not fall back to packaged rules) |
| Preview rows | Include match-only rows (tier unchanged), not only tier deltas |
| Portal chat UI | **Side dock beside workbench**; full-page `/rules/new?mode=orch` remains Pop out |

## Files changed (Phase E side dock)

| File | Role |
|------|------|
| `src/cs_tickets/portal_review_dock.py` | Wrap workbench + dock chrome |
| `src/cs_tickets/portal_layout.py` | `wide=` main class; CSS cache bump |
| `src/cs_tickets/portal_app.py` | Dock on results / audit / TBC |
| `src/cs_tickets/portal_rules.py` | `dock=True` compact editor |
| `src/cs_tickets/portal_category_audit.py` | Dock open CTA |
| `src/cs_tickets/static/review_dock.js` | Collapse / expand persistence |
| `src/cs_tickets/static/cs_tickets_theme.css` | Dock layout |
| `tests/test_review_chat.py` | Assert dock markup |

## Verification

```bash
python -m pytest tests/test_review_chat.py tests/test_portal_category_audit.py -v
# Portal: upload fixture → Results (chat on right) → Hide / Review chat FAB → Pop out
```

## Deferred / not implemented

- Phase D.8 — targeted rule soft-delete / session-scoped revert
- Formal package-review / package JSON editor in the portal (B.6)
- Full TOD intake form inside the portal (skill still handles Cursor-side intake)
- Phase E.6 resize handle for dock width
