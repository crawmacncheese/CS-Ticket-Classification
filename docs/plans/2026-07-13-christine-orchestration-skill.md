# Christine Orchestration Skill — Implementation Plan

> **Status:** Not started (2026-07-13). Refined 2026-07-14 (CLARIFY terminal, compile UX, promote guards).  
> **For implementer:** Document steps and design decisions in [2026-07-13-christine-orchestration-skill-notes.md](./2026-07-13-christine-orchestration-skill-notes.md).  
> **Prerequisite work:** Category audit Phases 0–5 **done** ([notes](./2026-07-07-category-audit-workflow-notes.md)); TBC queue + explicit rule authoring **done**.

**Goal:** Add a **Christine orchestration layer** that turns analyst chat into a **deterministic API execution queue**, grounded in real run data, without putting an LLM on the `/run` classification hot path. The LLM acts as **orchestrator** (intent → queue) and **compiler** (`/rules/compile` only).

**Users (Model B — unchanged):**

| Persona | Orchestration role |
|---------|-------------------|
| **CS analyst** | Trigger sessions; review sweep/profile results; compile + preview; hand off to lead |
| **Classifier maintainer / lead** | Approve Confirm; reclassify; revert bad promotes |
| **Taxonomy owner** | Own `docs/taxonomy-requirements.md`; resolve precedence conflicts |

---

## Architecture (current vs target)

### What is shipped today

| Layer | Status | Location |
|-------|--------|----------|
| Deterministic classify | ✅ | `classify.py`, `/run`, `/reclassify` |
| TBC queue + NL focus | ✅ | `portal_tbc_queue.py`, `tbc_filter_nl.py` |
| Category audit + sweeps | ✅ | `portal_category_audit.py`, `category_audit_sweeps.py` |
| Rule compile (LLM) | ✅ | `rule_compile.py`, `POST /rules/compile` |
| Rule preview (deterministic) | ✅ | `preview_rule_on_rows`, `POST /rules/preview` |
| Confirm + live promote | ✅ | `POST /rules/confirm`, `revert_latest_live_backup()` |
| Replay script (fixed demo) | ✅ | `scripts/replay_christine_workflow.py` |
| Taxonomy protocol MD | ✅ | `docs/taxonomy-requirements.md` |
| Session MD template | ✅ | `docs/sessions/_template-session-requirements.md` |

### What this plan adds

| Layer | Target |
|-------|--------|
| **Deterministic profile** | Cheap probes (counts, sample IDs) before orchestration queue is finalized |
| **Session Metadata Package** | JSON queue mapped to real portal endpoints |
| **Christine workflow skill** | Cursor `SKILL.md` + parameterized runner |
| **Taxonomy → compile injection** | Global precedence + scoped MD sections + compact live-shield id/weight table (not weights-only JSON) |
| **Preview depth** | Shadowing / overlap report on preview rows |
| **Bounded compile retry** | Mechanical retry ≤2; on failure → human clarification (no raw schema dump to analyst) |
| **Promote hygiene** | Fresh preview before Confirm; reclassify-after-Confirm (soft-fail if run gone); version-guarded revert |
| **Package review pause** | Optional analyst confirm of Session Metadata Package between prefilter and runner |
| **Unified chat UI** | Phase E — Cursor-like **side dock** beside workbench (not full-page takeover) |

### Explicit non-goals

- LLM batch categorization on `/run` ([prd.md](../prd.md) NG-01)
- Ticket database, date-range sweeps, or persistent per-ticket tagging
- Auto-Confirm without human lead
- Full autonomous agent (Model B keeps human gate)
- Replacing `rule_compile_corpus.py` — taxonomy MD **supplements** it

---

## End-to-end flow (repo-accurate)

```text
User chat (Cursor or future portal chat)
    ↓
[A] Deterministic profile     — parse_focus, sweeps, slice count (NO LLM)
    ↓
[B] Orchestration prefilter   — user intent + profile + taxonomy → Session Metadata Package
    ├─ if blockers (e.g. ZERO_MATCHES): STOP → message user; do NOT invoke runner
    └─ else: optional package review pause (analyst tweak queue / label intent)
    ↓
[C] Skill runner              — sequential API calls from package (only if queue actionable)
    ↓
[D] Compile                   — POST /rules/compile (LLM compile-only; retry ≤2)
    ├─ on exhaust: STOP → human-readable clarification ask (not raw JSON errors)
    ↓
[E] Preview + overlap         — POST /rules/preview (deterministic; enriched)
    ↓
[F] Human card                — analyst: handoff; lead: Approve / Edit / Reject
    ↓
[G] Confirm                   — POST /rules/confirm (lead only; require fresh preview on living run)
    ↓
[H] Reclassify                — POST /run/{id}/reclassify when run_id set
    ├─ on 404 / expired run: WARN + soft-fail (live promote still succeeded)
    ↓
[I] Session MD + taxonomy     — write results; promote stable edge cases upstream
```

