---
name: filter-tickets
description: >-
  Convert natural-language focus into structured portal filters (category audit,
  TBC queue, or rules list). Use when the user wants to filter or search tickets
  without drafting a rule.
---

# filter-tickets

**skill_version:** 1  
**Write:** never  

## I/O

**Input**

| Field | Type | Required |
|-------|------|----------|
| `text` | string | yes |
| `mode` | `category_audit` \| `tbc` \| `run_preview` \| `rules` | yes |

**Output**

| Field | Notes |
|-------|------|
| `ok` | parse success |
| `audit_filter` / `run_filter` / `rule_filter` | structured fields |
| `*_url` | redirect/query when provided |

## How to run

```http
POST /run/{run_id}/category_audit_parse_focus
{"text": "review B2C cancellation"}

POST /run/{run_id}/tbc_parse_focus
{"text": "…"}

POST /run/{run_id}/run_parse_focus
{"text": "…"}

POST /rules/parse_focus
{"text": "…"}
```

## Constraints

- Output must map to portal query params — do not invent tier paths outside allow-list parse.
- Filtering ≠ classify. No LLM writes to ticket categories.
- Phrases like “show all TBC” / “review manual review tickets” should open **`/run/{id}/tbc`**, not `/rules/compile`.

## Related

- [profile-run](../profile-run/SKILL.md) when the goal is sweeps + counts, not only UI filter
