---
name: propose-rule
description: >-
  Compile natural language into a RuleSpec draft via POST /rules/compile.
  Proposal only — never promotes live. Use when drafting or refining routing
  rules after a profile/sweep or from a compile phrase.
---

# propose-rule

**skill_version:** 1  
**Write:** never (draft / proposal only)

## I/O

**Input**

| Field | Type | Required |
|-------|------|----------|
| `message` / last user content | string | yes |
| `run_id` | string | no (exemplar context) |
| `exemplar_ticket_id` | string | no |
| `prior_rule` | RuleSpec JSON | no |

**Output** (`POST /rules/compile`)

| Field | Notes |
|-------|------|
| `ok` | false → surface `clarify_message` (not raw schema) |
| `rule` | RuleSpec JSON when ok |
| `warnings` | soft conflicts |
| `risk` | Consistency Gateway: `ok` \| `warn_*` \| `block_schema` |
| `attempts` | compile retry count |

## How to run

```http
POST /rules/compile
{"messages": [{"role": "user", "content": "<compile phrase>"}], "run_id": "<optional>"}
```

Prefer taxonomy `compile_phrase` from a sweep card when available.

## Constraints

- Allow-list 5-tuple required; ≤2 mechanical retries then human clarify.
- Always follow with [preview-rule](../preview-rule/SKILL.md) before Confirm.
- Never call [confirm-rule](../confirm-rule/SKILL.md) as ANALYST.

## Related

- [preview-rule](../preview-rule/SKILL.md)
- Architecture: Consistency Gateway in plan 2026-07-15