**Critical invariant:** Steps A, C, E, H never call an LLM. Steps D and B may.

**Runner gate:** Invoke `[C]` only when `orchestration_queue` is non-empty and `blockers` contains no terminal conditions (`ZERO_MATCHES`, etc.).

---

## Session Metadata Package (schema)

Machine queue produced by prefilter (Phase B). Persist to session MD execution log.

### Top-level fields

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | string | Unique id (`sess_` + uuid) |
| `run_id` | string \| null | Active portal run |
| `run_mode` | enum | `TBC_REVIEW` \| `CATEGORY_AUDIT` \| `COMPILE_ONLY` |
| `user_persona` | enum | `ANALYST` \| `LEAD` |
| `taxonomy_version` | int | From `taxonomy-requirements.md` header |
| `profile` | object | Output of deterministic profile (Phase A) |
| `orchestration_queue` | array | Ordered steps (below); **empty** when terminal blockers present |
| `blockers` | array | Terminal: `ZERO_MATCHES`. Soft: `NEEDS_LEAD_CONFIRM`, `PREVIEW_STALE`, `COMPILE_CLARIFY` |
| `clarify_message` | string \| null | Human-readable ask when Phase B or compile stops for clarification |

### Profile object (deterministic — Phase A)

```json
{
  "focus_nl": "review B2C cancellation",
  "audit_filter": { "tier1": "B2C", "categories": ["Cancellation"] },
  "slice_count": 33,
  "tbc_count": 12,
  "sweep_summaries": [
    { "sweep_id": "rosetta_footer", "match_count": 17, "sample_ids": ["169856"] }
  ],
  "no_op": false
}
```

If `slice_count == 0` and all sweeps `match_count == 0`, set `no_op: true`, add `ZERO_MATCHES` to `blockers`, set `clarify_message`, and leave `orchestration_queue` **empty**. Do **not** put `CLARIFY` in the queue — clarification is a **terminal Phase B state**, not a runner action. Headless `run_christine_session.py` exits non-zero with the clarify message printed; Cursor skill returns control to chat.

### Queue action types (map to portal)

| Action | Endpoint | Notes |
|--------|----------|-------|
| `ATTACH_RUN` | `POST /run` | When no `run_id` |
| `PARSE_FOCUS` | `POST .../category_audit_parse_focus` or `tbc_parse_focus` | Prefer deterministic parser first |
| `EXECUTE_SWEEP` | `GET .../category_audit/sweeps` | Run-scoped only |
| `COMPILE_RULE_DRAFT` | `POST /rules/compile` | Include `rule_prefill` text + optional exemplar |
| `PREVIEW_RULE` | `POST /rules/preview` | **Always** after successful compile |
| `QUEUE_FOR_CONFIRMATION` | UI / skill pause | `auto_confirm: false` |
| `CONFIRM_RULE` | `POST /rules/confirm` | Lead only; explicit Approve; refuse if preview stale / run gone |
| `RECLASSIFY_RUN` | `POST /run/{id}/reclassify` | After Confirm when `run_id` set; soft-fail on expired run |

### Example queue (Rosetta / Cancellation)

Reference: `scripts/replay_christine_workflow.py`.

1. `PARSE_FOCUS` — `review B2C categories: 1. Cancellation`
2. `EXECUTE_SWEEP` — `rosetta_footer`
3. `COMPILE_RULE_DRAFT` — Rosetta `compile_phrase` from taxonomy MD
4. `PREVIEW_RULE` — on current `run_id`
5. `QUEUE_FOR_CONFIRMATION` — attach preview + overlap summary
6. *(human)* `CONFIRM_RULE`
7. `RECLASSIFY_RUN` — `{ snapshot_audit: true, tier1, categories }`

---

## Implementation phases

### Phase A — Deterministic profile + session artifacts

**Goal:** Ground orchestration in real run data before any orchestration LLM call.

