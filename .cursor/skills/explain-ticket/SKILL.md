---
name: explain-ticket
description: >-
  Explain why a ticket got its current 5-tuple (evidence rules, TBC reason).
  Read-only. Use when the user asks why a ticket was categorized or for
  decision-trace on category audit / TBC.
---

# explain-ticket

**skill_version:** 1  
**Write:** never  

## I/O

**Input**

| Field | Type | Required |
|-------|------|----------|
| `run_id` | string | yes |
| `ticket_id` | string | yes |

**Output**

| Field | Notes |
|-------|------|
| `tier` | 5-tuple path |
| `evidence` | matching rules / weights |
| `tbc_reason` | when applicable |

## How to run

```http
GET /run/{run_id}/explain/{ticket_id}
```

Also used from category audit **Explain** button.

## Constraints

- Read-only — do not invent rules or change live config.
- Prefer portal evidence over free-form LLM speculation; if summarizing, stay faithful to payload.

## Related

- [filter-tickets](../filter-tickets/SKILL.md)
- [profile-run](../profile-run/SKILL.md)
