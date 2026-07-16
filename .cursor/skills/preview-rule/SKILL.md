---
name: preview-rule
description: >-
  Dry-run a candidate RuleSpec on a living portal run (or upload). Shows tier
  before/after, shield overlap, and risk grade. Use after propose-rule and
  before confirm-rule.
---

# preview-rule

**skill_version:** 1  
**Write:** never  

## I/O

**Input**

| Field | Type | Required |
|-------|------|----------|
| `rule` | RuleSpec JSON | yes |
| `run_id` | string | yes for orch freshness |
| `ticket_ids` | string[] | no |

**Output** (`POST /rules/preview`)

| Field | Notes |
|-------|------|
| `results` | rows with `before`/`after`, `shield_overlap`, description/tags |
| `summary` | `changed`, `candidate_matched`, `shield_overlap`, `headline`, `risk` |

## How to run

```http
POST /rules/preview
{"rule": {…}, "run_id": "<uuid>"}
```

Upload fallback: `POST /rules/preview_upload` (multipart).

## Consistency

- If `run_id` 404 → `PREVIEW_STALE`; do not Confirm.
- `summary.risk` of `warn_shield` / `warn_churn` → emphasize for lead.
- Confirm must not proceed without a successful preview this session (orch mode).

## Related

- [propose-rule](../propose-rule/SKILL.md)
- [confirm-rule](../confirm-rule/SKILL.md)
