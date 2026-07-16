# Session: [BATCH NAME] — [YYYY-MM-DD]

> **Role:** Per-batch review state. Link stable rules to `docs/taxonomy-requirements.md`.
> **Skill:** Read at session start; update after each major step.

**run_id:** (fill after `POST /run`)  
**portal_base:** http://127.0.0.1:8777  
**export_file:** (path or filename)  
**persona:** analyst | lead  
**loop:** tbc_queue | category_audit  
**taxonomy_version:** 1 (from taxonomy-requirements.md `protocol_version`)

---

## Goals

What the analyst wants from this session (one short paragraph).

Example: Review B2C Cancellation and Refund for the June 24 batch; fix Rosetta mislabels and Posties routed to B2C.

---

## Scope

- **segment:** B2C
- **categories:** Cancellation, Refund
- **focus_nl:** review B2C categories: 1. Cancellation 2. Refund
- **include_tbc:** false (category audit default)

---

## Corrections (this session only)

New observations not yet in taxonomy-requirements.md. After Confirm, promote stable ones upstream.

| ID | Observation | Target | Status |
|----|-------------|--------|--------|
| 1 | Rosetta footer in Cancellation slice | System Report | drafted |

---

## Rule drafts (ready for compile)

Natural-language messages for `POST /rules/compile`, in Christine phrasing.

1. (paste draft here)

---

## Execution log

| Step | Action | Result |
|------|--------|--------|
| 1 | Upload export | run_id = … |
| 2 | Parse focus | … |
| 3 | Sweeps | rosetta_footer: N matches |

---

## Results

- **TBC before / after:** — / —
- **Slice counts:** Cancellation N → M (after reclassify)
- **Rules compiled:** (ids)
- **Rules confirmed:** (ids, lead only)

---

## Open items

- [ ] Lead Confirm for rule X
- [ ] Add edge case to taxonomy-requirements.md
- [ ] Continue to UI/UX Enquiry category
- [ ] **Revert:** only if live `config_version` still equals this session's `config_version_after` after Confirm; else escalate (another promote may have landed)