| Task | Deliverable |
|------|-------------|
| A.1 | `scripts/session_profile.py` — given `run_id` + focus text, return profile JSON (parse_focus + sweeps + counts) |
| A.2 | `docs/sessions/README.md` — how to copy template, link taxonomy version |
| A.3 | Session MD writer helper — append execution log rows from runner |
| A.4 | Unit tests on christine fixture — profile returns expected Rosetta sweep count |

**Acceptance:** Profile on fixture run reports slice count and sweep matches without LLM.

---

### Phase B — Session Metadata Package + skill runner

**Goal:** Parameterize `replay_christine_workflow.py` into a profile-driven runner.

| Task | Deliverable |
|------|-------------|
| B.1 | `src/cs_tickets/session_metadata.py` — dataclasses + validation for package schema |
| B.2 | `scripts/run_christine_session.py` — read package JSON or build from profile + user goal; execute queue **only if actionable** |
| B.3 | `.cursor/skills/christine-workflow/SKILL.md` — orchestration instructions, stop conditions, API map |
| B.4 | Prefilter rules in SKILL — deterministic path when `parse_focus` succeeds; LLM only if ambiguous |
| B.5 | Terminal `no_op` — if `ZERO_MATCHES` (or equivalent): set `blockers` + `clarify_message`, empty queue, **do not invoke runner**; exit/print clarify text |
| B.6 | Optional **package review pause** — show proposed queue / label intent to analyst; allow edit of package before `[C]` |

**Acceptance:** One command replays Rosetta flow from package; zero-match profile exits with clarify and never calls compile; session MD updated; analyst mode stops before Confirm.

---

### Phase C — Compile-time hardening

**Goal:** Address precedence / visibility critiques without new storage.

| Task | Deliverable |
|------|-------------|
| C.1 | `taxonomy_requirements.py` — parse markdown protocol; extract **Global precedence** + sections by category / `sweep_id` |
| C.2 | Inject into `build_compile_system_prompt()`: (1) Global precedence (always, short), (2) scoped category/sweep prose + `compile_phrase`, (3) compact live-shield table (`rule_id`, weight, override). Cap token size. **Not** weights-only JSON — narrative edge cases are required for drafting matchers |
| C.3 | Post-compile validator — shield weight floors; warn if new rule id collides semantically with live shield |
| C.4 | **Preview overlap report** — extend `preview_rule_on_rows` return: `evidence_before`, `evidence_after`, `candidate_matched`, `candidate_won`, `shield_overlap` |
| C.5 | Bounded compile retry — on allow-list / empty matchers errors, retry ≤2 with error text in **compile** user blob; on exhaust: set `COMPILE_CLARIFY` + human-readable ask (tier / target / signals). Log raw errors to session MD for lead; **never** dump schema JSON to analyst chat |
| C.6 | Golden compile tests stay in CI (`test_rule_compile.py`, `test_structured_eval_golden.py`) |

**Acceptance:** Preview card shows “17 changed; 2 overlap Stefan Rule”; compile retries once on invalid tier then asks for clarification in plain language.

---

### Phase D — Promote hygiene + rollback

**Goal:** Close the “split state” gap within a session (not across DB). Respect in-memory run lifetime and Model B concurrency reality.

| Task | Deliverable |
|------|-------------|
| D.1 | Before `CONFIRM_RULE`: require a successful `PREVIEW_RULE` on a **still-living** `run_id` for this session. If run 404 / expired → set `PREVIEW_STALE`, refuse Confirm, ask lead to re-attach run and re-preview (**same** upload — do not silently switch datasets) |
| D.2 | Note: `POST /rules/confirm` today does **not** take `run_id` (promotes live only). Staleness check is a **session/runner + preview gate**, not a rewrite of Confirm body schema unless needed later |
| D.3 | Runner attempts `RECLASSIFY_RUN` after successful Confirm when `run_id` present. On 404 / expired: **WARN + soft-fail** — live rule already promoted; record in session MD; do not treat Confirm as failed |
| D.4 | Session MD records `config_version_after` from Confirm response |
| D.5 | **Version-guarded revert (v1):** before calling `POST /learn/revert`, compare session’s `config_version_after` to current live `config_version`. If equal → allow global undo via `revert_latest_live_backup()`. If another promote landed → refuse and message lead (“config moved; revert manually / contact maintainer”) |
| D.6 | Expose revert CTA on `/rules` after explicit Confirm (with version guard messaging) |
| D.7 | Document revert playbook in session template Open items |
| D.8 | **Later (P2):** targeted rule soft-delete / session-scoped revert — not required for first ship; global + version guard is enough under Model B |

