# Learn Preview — Beginner UX — Phase 1 Implementation Notes

**Date:** 2026-06-17  
**Plan:** [2026-06-17-learn-preview-beginner-ux.md](./2026-06-17-learn-preview-beginner-ux.md)

## Shipped (Phase 1)

| Area | Files |
|------|--------|
| Learn copy module | `src/cs_tickets/portal_learn_copy.py` |
| Collapsed preview | `src/cs_tickets/portal_learn.py` — `learn_preview_panel_html()` |
| Skip-preview confirm bar | `src/cs_tickets/portal_learn.py` — `learn_confirm_bar_html(preview_run=…)` |
| Section intros | `src/cs_tickets/portal_learn.py` — `learn_proposals_html()` |
| Styles | `src/cs_tickets/static/cs_tickets_theme.css` — `.learn-preview-details` |

## Shipped (Phase 2)

| Area | Files |
|------|--------|
| Learn wizard | `src/cs_tickets/portal_learn.py` — `learn_wizard_html()` |
| Session details collapse | `src/cs_tickets/portal_learn.py` — `learn_session_details_html()`; wired in `portal_app._learn_process_page()` |
| Results above form | `src/cs_tickets/portal_learn.py` — `learn_preview_panel_html()` reorder |
| Wizard on all Learn pages | `portal_app.py` — index, process, confirm success, error |
| Styles | `cs_tickets_theme.css` — `.wizard-step--optional`, `.session-details`, `.learn-wizard` |

## Shipped (Phase 3)

| Area | Files |
|------|--------|
| Verdict next steps + plain stat labels | `portal_training.py` — optional params on `training_verdict_banner_html()` |
| Golden baseline hint | `portal_learn.py` — `_golden_baseline_hint_html()` |
| Stale warning on confirm bar | `learn_confirm_bar_html(preview_stale=…)` |
| Confirm dialog + risky gate | `training.js` v5 — `#learn-confirm-btn` |

## Behaviour

- Preview summary reads **“Preview: see how this affects real tickets”** (not “Optional”).
- Preview upload form lives inside `<details class="learn-preview-details">`, collapsed by default.
- After a successful preview (`batch_result` present), `<details>` renders with `open` so analysts can re-run or adjust options.
- Preview **results** (verdict banner, changed tickets) render **above** the collapsible upload form.
- Four-step wizard: Upload → Review → Check impact (optional) → Confirm. Step 2 active on process page; step 4 active after preview; all steps done on confirm success (`active_step=5`).
- Step 3 uses dashed `wizard-step--optional` styling until preview has run; links to `#learn-preview-details` from process page.
- Upload id and row-count metadata collapsed under **Session details**.
- Confirm bar always shows `PREVIEW_SKIP_NOTE`; `PREVIEW_FIRST_TIME_NUDGE` hidden once preview has run this session.
- Rules and taxonomy tables use `section-intro` paragraphs from Learn copy (not Training / `doc/` wording).
- Impact badges and deselect helpers still import from `portal_training_copy.py` (shared machinery).
- Verdict banner includes **next-step** copy per band; Learn uses plain-language outcome stats.
- Preview metrics table shown inline (not collapsed); golden baseline hint when fixture exists.
- Stale preview warning on confirm bar; Confirm prompts with rule/taxonomy counts (`risky` needs extra OK).

## Design decisions

- Replaced outer `<h2>` preview heading with `<summary>` text (“Preview: …”) to avoid duplicate titles when collapsed.
- Preview results appear above the `<details>` block so verdict is visible without scrolling past the form.
- `active_step=5` on confirm success marks all four steps done (same pattern as Training).
- `CANCEL_LABEL` duplicated in `portal_learn_copy.py` so Learn does not depend on Training copy for confirm bar strings.

## Tests

```bash
pytest tests/test_portal_learn_html.py tests/test_portal_learn.py -q
```

## Next (Phase 2b)

- “Use last classify export” button
- Auto-expand preview for large selections

## Shipped (Phase 4)

| Area | Files |
|------|--------|
| Collapsible tables | `portal_learn.py` — `_learn_collapsible_section_html()` for rules, taxonomy, metrics, changed tickets |
| Preview file guidance | `_learn_preview_file_guidance_html()` + checklist linking to `/` |
| No-op hints | `PREVIEW_NO_OP_HINT`, `PREVIEW_NO_OP_RULES_NEEDED_HINT` when `rules_needed` without no-op data |
| TBC footnote | `learn_process_body_html()` |

## Behaviour (Phase 4)

- All data tables use `<details class="learn-table-collapse" open>` — expanded by default, user can collapse.
- Preview upload shows labeled file input, 3-step checklist, and link to Categorize tickets.
- TBC footnote appears above preview section on process page.
