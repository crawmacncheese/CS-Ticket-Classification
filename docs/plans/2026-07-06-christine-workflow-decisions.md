# Christine Workflow — Locked Decisions (2026-07-06)

> **Status:** Approved product decisions from design brainstorm (Gemini PDF parity → native portal).
>
> **Implements:** [2026-07-03-gemini-conversation-patterns.md](./2026-07-03-gemini-conversation-patterns.md), [2026-07-03-explicit-rule-authoring.md](./2026-07-03-explicit-rule-authoring.md), [Gemini-update-notes.md](./Gemini-update-notes.md).

---

## Summary

| Topic | Decision |
|-------|----------|
| **Who runs the loop** | **Model B — shared loop, gated promote.** CS analysts run TBC queue + explain + propose rules; classifier maintainers / team leads **Confirm** live. |
| **Single-ticket relabel** | **Phase 1: no.** Fix patterns via propose rule → Confirm → re-classify run. **Phase 2:** run-scoped relabel for XLSX/report only (no new rule). |
| **Weekly narrative report** | Phase C backlog — tier breakdown + TBC trends first; optional LLM summary later. |
| **Re-classify after Confirm** | Required for Christine feel — same export, updated live rules, show TBC delta. |

---

## Personas and permissions (Model B)

### CS analyst

**Runs the weekly TBC loop** (same operator role as Christine in Gemini today).

| Can | Cannot |
|-----|--------|
| Upload / `/run` categorize | **Confirm live** (write `runs/live/`) |
| Open **TBC queue** (chunks of 10) | Disable or replace rules |
| **Explain** — why TBC, top candidate | Advanced JSON edit (optional: hide until lead) |
| **Propose rule** from ticket → compile chat + preview | Claim “0 TBC” without re-run |
| **“Rest look fine”** — advance chunk without new rules | *(UI label: **Skip chunk — no rule needed**)* |

**Primary screens:** Run results → TBC queue → Explain → inline rule panel (or `/rules/new` prefill).

**Rules list:** Read-only browse + search; matched rule ids visible in explain only (not full maintainer CRUD).

### Classifier maintainer / CS team lead

**Owns production rule quality and promote gate.**

| Can | Notes |
|-----|-------|
| Everything analysts can | |
| **Confirm live** after compile + preview | Same gate as `/learn` |
| Disable / replace rules on `/rules` | Soft delete via `enabled: false` |
| Rules export | Parity with *“give me the master prompt”* |
| Re-classify run after Confirm | Show before/after TBC count |

**Phase 1 auth:** `PORTAL_ALLOW_CONFIRM=1` (or `true`/`yes`/`lead`) enables Confirm and disable on `/rules`. Unset = analyst mode (compile + preview only).

---

## TBC resolution loop (end state)

```text
1. POST /run → summary + TBC count
2. CTA: "Review N TBC tickets" → TBC queue
3. Chunk of 10: ID | quote | why TBC | suggested tier (explain engine, not LLM)
4. Per row:
     a. "Rest look fine" on chunk → next chunk (no relabel, no rule)
     b. Pattern fix → Propose rule → compile → preview → [lead] Confirm → re-classify run
5. Repeat until TBC queue empty or analyst stops
6. Category audit / download XLSX for weekly report
```

**Suggested tier column:** Top weighted candidate when score > 0; label **“candidate (not accepted)”** when `fallback_used` or below acceptance gate. Never auto-apply.

**No batch LLM classify** on `/run` or TBC queue ([prd.md](../prd.md) NG-01).

---

## Single-ticket relabel

### Phase 1 (initial) — not in scope

- No per-ticket category override store.
- Corrections that should persist → **rule + Confirm + re-classify**.
- Chunk acceptance → **“Rest look fine”** only (workflow pacing, not relabel).

**Rationale:** Matches Christine’s dominant habit (corrections become protocol updates); avoids override vs rules dual truth.

### Phase 2 (implemented) — run-scoped relabel (in-memory)

| Field | Behavior |
|-------|----------|
| **Scope** | Single `_RunRecord` in memory (one `run_id`) |
| **Effect** | Ticket’s tier columns updated for this run (TBC queue, category audit, XLSX download) |
| **Engine** | Classifier + live rules remain default; overrides apply after classify/reclassify |
| **Persistence** | Lost on portal restart; not copied to next `/run` |
| **Audit** | Stored as `record.overrides[ticket_id] = {tier, note}` (no global DB) |

**Use when:** One-off wording, hesitant category pick, weekly report fix before a pattern is confirmed.

**Explicitly not Phase 2:** Global override DB, auto-promote override → rule.

#### UX (current)

- In TBC queue review panel, analysts can click **“Classify as suggested”** (run-scoped).
- The action **does not write rules**; it only records an override and updates the run snapshot.

#### API (current)