**Acceptance:** Lead Confirm → reclassify (or soft-warn if run gone) → session MD shows TBC before/after when reclassify succeeded; revert only when `config_version` still matches session.

---

### Phase E — Side-panel Review chat (optional, later)

**Goal:** Cursor-style **docked chat** beside the existing workbench — not a full-page chat block that replaces or obscures audit / TBC / results.

**Layout (locked):**

```text
┌─────────────────────────────────────────────┬──────────────────┐
│  Primary workbench (unchanged)              │  Review chat     │
│  · run results / category audit / TBC       │  (side panel)    │
│  · ticket lists, sweeps, explain            │  · thread        │
│  · remains fully visible and usable         │  · rich cards    │
│                                             │  · compose       │
└─────────────────────────────────────────────┴──────────────────┘
```

| Constraint | Rule |
|------------|------|
| Placement | Right (or left) **side dock**; default ~360–420px; resizable; collapsible |
| Primary view | Category audit, TBC queue, run results stay the **main pane** |
| Not allowed | Full-viewport “chat-only” takeover of workbench pages |
| Mobile | Collapse to drawer overlay or bottom sheet; do not crush the table to unreadability |
| Entry | Toggle from run results / audit / TBC (“Review chat”); deep link may open panel with `run_id` |
| Today’s gap | `/rules/new?mode=orch` is a **dedicated chat page** — Phase E migrates that UX into a **side panel** over the workbench |

| Task | Deliverable |
|------|-------------|
| E.1 | Shared side-panel shell (CSS grid / flex) embeddable on `/run/{id}/results`, `category_audit`, `tbc` |
| E.2 | Message types: profile summary, sweep card, preview+delta card, confirm card (in panel scroll) |
| E.3 | Mode badge: Audit vs Config (compile/confirm) in panel header |
| E.4 | Analyst vs lead actions on cards (Approve hidden for analyst) |
| E.5 | Chat → session MD sync (append execution log) |
| E.6 | Collapse / expand persistence (sessionStorage); optional “pop out” to `/rules/new?mode=orch` for focus mode |

**Defer until:** Phases A–D prove flow via Cursor skill + runner.

---

## Design decisions (locked)

| Topic | Decision | Rationale |
|-------|----------|-----------|
| Orchestrator sees tickets? | **No raw tickets**; yes **profile counts/snippets** | Visibility gap fix without LLM on hot path |
| Preview before Confirm | **Always automatic** | Model B safety; Christine parity |
| Auto-Confirm | **Never** | Lead gate |
| Reclassify after Confirm | **Attempt when `run_id` set**; soft-fail if run expired | Live promote and run snapshot are separate; expired run must not undo Confirm |
| Confirm vs run staleness | Gate via **fresh preview on living run** (session/runner); Confirm API stays live-only | Matches current `POST /rules/confirm` (no `run_id`); avoid silent dataset switch |
| `CLARIFY` / `ZERO_MATCHES` | **Terminal Phase B** — empty queue, no runner | Headless runner cannot chat; clarify returns to user |
| Package review pause | **Optional** between B and C | Analyst may tweak package without inventing goals before profile |
| Eval harness in product loop | **CI required**; pre-Confirm gate **optional** for lead | Avoid blocking analysts on slow tests |
| Compile retry | **Max 2**, mechanical only; then **human clarification** | Recovery without autonomous loops; analyst is not a prompt engineer |
| Taxonomy inject | **Global precedence + scoped MD + shield weight table** | Prose/`compile_phrase` drafts matchers; weights alone under-specify |
| Historical tagging | **Reclassify run**, not DB | Matches in-memory run architecture |
| Taxonomy MD vs corpus | **Both** — MD human-editable; corpus few-shots in code | Git-friendly protocol + stable tests |
| Revert (v1) | **Global backup + `config_version` guard** | Prevents undoing a later lead’s promote; targeted soft-delete deferred |
| Revert (later) | Session / `rule_id` soft-delete | Needed if concurrent Confirm becomes common |
| Review chat layout | **Side dock beside workbench** (Cursor-like); not a full-page obstruction | Chat is conductor; tables/sweeps stay visible; “chat must not replace TBC workbench” |

---

## API quick reference (runner)

