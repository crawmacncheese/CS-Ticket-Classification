---
name: christine-workflow
description: >-
  Thin Christine session orchestrator: intake fields, route to atomic skills
  (profile-run, propose-rule, preview-rule, confirm-rule, …), stop for human
  Confirm. Use for Christine workflow, Rosetta demo, category-audit orchestration,
  or Review chat sessions — not for raw classify / scoring engine changes.
---

# Christine Workflow (thin orchestrator)

**Architecture:** [docs/architecture/agent-skills-framework.md](../../../docs/architecture/agent-skills-framework.md)  
**Plan / migration:** [2026-07-15-atomic-skills-architecture.md](../../../docs/plans/2026-07-15-atomic-skills-architecture.md)  
**You route.** Atomic skills own capability detail. You do **not** invent counts or promote live rules.

| Layer | Who |
|-------|-----|
| Orchestrator | This skill |
| Skills | `profile-run`, `propose-rule`, `preview-rule`, `explain-ticket`, `filter-tickets`, `confirm-rule` |
| Core | Portal APIs + deterministic classify (no LLM on `/run`) |

## Constraints

- No Auto-Confirm. No LLM batch categorization on `/run`.
- `ZERO_MATCHES` → clarify; do not compile.
- ANALYST cannot Confirm — hand off to LEAD.
- Prefer taxonomy `compile_phrase` when a sweep is in scope (`rosetta_footer` → portal `rosetta_system_email`).

## Intake (required before work)

Ask until filled (or user says `--demo rosetta`):

| Field | Question | Required |
|-------|----------|----------|
| `run_id_or_export` | Existing `run_id`, NDJSON path, or Christine demo? | yes |
| `focus_nl` | What to review? e.g. `review B2C` | yes |
| `persona` | `ANALYST` or `LEAD`? Default ANALYST | no |
| `goal` | `PROFILE_ONLY` / `DRAFT_RULE` / `CONFIRM_RULE` | yes |
| `rule_prefill_or_sweep` | Compile phrase or sweep id? | no |

## Route table

| Goal / utterance | Invoke skill |
|------------------|--------------|
| Profile / review focus / sweeps (`review B2C`) | [profile-run](../profile-run/SKILL.md) |
| Show / list / review **TBC** / manual review | Open `/run/{id}/tbc` (Review chat handoff) — do **not** compile |
| Draft / map / compile phrase | [propose-rule](../propose-rule/SKILL.md) then [preview-rule](../preview-rule/SKILL.md) |
| Why this ticket? | [explain-ticket](../explain-ticket/SKILL.md) |
| NL filter only | [filter-tickets](../filter-tickets/SKILL.md) |
| Unclear NL | Clarify options — **never** invent a rule |
| Explicit Confirm (LEAD) | [confirm-rule](../confirm-rule/SKILL.md) after fresh preview |

**Batch playlist (CLI):** `python scripts/run_christine_session.py --demo rosetta --persona ANALYST`  
**Portal:** Results → **Review chat** → `/rules/new?mode=orch`

## Stop conditions

| Condition | Action |
|-----------|--------|
| Intake incomplete | Ask; stop |
| `ZERO_MATCHES` / `no_op` | Clarify; no propose |
| ANALYST + Confirm | Refuse Confirm; hand off |
| Preview run expired | `PREVIEW_STALE`; re-attach same upload |
| Auto-Confirm request | Refuse |

## Package / runner reference

Full queue API detail: [reference.md](reference.md)  
Legacy plan: [2026-07-13-christine-orchestration-skill.md](../../../docs/plans/2026-07-13-christine-orchestration-skill.md)
