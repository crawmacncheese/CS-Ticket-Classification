---
name: confirm-rule
description: >-
  Lead-only promote of a validated RuleSpec to live config after a fresh
  preview. Soft-fail reclassify if run expired. Use only when persona is LEAD
  and the user explicitly Approves Confirm — never auto-Confirm.
---

# confirm-rule

**skill_version:** 1  
**Write:** yes — live rules only via this path  

## Preconditions

1. Persona **LEAD** (`PORTAL_ALLOW_CONFIRM` / explicit user Approve).
2. Successful [preview-rule](../preview-rule/SKILL.md) on a **living** `run_id` this session.
3. User explicitly asked to Confirm (orchestrator must not auto-fire).

## I/O

**Input**

| Field | Type | Required |
|-------|------|----------|
| `rule` | RuleSpec JSON | yes |
| `run_id` | string | recommended (reclassify) |

**Output** (`POST /rules/confirm`)

| Field | Notes |
|-------|------|
| `ok` | promote success |
| `config_version_after` | for session MD + revert guard |

Then optionally:

```http
POST /run/{run_id}/reclassify
```

404 → soft-warn; Confirm still succeeded.

## Revert

`POST /learn/revert` with `expected_version` = session `config_version_after` only if live still matches.

## Related

- [preview-rule](../preview-rule/SKILL.md)
- Orchestrator stop: refuse if ANALYST