| Step | Method | Path |
|------|--------|------|
| Health | GET | `/health` |
| Upload | POST | `/run` |
| Audit focus | POST | `/run/{id}/category_audit_parse_focus` |
| TBC focus | POST | `/run/{id}/tbc_parse_focus` |
| Sweeps | GET | `/run/{id}/category_audit/sweeps` |
| Compile | POST | `/rules/compile` |
| Preview | POST | `/rules/preview` |
| Confirm | POST | `/rules/confirm` |
| Reclassify | POST | `/run/{id}/reclassify` |
| Revert live | POST | `/learn/revert` |

---

## Testing strategy

| Layer | Tests |
|-------|-------|
| Profile | `tests/test_session_profile.py` on christine fixture |
| Metadata package | Schema validation; terminal `ZERO_MATCHES` ⇒ empty queue |
| Runner | Integration: package → compile + preview (mock LLM or heuristic); skip runner when blockers terminal |
| Compile clarify | Exhausted retry yields `COMPILE_CLARIFY` + non-technical message |
| Preview overlap | `tests/test_preview_overlap.py` — Stefan vs candidate scenarios |
| Promote hygiene | Stale/expired `run_id` blocks Confirm gate; reclassify 404 soft-fails after Confirm |
| Revert guard | Revert refused when live `config_version` ≠ session `config_version_after` |
| Taxonomy parse | `tests/test_taxonomy_requirements.py` — global + scoped extract; shield table shape |
| E2E manual | `scripts/run_christine_session.py` against local portal |

---

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Orchestrator queues no-op sweeps | Phase A profile + `no_op` + terminal `ZERO_MATCHES` (no queue) |
| `CLARIFY` breaks headless runner | Clarify is Phase B terminal state, not a queue action |
| New rule shadows Stefan / shields | Phase C overlap report + shield warnings |
| Compile hallucinates tier | Allow-list validation + taxonomy inject + retry + clarification ask |
| Analyst sees raw schema errors | Orchestrator wraps failures; raw errors only in session MD |
| Stale / expired run after handoff | Fresh-preview Confirm gate; reclassify soft-fail |
| Blind global revert undoes later promote | Version-guarded revert; targeted rule revert later |
| Analyst promotes by mistake | Confirm gate unchanged; preview required |
| Bad rule live 24h later | Version-guarded `revert_latest_live_backup()` + session MD version log |
| Skill drifts from APIs | Runner is source of truth; SKILL.md references runner |
| Taxonomy context dilution | Cap inject size; always global + scoped sections, not full file |

---

## Critique resolutions (2026-07-14)

| Component | Adjustment adopted |
|-----------|-------------------|
| Skill runner / `CLARIFY` | Terminal Phase B via `blockers`; empty queue; no runner |
| Confirm / stale `run_id` | Fresh preview on living run; Confirm stays live-only; soft-fail reclassify |
| Taxonomy inject | Scoped MD prose + global precedence + compact shield table (**not** weights-only JSON) |
| Compile retry UX | Human-readable clarification after ≤2 retries |
| Revert concurrency | v1: `config_version` guard on global revert; P2: rule/session soft-delete |

---

## Related documents

| Doc | Role |
|-----|------|
| [2026-07-06-christine-workflow-decisions.md](./2026-07-06-christine-workflow-decisions.md) | Model B personas |
| [2026-07-07-category-audit-workflow.md](./2026-07-07-category-audit-workflow.md) | Audit UI (done) |
| [2026-07-03-explicit-rule-authoring.md](./2026-07-03-explicit-rule-authoring.md) | Compile + Confirm |
| [2026-07-03-gemini-conversation-patterns.md](./2026-07-03-gemini-conversation-patterns.md) | Phrasing + precedence |
| [docs/taxonomy-requirements.md](../taxonomy-requirements.md) | Stable protocol |
| [docs/sessions/_template-session-requirements.md](../sessions/_template-session-requirements.md) | Per-batch state |
| [CONTEXT.md](../../CONTEXT.md) | Domain glossary |

---

## Suggested execution order

```text
Week 1   Phase A (profile) + Phase B.1–B.2 (schema + runner gate)
Week 2   Phase B.3–B.6 (SKILL.md + terminal clarify + package pause) + Phase C.4 (preview overlap)
Week 3   Phase C.1–C.5 (taxonomy inject + clarify UX) + Phase D.1–D.7 (promote hygiene + version-guard revert)
Later    Phase D.8 (targeted revert) + Phase E (portal chat UI)
```