# Explicit Rule Authoring — Implementation Plan

> **For implementer:** Document steps in `docs/plans/2026-07-03-explicit-rule-authoring-notes.md` when execution starts.

**Goal:** Classifier maintainers describe routing rules in **natural language** (conversational / chat-style input). An **LLM compiles** that text into a validated **`RuleSpec` + target category** the deterministic classifier can run. The maintainer **reviews**, **sandbox-previews**, and **Confirms** before the rule merges into **`runs/live/classifier_rules.json`**. **No LLM in the `/run` classification hot path** — only in the authoring step.

**Source context:** [Gemini-update-notes.md](./Gemini-update-notes.md) (client workflow; Gemini is workaround only). [2026-07-03-gemini-conversation-patterns.md](./2026-07-03-gemini-conversation-patterns.md) — distilled from client PDF export (~320 pages). Builds on completed [category drill-down](./2026-07-02-category-review-and-drill-down.md).

**Users:** Role split locked in [2026-07-06-christine-workflow-decisions.md](./2026-07-06-christine-workflow-decisions.md) (**Model B — shared loop, gated promote**).

| Persona | Need |
|---------|------|
| **CS analyst** | TBC queue (chunks of 10), explain, **propose rule** from ticket (compile + preview); **no Confirm** |
| **Classifier maintainer / CS team lead** | Review compiled rules; **Confirm live**; disable/replace; re-classify run after promote |
| **Taxonomy owner** | Ensure compiled tier is allow-listed; reject invalid LLM suggestions at Confirm |

**Architecture:** **`rule_compile`** service (LLM + strict JSON schema + allow-list validation) → proposed `RuleSpec` → **review panel** (structured, editable) → **sandbox classify** → **Confirm** via existing promote path. List/disable/edit still available for lifecycle.

**Principles from client patterns** ([patterns doc](./2026-07-03-gemini-conversation-patterns.md)):

