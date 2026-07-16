# Christine Workflow — API & Package Reference

Companion to [SKILL.md](SKILL.md). Prefer the runner over hand-rolled curls.

## Dify pattern mapping (reference only)

Awesome-Dify-Workflow DSL inspirations (not Cursor file format):

| Dify pattern | Christine skill equivalent |
|--------------|----------------------------|
| `information_schema` / `task_schema` fields | Session **intake schema** in SKILL.md |
| TOD until `InformationCollectionCompleted` | Gate until `SessionIntakeComplete` |
| `if-else` → only then plan/execute | Package review `<PLAN>` then runner |
| Agent `instruction` + tools | Skill Role/Task + CLI entrypoints |
| Structured Role / Task / Limits prompts | SKILL Role / Task / Constraints |

Keep this skill as **SKILL.md** (Markdown). Do not convert the Christine skill into Dify app YAML unless building a separate Dify prototype.

## Session intake fields (copy)

| name | required | question (short) |
|------|----------|------------------|
| `run_id_or_export` | yes | run_id, NDJSON path, or demo fixture? |
| `focus_nl` | yes | What to review? |
| `persona` | no (default ANALYST) | ANALYST or LEAD? |
| `goal` | yes | PROFILE_ONLY / DRAFT_RULE / CONFIRM_RULE |
| `rule_prefill_or_sweep` | no | compile phrase or sweep id |

## Session Metadata Package (top-level)

| Field | Type | Notes |
|-------|------|-------|
| `session_id` | string | `sess_` + hex |
| `run_id` | string \| null | Portal run |
| `run_mode` | enum | `TBC_REVIEW` \| `CATEGORY_AUDIT` \| `COMPILE_ONLY` |
| `user_persona` | enum | `ANALYST` \| `LEAD` |
| `taxonomy_version` | int | From taxonomy MD `protocol_version` |
| `profile` | object | Phase A profile dict |
| `orchestration_queue` | array | Empty when terminal blockers |
| `blockers` | array | Terminal: `ZERO_MATCHES`. Soft: `NEEDS_LEAD_CONFIRM`, `PREVIEW_STALE`, `COMPILE_CLARIFY` |
| `clarify_message` | string \| null | Human ask when blocked |

### Invariants

- `ZERO_MATCHES` ⇒ empty `orchestration_queue`
- `is_actionable` ⇔ non-empty queue and no terminal blockers
- `CLARIFY` is not a queue action

## Profile fields

| Field | Notes |
|-------|-------|
| `focus_nl` | User focus text |
| `audit_filter` | `tier1`, `categories`, `q`, … |
| `slice_count` | Tickets in audit slice |
| `tbc_count` | TBC in full run |
| `sweep_summaries[]` | `sweep_id`, `match_count`, `sample_ids` |
| `no_op` | True when slice empty and all sweeps zero |

## Sweep id aliases (taxonomy → portal)

| Taxonomy `sweep_id` | Portal sweep `id` |
|---------------------|-------------------|
| `rosetta_footer` | `rosetta_system_email` |
| `refund_precedence` | `refund_cancel_combo` |
| `account_deletion` | `delete_account_gdpr` |
| `esp_print` | `esp_print` |
| `posties_young_post` | `posties_young_post` |
| `invoice_request` | `invoice_request` |

## Portal API map

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
| Review chat entry | GET | `/run/{id}/review_chat` → `/rules/new?mode=orch` |
| Profile turn | POST | `/run/{id}/review_chat/turn` |
| Session log (optional) | POST | `/run/{id}/review_chat/log` |

### Confirm / revert notes

- `POST /rules/confirm` does **not** take `run_id` (promotes live only).
- Runner Confirm gate: living `run_id` + successful `PREVIEW_RULE` this session (`PREVIEW_STALE` otherwise).
- Reclassify may 404 if the in-memory run expired; treat as soft-fail after Confirm.
- Compile failures return `clarify_message` (analyst-facing) plus raw `errors` (session MD / debug).
- Revert v1: `POST /learn/revert` with form `expected_version` — only safe if session `config_version_after` still matches live.

## Python helpers

| Module | Function |
|--------|----------|
| `cs_tickets.session_profile` | `build_session_profile`, `compute_no_op` |
| `cs_tickets.session_metadata` | `parse_package`, `package_from_profile`, `build_rosetta_package`, `runner_gate` |
| `cs_tickets.taxonomy_requirements` | `load_taxonomy_requirements`, `format_taxonomy_for_compile` |
| `scripts/run_christine_session.py` | `execute_package`, `profile_via_http` |

## Preview response shape (`POST /rules/preview`)

```json
{
  "ok": true,
  "rule_id": "…",
  "results": [
    {
      "ticket_id": "170002",
      "before": ["B2C", "…"],
      "after": ["B2C", "…"],
      "matched": true,
      "candidate_matched": true,
      "candidate_won": false,
      "tier_changed": false,
      "evidence_before": [{"rule_id": "…", "weight": 14.0, "signal": "…"}],
      "evidence_after": [{"rule_id": "…", "weight": 14.0, "signal": "…"}],
      "shield_overlap": ["stefan_rule_moderation"]
    }
  ],
  "summary": {
    "changed": 0,
    "candidate_matched": 1,
    "candidate_won": 0,
    "shield_overlap": 0,
    "headline": "0 changed; 1 matched; 0 overlap"
  }
}
```
