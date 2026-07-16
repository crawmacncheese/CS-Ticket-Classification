# Portal API reference

HTTP routes exposed by `cs_tickets.portal_app:app` (FastAPI). Unless noted, responses are HTML for browser pages or JSON for AJAX.

**Base URLs:**

- Local: `http://127.0.0.1:8777`
- Dev: `https://cs-ticket-automation.itbs-dev.scmp.tech`
- Prod: `https://cs-ticket-automation.scmp.work`

**Auth:** No application-level authentication in Phase 1 — rely on network / ingress policy.

**Run scope:** Most `/run/{run_id}/…` routes require an active in-memory run (created by `POST /run`). Runs are lost on process restart.

---

## Health and static

| Method | Path | Response | Notes |
|--------|------|----------|-------|
| GET | `/health` | `text/plain` `ok` | Load balancer probe |
| GET | `/static/*` | Static assets | CSS, JS (`rules.js`, `category_audit.js`, etc.) |

---

## Classify

| Method | Path | Response | Body / params |
|--------|------|----------|---------------|
| GET | `/` | HTML | Upload form |
| POST | `/run` | HTML | `multipart`: `export` (NDJSON), optional `bad_satisfaction_only=true` |
| GET | `/run/{run_id}/results` | HTML | `?reclassified=1` optional banner |
| GET | `/download/{run_id}` | XLSX | Run metadata + Tickets + Tier breakdown sheets |

---

## Category audit

| Method | Path | Response | Body / params |
|--------|------|----------|---------------|
| GET | `/run/{run_id}/category_audit` | HTML | Bucket review UI |
| GET | `/run/{run_id}/category_audit/sweeps` | JSON | `?tier1=`, `?categories=` |
| GET | `/run/{run_id}/category_audit/export.csv` | CSV | Filtered audit export |
| POST | `/run/{run_id}/category_audit_parse_focus` | JSON | `{ "text": "review B2C …" }` |

Plan: [plans/2026-07-07-category-audit-workflow.md](./plans/2026-07-07-category-audit-workflow.md).

---

## Review chat

| Method | Path | Response | Body / params |
|--------|------|----------|---------------|
| GET | `/run/{run_id}/review_chat` | Redirect | → `/rules/new?mode=orch&run_id=…` |
| POST | `/run/{run_id}/review_chat/turn` | JSON | Focus / profile turn (LLM when configured) |
| POST | `/run/{run_id}/review_chat/log` | JSON | Append row to optional session MD |
| POST | `/run/{run_id}/run_parse_focus` | JSON | NL focus for full-run preview filter |

Framework: [architecture/agent-skills-framework.md](./architecture/agent-skills-framework.md).

---

## Ticket detail and explain

| Method | Path | Response | Body / params |
|--------|------|----------|---------------|
| GET | `/run/{run_id}/ticket/{ticket_id}` | JSON | Row + tiers for inline preview |
| GET | `/run/{run_id}/explain/{ticket_id}` | JSON | `ClassificationDecision` trace |
| POST | `/run/{run_id}/override/{ticket_id}` | JSON | Run-scoped tier override (not live rules) |
| POST | `/run/{run_id}/override/{ticket_id}/clear` | JSON | Clear override |
| POST | `/run/{run_id}/reclassify` | JSON | Re-run classify on stored NDJSON after live config change |

---

## TBC queue

| Method | Path | Response | Body / params |
|--------|------|----------|---------------|
| GET | `/run/{run_id}/tbc` | HTML | TBC workbench page |
| GET | `/run/{run_id}/tbc_queue` | JSON | Paginated TBC tickets + filters |
| POST | `/run/{run_id}/tbc_parse_focus` | JSON | `{ "text": "…" }` → structured filter |
| POST | `/run/{run_id}/tbc_draft_rule_for_filter` | JSON | Draft rule from current TBC filter |
| POST | `/run/{run_id}/tbc_chunk/ack` | JSON | Ack reviewed TBC chunk |
| POST | `/run/{run_id}/suggest_category/{ticket_id}` | JSON | LLM category suggestion (optional) |
| POST | `/run/{run_id}/add_allowlist_tuple/{ticket_id}` | JSON | **Confirm gated** — add tuple from ticket |