- `POST /run/{run_id}/override/{ticket_id}` — body: `{ "tier": ["..", "..", "..", "..", ".."], "note": "..." }`
  - Validates tier is in allow-list and is not a TBC/manual-review leaf.
- `POST /run/{run_id}/override/{ticket_id}/clear` — clears override (re-classify to recompute tier).

---

## Implementation phases (ordered)

### Phase A — Core loop (Christine parity) ✅

1. **TBC queue UI** — chunk 10, Gem table columns ([explicit-rule-authoring §3.3](./2026-07-03-explicit-rule-authoring.md)) — [notes](./2026-07-06-tbc-queue-review-focus-notes.md)
2. **Re-classify run** — `POST /run/{run_id}/reclassify` with current live rules; TBC before/after
3. **Propose rule from TBC row** — inline compile panel + `/rules/new` prefill
4. **Confirm gate** — analyst vs lead UI split (Model B)

### Phase B — Session continuity (partial) ✅

5. TBC progress header (*“17 in focus · 47 total · chunk 2 of 5”*) + **review focus filters**
6. `GET /rules/export` — live JSON + metadata — **not yet**
7. Rules version hash on run metadata — **not yet**

**Also shipped (2026-07-06):** session-persistent suggestions/rules, batch compile/confirm, NL review focus, allow-list gap add from TBC — see [2026-07-06-tbc-queue-review-focus-notes.md](./2026-07-06-tbc-queue-review-focus-notes.md).

### Phase C — Analyst layer

8. Category slice CSV export from drill-down → **done** in [2026-07-07-category-audit-workflow.md](./2026-07-07-category-audit-workflow.md) Phase 5
9. Random sample N from category (category-review Phase 3)
10. Weekly summary template (counts + top complaint types; no LLM v1) → partial coverage in category audit Phase 5 (representative examples)

**Category audit:** [2026-07-07-category-audit-workflow.md](./2026-07-07-category-audit-workflow.md) — **Phases 0–5 done** ([notes](./2026-07-07-category-audit-workflow-notes.md)).

**Christine orchestration skill (new):** [2026-07-13-christine-orchestration-skill.md](./2026-07-13-christine-orchestration-skill.md) — session prefilter, metadata package, skill runner, preview overlap, promote hygiene; optional unified chat UI.

### Phase D — Rule health

11. Override tracking when lead changes category after suggestion
12. “Rules needing review” list

---

## API sketch (Phase A + review focus)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/run/{run_id}/tbc_queue?offset=0&limit=10` | Chunk rows; optional `q`, `tier1`, `categories`, `include_facets=1` |
| POST | `/run/{run_id}/tbc_parse_focus` | NL → structured filter + `rule_target` |
| POST | `/run/{run_id}/tbc_draft_rule_for_filter` | Batch rule prefill for active focus |
| POST | `/run/{run_id}/add_allowlist_tuple/{ticket_id}` | Add taxonomy-valid tuple via ticket exemplar (lead) |
| POST | `/run/{run_id}/override/{ticket_id}` | Run-scoped single-ticket category override (no rule) |
| POST | `/run/{run_id}/override/{ticket_id}/clear` | Clear a run-scoped override |
| POST | `/run/{run_id}/reclassify` | Re-run classifier on stored NDJSON; refresh rows + stats |
| POST | `/run/{run_id}/tbc_chunk/ack` | Mark chunk reviewed (“skip chunk”); respects active filter |
| POST | `/rules/confirm_batch` | Confirm multiple compiled rules (lead) |

Existing: `GET /run/{run_id}/explain/{ticket_id}`, `POST /run/{id}/suggest_category/{id}`, `/rules/compile`, `/rules/confirm`, `/rules/new?run_id=&ticket_id=`.

**Implementation detail:** [2026-07-06-tbc-queue-review-focus-notes.md](./2026-07-06-tbc-queue-review-focus-notes.md)

---

## Acceptance criteria (Phase A)

- [x] Analyst can complete TBC chunk review without Confirm access
- [x] Lead can Confirm compiled rule from analyst’s propose flow
- [x] After Confirm + reclassify, TBC count decreases for pattern-matching tickets (golden: Rosetta fixture)
- [x] “Skip chunk” advances chunk without creating rules or relabeling
- [x] Review focus filters + NL parse support Christine-style batch review ([notes](./2026-07-06-tbc-queue-review-focus-notes.md))
- [x] No single-ticket relabel UI in Phase A (initially)
- [x] Run-scoped single-ticket relabel available without changing live rules (Phase 2)

---

## Related documents

- [2026-07-03-explicit-rule-authoring.md](./2026-07-03-explicit-rule-authoring.md) — compile + Confirm implementation
- [2026-07-03-gemini-conversation-patterns.md](./2026-07-03-gemini-conversation-patterns.md) — PDF interaction patterns
- [2026-07-02-category-review-and-drill-down.md](./2026-07-02-category-review-and-drill-down.md) — audit after loop
