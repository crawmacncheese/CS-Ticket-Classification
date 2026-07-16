---
name: profile-run
description: >-
  Deterministic session profile for a portal run: NL focus → slice counts,
  sweep matches, ZERO_MATCHES clarify. Use when profiling a run, auditing B2C
  sweeps, or before drafting a rule from Review chat / Christine.
---

# profile-run

**skill_version:** 1  
**Write:** never  

## I/O

**Input**

| Field | Type | Required |
|-------|------|----------|
| `run_id` | string | yes (or demo upload) |
| `focus_nl` | string | yes |
| `base_url` | string | no (default `http://127.0.0.1:8777`) |

**Output**

| Field | Notes |
|-------|------|
| `profile` | `slice_count`, `tbc_count`, `sweep_summaries`, `no_op`, `blockers` |
| `cards` | `profile_summary`, `sweep` (+ `compile_phrase`), `clarify` |
| Terminal | `ZERO_MATCHES` → clarify; **do not** call propose-rule |

## How to run

```bash
python scripts/session_profile.py --run-id <uuid> --focus "review B2C" --json
```

Portal:

```http
POST /run/{run_id}/review_chat/turn
{"text": "review B2C"}
```

## Notes

- No LLM on this path.
- Alias: taxonomy `rosetta_footer` → portal sweep `rosetta_system_email`.
- Prefer probe `review B2C` when Rosetta may already be System Report.

## Related

- Orchestrator: [christine-workflow](../christine-workflow/SKILL.md)
- Next: [propose-rule](../propose-rule/SKILL.md) when a sweep has `compile_phrase`