| Client habit | Portal requirement |
|--------------|-------------------|
| Versioned master prompt (V13→V37+) | **`runs/live/classifier_rules.json`** is the portable rule store; optional prose spec appendix — not a 300-page paste into compile |
| “Did u read my file?” — rules grounded in real tickets | Compile **must** use exemplar ticket + explain evidence when available; reject vague rules with no match conditions |
| **`Update: Map "phrase" → tier`** phrasing | Few-shot + input normalizer accept paraphrases (`Map X to Y`, `If … then …`, `CRITICAL: do NOT …`) |
| Shield rules checked **first** | Weight bands + `override` for shields; `exclude_blob` for CRITICAL negatives — see [Precedence](#precedence--shield-rules) |
| 4-tier Gem labels vs 5-tuple workbook | Compiler maps to **`AllowList` 5-tuple**; workbook path wins over Gem/session labels |
| “Next 10 TBC” → correct one ID → map phrase | TBC queue chunk UI → explain → compile chat with ticket prefill (Phase 3) |
| Save latest prompt for next batch | **Confirm** writes live JSON; no session-only prompt as source of truth |

**Tech stack:** FastAPI portal, vanilla JS chat UI, Gemini (or configured model) for **compile-only**, `RuleSpec` / `classifier_rules.json`, Drive `runs/live/`.

**Depends on:** [design.md](../design.md); [prd-phase2-learning-feedback.md](../prd-phase2-learning-feedback.md) Confirm gate; drill-down explain; `portal_learn.py` promote patterns.

**Out of scope for this plan:**

- LLM classifying tickets on `/run` or in TBC batch review (deterministic engine only at runtime)
- Auto-Confirm without human review of compiled rule
- Automatic rule mining without human Confirm (keep `/learn` separate)
- Editing `classify.py` computed logic via UI
- Full `CategorizationEvent` audit DB (Phase 3 lite: rule metadata only)

---

## Context

### Why the client uses Gemini today

From [Gemini-update-notes.md](./Gemini-update-notes.md): batch TBC context, natural-language rule thinking, immediate iteration. **This plan keeps the conversational UX** but routes output into **`RuleSpec`** instead of ad-hoc chat categorization.

### Client Gemini loop → portal mapping

See [patterns doc](./2026-07-03-gemini-conversation-patterns.md) for the full loop. Implementation-relevant slice:

```text
Gemini: upload + master prompt → TBC table → "Update: Map …" → save prompt V34
Portal: /run + live rules → TBC queue (Phase 3) → compile chat → Confirm → live JSON
```

**Compiler utterance targets** (few-shot in `rule_compile_prompt.py`; input normalizer accepts paraphrases):

```text
Update: Map "how can i renew my scmp" or "renewal reminder" to Sales Leads > Rate or Renewal Inquiry.
Update: Map "Stripe payment completed" to Billing & Admin > System Report.
If it contains Rosetta System Email, that is system email — NOT cancellation request.
CRITICAL: Do NOT mark Conversation with + URL-only as Sales Lead.
Stefan Rule: moderation / deleted comments → Account Management even if refund mentioned.
```

**High-value patterns** (seed compile corpus + golden compile tests — validate every tier against `AllowList`):

| Pattern | Target tier (workbook 5-tuple) | Rule shape |
|---------|-------------------------------|------------|
| Rosetta System Email footer | Billing & Admin > System Report | `any_blob` + `exclude_blob` cancel keywords |
| Stripe payment completed | System Report | `any_blob` |
| Conversation with + URL only | General Support > No Content - Live chat auto-trigger | `any_subject` + `override` — **not** Sales Lead |
| Moderation / deleted comments | Account Management (Comments blocked) | Named **Stefan Rule**; `override` beats refund `any_blob` |
| AlipayHK auto-debit notification | System Report or TBC | Distinguish from user-initiated cancel without Rosetta |
| Refund + cancel in same ticket | Taxonomy owner picks Refund vs Cancellation — encode once | Document in `notes`; no duplicate conflicting rules |
| Posties / Young Post | B2B segment | `any_blob` + optional `requires_b2b_print_context` |
| `privaterelay.appleid.com` | Sender signal for refund/cancel context | `any_requester_domain` |

### LLM boundary (PRD-safe)

| Step | LLM? | Notes |
|------|------|-------|
| Maintainer types rule in plain language | — | Chat / text input UI |
| **Compile** text → `RuleSpec` + tier | **Yes** | `rule_compile`; structured output only |
| Validate allow-list, schema, signals | **No** | Deterministic server checks; reject/reprompt |
| Sandbox preview on sample tickets | **No** | `classify_row_with_explanation` |
| **Confirm** → live rules | **No** | Same gate as `/learn` |
| **`/run` classify export** | **No** | [prd.md](../prd.md) NG-01 unchanged |

### What already exists

| Capability | Location |
|------------|----------|
| Rule storage (live) | `runs/live/classifier_rules.json` via `load_runtime_rule_specs()` |
| Workbook-mined proposals | `/learn` → `RuleProposal` → Confirm |
| Explain single ticket | `GET /run/{run_id}/explain/{ticket_id}` |
| Audit by category | Drill-down + `category_rows` / `tbc_rows` |
| Allow-list boundary | `AllowList` coercion on output |
| Compare before/after rules | `allowlist_compare` (training shell) |

### Gaps this plan closes

| Gap | Solution |
|-----|----------|
| No UI for explicit one-off rules | **Conversational Rules** UI + Confirm |
| “Type like an LLM” | Chat input → **compile** → review panel (not a checklist form as primary UX) |
| “Always this category” | `override: true` on `RuleSpec` (engine change) |
| Sender/domain rules | `requester_email` in flatten + `any_requester` / `any_requester_domain` on `RuleSpec` |
| No disable without delete | `enabled: false` + soft-disable in live JSON |
| No preview before live | Sandbox classify on current run sample |
| No entry from audit | “Propose rule from ticket” on explain pane |

---

## Design decisions

| Topic | Decision | Rationale |
|-------|----------|-----------|
| Primary UX | **Conversational text input** (chat-style); multi-turn refine (“also require tag X”) | Matches client Gemini habit; lower friction than checklist-first |
| Compiled artifact | **`RuleSpec` JSON** (same as today) | Single engine; `/learn` and chat-authored rules interoperate |
| Review step | **Structured preview panel** (read-only default + “Advanced edit”) | Human verifies LLM output; not a blind Confirm |
| LLM role | **Compiler only** — NL → `{ rule, rationale, confidence_notes }` | Never writes live config; never classifies production tickets |
| LLM provider | **Gemini** (configurable); API key server-side | Align with client stack; env `RULE_COMPILE_MODEL` |
| Compile context | **Never blank slate:** allow-list paths, `RuleSpec` field docs, **live rules digest** (ids + tiers + key matchers), **precedence corpus**, few-shots, exemplar + explain evidence when present | Replaces ad-hoc master prompt paste; tiers grounded in workbook |
| Precedence / shields | Weight bands (see below) + `override: true` for shields; `exclude_blob` for CRITICAL negatives | Engine evaluates overrides before weighted scoring |
| Named rules | Optional `display_name` on `RuleSpec` (e.g. `Stefan Rule`) | Shown in rules list + explain; `id` stays machine-stable |
| Validation after LLM | Schema parse → allow-list check → at least one match condition → no empty rule | Fail closed; show errors in chat (“tier not in list”) |
| “Always” rules | LLM may set `override: true` when user says “always” / “every time”; maintainer must see flag in preview | Maps client intent to engine semantics |
| Promote path | Reuse **`confirm_hybrid_proposals`** / `runtime_config` → `runs/live/` | Same human gate as `/learn` |
| Preview | Sandbox classify with `live_rules + [candidate]` | Prove rule matches intended tickets |
| Disable | `enabled: false`; loader skips | Soft delete |
| Sender rules | `requester_email` in flatten + `any_requester` / `any_requester_domain` | LLM prompt documents these fields when signal exists |
| Entry points | **`/rules`** (chat create) + “Add rule from this ticket” on explain pane | Ticket context passed into compile prompt |
| Advanced mode | Collapsible form editing raw `RuleSpec` fields | Escape hatch for maintainers; not default |
| Taxonomy mapping | Compiler outputs **5-tuple** only; map Gem-style 4-tier paths via allow-list search | e.g. `Service Task > Need help for Cancellation` → workbook `Complaint > Refund > Cancellation Request` |
| Portable export | `GET /rules/export` (optional P2) — live JSON + metadata | Parity with *“can you give me the master prompt?”* |
| **Who runs the loop** | **Model B** — analysts: TBC queue + propose rule; leads/maintainers: **Confirm** only | [2026-07-06 decisions](./2026-07-06-christine-workflow-decisions.md) |
| **Single-ticket relabel** | **Phase 1: no** — rule + Confirm + re-classify; **Phase 2:** run-scoped override for XLSX only | Avoids dual truth until TBC queue ships |

### Precedence / shield rules

Client master prompt (V18/V34) checks these **before** financial/growth rules. Encode in compile prompt and engine:

| Order | Shield | Typical `RuleSpec` | Weight band |
|-------|--------|-------------------|-------------|
| 1 | No Content / live-chat auto-trigger | `any_subject: ["conversation with"]` + URL-only body heuristic or blob guard; `exclude_blob` sales-lead signals | `override: true`, weight ≥ 20 |
| 2 | Stefan Rule (moderation friction) | `any_blob` moderation/deleted-comment phrases; `override: true` | weight ≥ 18 |
| 3 | External junk / vendor / HR | `any_blob` PR/job-application phrases → Junk | weight ≥ 16 |
| 4 | Financial / growth / B2B rules | Normal weighted rules | default 8–14 |

Compiler assigns shield rules into bands automatically when user says **CRITICAL**, **always**, **even if refund**, or names a shield (Stefan Rule). Maintainer sees band + `override` in review panel.

### Conversational rule authoring (primary UI)

```text
┌─ Rules — Describe a routing rule ──────────────────────────────┐
│  💬 Chat                                                      │
│  You: If email is from @scmp.com procurement, always B2B      │
│       Invoices and PO request                                 │
│  Assistant: I'll route tickets where the requester domain is    │
│       scmp.com and the body mentions purchase order / invoice   │
│       to B2B → … → Invoices and PO request. [Override: yes]   │
│                                                               │
│  ┌─ Compiled rule (review before Confirm) ─────────────────┐  │
│  │ Category: B2B → Service Task → Billing & Admin → …      │  │
│  │ Match: requester domain scmp.com; blob: purchase order… │  │
│  │ Override: ☑ Always when matched                         │  │
│  │ [Edit fields] [Preview on tickets] [Confirm live]       │  │
│  └─────────────────────────────────────────────────────────┘  │
│  [Type another refinement…                          ] [Send]  │
└───────────────────────────────────────────────────────────────┘
```

The **checklist / form** is the **review panel**, not the data-entry surface. Maintainers converse; the system compiles.

### LLM compile contract

**Request** (`POST /rules/compile`):

```json
{
  "messages": [{"role": "user", "content": "If sender is …"}],
  "exemplar_ticket_id": "optional",
  "run_id": "optional",
  "prior_rule": "optional — last compiled RuleSpec for multi-turn refine"
}
```

**Server-assembled context** (not sent by client; built in `rule_compile.py`):

- Allow-list tier index (tier4 labels + full 5-tuples on collision)
- `RuleSpec` field reference (supported matchers only)
- **Live rules digest** — compact list from `load_runtime_rule_specs()`: `id`, tier path, `override`, top matchers (avoid duplicating conflicting rules)
- Precedence corpus + few-shots (see [high-value patterns](#client-gemini-loop--portal-mapping))
- If `run_id` + `exemplar_ticket_id`: subject, tags, description snippet, requester, current explain tier + `evidence`

**Response** (strict JSON from model, validated server-side):

```json
{
  "rule": {
    "id": "explicit.procurement_scmp",
    "tier": ["B2B", "Service Task", "Billing & Admin", "Invoices and PO request", "N/A"],
    "weight": 14.0,
    "override": true,
    "any_requester_domain": ["scmp.com"],
    "any_blob": ["purchase order", "invoice"],
    "notes": "Compiled from: …"
  },
  "rationale": "Plain-language summary for the maintainer",
  "warnings": ["Tier4 matched allow-list path …"]
}
```

**System prompt rules:**

- Output **only** JSON matching schema; never invent tiers outside allow-list
- **Workbook wins:** if user cites a Gem 4-tier path, resolve to the matching 5-tuple or return `warnings` asking maintainer to pick
- When exemplar present: derive matchers from **that ticket’s text**, not generic placeholders
- Prefer `exclude_blob` when user says **NOT**, **do not mark**, or corrects a mis-route (e.g. Rosetta ≠ cancellation)
- Set `display_name` when user names a rule (Stefan Rule, etc.)
- Suggest `enabled: false` on superseded rule id when user says “replace rule X” (Confirm handles both in replace flow)

**On validation failure:** return chat message with errors; auto-retry compile with validator feedback (max 1 retry). Common failures: tier not in list, no match conditions, duplicate `id`, shield rule without `override`.

### Propose rule from ticket (drill-down)

Explain pane → **Add rule from this ticket** opens `/rules/new` with:

- Chat pre-filled (TBC queue uses same template):

```text
When tickets look like #{ticket_id} ("{subject_snippet}"), they should be {suggested_tier or "TBC — suggest category"} because {why_tbc_or_user_note}.
Classifier currently: {explain_top_evidence}.
```

- `exemplar_ticket_id` + `run_id` on every compile call
- Explain `evidence` injected server-side (maintainer can edit prefill before Send)

---

## Phase 1 — Engine extensions

### Task 1.1 — `requester_email` signal

**Files:** `flatten.py`, `schema.py`, `classify.py` (`_RowSignals`, `_signals`, `_rule_matches`)

- Parse requester from Zendesk export (field name per fixture audit)
- Add to `BASE_COLUMNS` if persisted in master rows (optional for Excel — confirm workbook contract)
- Expose in explain / preview payloads for display

### Task 1.2 — Extend `RuleSpec`

**Files:** `classifier_rules.py`, `classifier_rules.json` schema docs

New optional fields:

```python
enabled: bool = True
override: bool = False
any_requester: tuple[str, ...] = ()
any_requester_domain: tuple[str, ...] = ()
display_name: str = ""  # human label, e.g. "Stefan Rule"
notes: str = ""
created_at: str = ""  # ISO; set on Confirm
disabled_at: str = ""
replaced_by: str = ""  # rule id
source_message: str = ""  # optional: originating chat turn
```

`exclude_blob` already exists on `RuleSpec` — compiler should emit it for CRITICAL negatives (e.g. exclude `sales lead` when matching live-chat auto-trigger).

- `_load_rules_file` / `_rule_from_dict` accept new keys; default `enabled=True`
- `load_runtime_rule_specs` filters `enabled is not False`

### Task 1.3 — Override evaluation

**Files:** `classify.py` (`_score_tiers` or `classify_row_with_explanation`)

Before weighted scoring:

1. Collect matching rules where `override and enabled`
2. If exactly one → return that tier with `evidence` pointing to rule id
3. If multiple → TBC or highest-priority rule id (lexicographic id tie-break); **log warning in evidence**

### Task 1.4 — Tests

**Files:** `tests/test_classify.py`, `tests/test_classifier_rules.py`

- Override beats competing weights
- Disabled rule ignored
- Requester domain match
- Backward compat: existing JSON loads unchanged

---

## Phase 2 — Conversational rules portal + compile service

### Task 2.1 — `rule_compile` module

**Files:** new `src/cs_tickets/rule_compile.py`, `rule_compile_prompt.py`; corpus in [`rule_compile_corpus.py`](../../src/cs_tickets/rule_compile_corpus.py) (few-shots + golden fixtures)

- Build system prompt: allow-list + schema + **live rules digest** + precedence corpus + few-shots from [high-value patterns](#client-gemini-loop--portal-mapping)
- **Input normalizer:** map common paraphrases to canonical intent before LLM (`Map "x" to Y`, `always category Y when`, `CRITICAL: do NOT`)
- Call Gemini (google-genai or existing org client); `response_mime_type: application/json`
- Parse → `RuleSpec` via `_rule_from_dict`; apply weight band heuristics for shields
- Validator: tier ∈ allow-list; ≥1 condition field; id unique vs live; shield rules should have `override` (warning if missing)
- Unit tests with **mocked** LLM responses (no live API in CI); **golden compile fixtures** for Rosetta, Stefan, live-chat, Stripe patterns

### Task 2.2 — Compile API

**Files:** `portal_app.py`, `portal_rules.py`

- `POST /rules/compile` — messages + optional exemplar → `{ rule, rationale, warnings }`
- `POST /rules/confirm` — validated `RuleSpec` → promote (same as below)
- Rate limit / max message length; log compile requests (no ticket PII in logs if policy requires redaction)

### Task 2.3 — Chat UI

**Files:** `portal_rules.py`, `static/rules.js`, `cs_tickets_theme.css`

- `GET /rules/new` — chat layout + empty review panel
- Send message → compile → append assistant rationale + populate review panel
- Multi-turn: send refinement with prior compiled rule in context
- **Confirm live** disabled until validation passes and optional preview acknowledged

### Task 2.4 — Review panel (structured, secondary)

- Human-readable summary of conditions + tier path + override flag
- **Advanced edit** expands to field-level form (checkboxes/inputs map to `RuleSpec`)
- Edits re-validate without re-calling LLM unless user clicks “Re-compile from chat”

### Task 2.5 — Rules list + disable

**Files:** `portal_rules.py`, nav in `portal_layout.py`

- `GET /rules` — table of live rules; Disable / Edit (edit opens chat + review with rule loaded as context)

### Task 2.6 — Promote integration

**Files:** `feedback/promote.py` or `promote_explicit_rule()`

- Confirm merges into `runs/live/classifier_rules.json`; Drive sync; cache invalidate

### Task 2.7 — Sandbox preview

**Files:** `portal_rules.py`

- `POST /rules/preview` — candidate rule + `run_id` + ticket ids → before/after tiers

### Task 2.8 — “Add rule from this ticket”

**Files:** `ticket_preview.js`, `portal_rules.py`

- Explain pane button → `/rules/new?run_id=&ticket_id=` with exemplar context for compile

### Task 2.9 — Tests

**Files:** `tests/test_rule_compile.py`, `tests/test_portal_rules.py`

- Validator rejects tier not in allow-list
- Mock compile returns parseable rule
- Confirm appends to live JSON in test harness
- Portal smoke: chat page renders, compile endpoint 200 with fixture

---

## Phase 3 — Rule lifecycle (lite)

### Task 3.1 — Disable / replace flow

- Disable sets `enabled: false`, `disabled_at`, optional `notes`
- Replace: disable old, create new with `replaced_by` link on old rule’s `replaced_by` field pointing to new id

### Task 3.2 — Rule health (minimal)

**Files:** `portal_rules.py`

- Surface rules never matching in last N portal runs (future: needs match logging) — **defer full metrics**
- **MVP:** manual “last reviewed” date field on rule + sort by age
- Link from drill-down: “This ticket matched rule X” in explain pane (already shows rule ids)

### Task 3.3 — TBC queue shell (client parity — P1 after Phase 2) ✅

> **Implemented 2026-07-06** with review focus, session continuity, and allow-list gap handling — see [2026-07-06-tbc-queue-review-focus-notes.md](./2026-07-06-tbc-queue-review-focus-notes.md).

Mirror PDF **“show me tickets needing manual review” / “next 10 TBC”** — same table shape as Gem:

| Ticket ID | Context / quote | Why TBC | Suggested classification |
|-----------|-----------------|---------|--------------------------|
| `#167391` | subject + description snippet | explain `evidence` / competing rules | top weighted candidate or “—” |

| Column | Source |
|--------|--------|
| Ticket ID | `tbc_rows` |
| Context / quote | preview subject + ~120 char description |
| Why TBC | `GET /run/{run_id}/explain/{ticket_id}` |
| Suggested classification | explain payload top candidate tier |

- Default chunk size **10**; prev/next chunk; filter persists across chunks  
- Row: **Explain** → **Add rule from this ticket** (prefill template above)  
- Maintainer may say *“the rest ok”* (no bulk action) or correct specific IDs via compile chat  
- **No** batch LLM categorize — deterministic explain only; rules land via compile → Confirm  
- After Confirm, **re-classify run** (`POST /run/{run_id}/reclassify`) and refresh chunk; show TBC before/after (no “0 TBC” claim without golden tests)  
- **Model B:** analysts use **Propose rule**; **Confirm live** visible only to lead/maintainer ([decisions doc](./2026-07-06-christine-workflow-decisions.md))  
- **Phase 1:** no single-ticket relabel; **“Skip chunk”** acks chunk only (`POST …/tbc_chunk/ack`)  
- **Extensions:** NL review focus (`POST …/tbc_parse_focus`), keyword/category filters, batch rule draft/confirm, allow-list add from TBC — [notes](./2026-07-06-tbc-queue-review-focus-notes.md)

---

## Implementation order

```text
Phase 1 (engine)
  1.1 requester_email
  1.2 RuleSpec fields + loader
  1.3 override evaluation
  1.4 tests

Phase 2 (conversational authoring)
  2.1 rule_compile module + prompt
  2.2 POST /rules/compile
  2.3 chat UI
  2.4 review panel + advanced edit
  2.5 rules list + disable
  2.6 promote / Confirm
  2.7 sandbox preview
  2.8 add rule from ticket
  2.9 tests

Phase 3 (lifecycle)
  3.1 disable/replace
  3.2 minimal health fields
  3.3 TBC queue shell (client parity — after 2.8)
```

---

## Acceptance criteria

### Phase 1

- [ ] Maintainer can define `any_requester_domain` rule in JSON; classifier matches
- [ ] `override: true` rule forces tier when matched
- [ ] `enabled: false` rule never matches
- [ ] Existing `classifier_rules.json` unchanged behavior when new fields absent

### Phase 2

- [ ] Maintainer can describe a rule in chat; **compile** returns valid `RuleSpec` + rationale
- [ ] Compile context includes live rules digest (not blank slate)
- [ ] Paraphrased **Update: Map** / **CRITICAL** inputs compile correctly (golden fixtures: Rosetta, Stefan, live-chat)
- [ ] Invalid tier or empty conditions rejected with clear chat error (no Confirm)
- [ ] Review panel shows compiled rule + `override` / weight band for shields; **Advanced edit** allows field tweaks
- [ ] Multi-turn refinement updates compiled rule (`prior_rule` in compile request)
- [ ] Preview shows at least one ticket tier change before Confirm (exemplar ticket when present)
- [ ] Confirm writes live without redeploy; next `/run` uses new rule
- [ ] “Add rule from this ticket” passes exemplar + explain evidence into compile context
- [ ] `/rules` lists live rules; disable stops matching

### Phase 3

- [ ] Disable rule stops matching; rule still visible in list as disabled
- [ ] Replace links old → new rule id
- [x] TBC queue shows 10-ticket chunks with Gem table columns; explain → compile prefill → Confirm path ([notes](./2026-07-06-tbc-queue-review-focus-notes.md))
- [ ] Shield rules (live-chat, Stefan, junk) compile with `override` and correct weight band

### Non-regression

- [ ] `/learn` Confirm still works
- [ ] Drill-down + explain unchanged
- [ ] Golden classifier tests pass (or updated with intent)

---

## Success metrics (from client brief)

| Metric | How we measure |
|--------|----------------|
| Conversational parity | Maintainers prefer `/rules` chat over external Gemini for **rule capture** |
| Compile accuracy | % compiles Confirm without advanced edit (track qualitatively at first) |
| Safety | Zero auto-Confirm; validator blocks invalid tiers |
| Time to live rule | Minutes from audit → chat → Confirm |

---

## Open questions

| # | Question | Default |
|---|----------|---------|
| 1 | Add `requester_email` to Excel export columns? | Portal + compile first; Excel optional |
| 2 | Multiple override matches | TBC + evidence lists conflicting rule ids |
| 3 | Who can Confirm? | Same as `/learn` (document trust model) |
| 4 | Which Gemini model? | Env `RULE_COMPILE_MODEL`; flash for speed, pro for quality |
| 5 | Store chat history? | Session-only until Confirm; optional save `notes` + `source_message` on rule |
| 6 | Rule id edit after live? | Immutable id; replace flow for renames |
| 7 | Allow-list size in prompt | Tier4 index + full 5-tuple on ambiguity; B2B corp names grow per batch — compile suggests `any_blob`, maintainer spot-checks on `category_rows` |
| 8 | Refund + cancel in same ticket | **Block compile** until taxonomy owner sets disambiguation note in corpus; then single encoded rule — no duplicate Refund/Cancel rules for same blob set |
| 9 | Live-chat URL-only heuristic | Body “URL-only” may need `any_blob` / `any_url` combo vs subject-only — validate on fixtures from PDF export before shipping shield #1 |
| 10 | Rules export | Optional `GET /rules/export` in Phase 2 if maintainers ask for master-prompt parity |

---

## What we deliberately do not build (from patterns doc)

- Full-batch **LLM categorization** on `/run` — deterministic engine only
- **Prompt version as only rule store** — `RuleSpec` JSON + Confirm is source of truth
- **Unbounded corporate keyword lists** without allow-list validation and spot-check
- **Claiming 0 TBC** without golden tests after rule changes

---

## References

- [2026-07-03-gemini-conversation-patterns.md](./2026-07-03-gemini-conversation-patterns.md) — PDF-derived loop, precedence, few-shots
- [Gemini-update-notes.md](./Gemini-update-notes.md) — client pain (workaround vs end state)
- [2026-07-02-category-review-and-drill-down.md](./2026-07-02-category-review-and-drill-down.md) — audit entry point
- [prd.md](../prd.md) — NG-01: no LLM **classifier**; LLM **compile** is authoring-only with Confirm
- [prd-phase2-learning-feedback.md](../prd-phase2-learning-feedback.md) — Confirm gate
- `src/cs_tickets/classifier_rules.py` — `RuleSpec`
- `src/cs_tickets/feedback/promote.py` — live merge
- `src/cs_tickets/rule_compile_corpus.py` — precedence, few-shots, golden fixtures
