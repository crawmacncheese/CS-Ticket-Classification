# Portal UX Improvement — Phase 1 Implementation Notes

**Date:** 2026-06-10  
**Plan:** [2026-06-10-portal-ux-improvement.md](./2026-06-10-portal-ux-improvement.md)  
**Scope:** Phase 1 (Classify flow UX) only.

---

## Shipped

| Task | Files |
|------|--------|
| TBC summary card | `portal_stats.py` — `classify_run_counts`, `classify_run_summary_html` |
| Download CTA | `portal_app.py` — primary button top + after category breakdown |
| Upload loading | `static/classify.js`, index form `data-loading-form` |
| Plain-language copy | `portal_copy.py`, `portal_app.py` index + result pages |
| Collapsed technical docs | `<details>` on index and result pages |

## Behaviour

- **Manual review (TBC)** count uses audit-style rule: `Tier4_Type` contains `tbc` (case-insensitive).
- Technical warnings line appears only when `warns > 0`.
- Training link on index: **Update reference categories** (Training routes unchanged — Phase 2).

## Tests

```bash
pytest tests/test_portal.py tests/test_portal_stats.py -q
pytest -q
```

## Phase 2 (Training)

Shipped separately — see [2026-06-10-training-ux-wizard-and-impact-preview-notes.md](./2026-06-10-training-ux-wizard-and-impact-preview-notes.md) for wizard, verdict banner, plain-language copy, and the preview performance / optional no-op follow-up.