---

## Rules (explicit authoring)

| Method | Path | Response | Body / params |
|--------|------|----------|---------------|
| GET | `/rules` | HTML | Live rules list |
| GET | `/rules/new` | HTML | Chat UI; `?run_id=`, `?mode=orch` |
| POST | `/rules/parse_focus` | JSON | NL filter for rules list |
| POST | `/rules/compile` | JSON | `{ "messages": [...], "run_id?", "exemplar_ticket_id?", "prior_rule?" }` → draft + risk |
| POST | `/rules/preview` | JSON | `{ "rule": {...}, "run_id?" }` → impact summary |
| POST | `/rules/preview_upload` | multipart | NDJSON + rule → offline preview |
| POST | `/rules/confirm` | JSON | **Confirm gated** — promote one rule |
| POST | `/rules/confirm_batch` | JSON | **Confirm gated** — promote batch |
| POST | `/rules/disable` | Redirect | **Confirm gated** — `rule_id` form field |

**Confirm gated:** requires `PORTAL_ALLOW_CONFIRM=1` (or truthy) in server env.

Plan: [plans/2026-07-03-explicit-rule-authoring.md](./plans/2026-07-03-explicit-rule-authoring.md).

---

## Learn New (allow-list + rules)

| Method | Path | Response | Body / params |
|--------|------|----------|---------------|
| GET | `/learn` | HTML | Wizard entry |
| POST | `/learn/process` | HTML | `multipart`: classified `workbook` (.xlsx) |
| POST | `/learn/preview` | HTML | `upload_id`, optional NDJSON + `bad_satisfaction_only` |
| POST | `/learn/confirm` | HTML | **Confirm gated** — promote accepted tuples/rules |
| POST | `/learn/cancel` | Redirect | Drop in-progress upload |
| POST | `/learn/revert` | HTML | Restore from backup; optional `expected_version` |
| GET | `/training` | Redirect | → `/learn` |

---

## Dashboard

| Method | Path | Response | Notes |
|--------|------|----------|-------|
| GET | `/dashboard` | HTML | TBC trends from SQLite (`TBC_TRENDS_DB_PATH`) |

---

## JSON response patterns

### Rule compile (`POST /rules/compile`)

Success payload includes draft `rule`, optional `clarify_message`, `risk` grade from Consistency Gateway, and soft `warnings`. Errors: `400` validation, `502` LLM failure.

### Rule preview (`POST /rules/preview`)

Returns `summary` with match counts, tier deltas, `shield_overlap`, and `risk` when `run_id` is provided.

### Explain (`GET …/explain/{ticket_id}`)

Returns tier tuple, score, `fallback_used`, ranked `candidates`, and `evidence` (rule ids + weights).

### TBC queue (`GET …/tbc_queue`)

Query params: pagination, sort, structured filters from parse-focus. Returns ticket rows with TBC reason buckets.

---

## Error codes

| Code | Typical cause |
|------|---------------|
| 400 | Missing body fields, invalid rule JSON |
| 404 | Unknown `run_id` or ticket |
| 403 | Confirm attempted when `PORTAL_ALLOW_CONFIRM` disabled |
| 502 | LLM provider error on compile / suggest |

---

## OpenAPI

FastAPI auto-schema is available at `/docs` and `/redoc` when running locally if not disabled. This document is the maintained operator reference; regenerate from `portal_app.py` when adding routes.

**Source:** [`src/cs_tickets/portal_app.py`](../src/cs_tickets/portal_app.py)

---

## Related

- [ops-runbook.md](./ops-runbook.md)
- [configuration.md](./configuration.md)
- [.cursor/skills/](../.cursor/skills/) — agent-facing skill docs mirroring these APIs
