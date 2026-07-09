# Client workflow notes — TBC review, rules, and audit

> **Document type:** Product brief / pain-point capture (not an implementation spec).
>
> **Important:** The client **currently uses Gemini** for the workflow below because the portal lacked these capabilities. **Gemini is a workaround, not the desired end state.** The target is the same outcomes — batch TBC review, explainability, easy rules, no Excel loop — delivered **natively** via the deterministic classifier (`RuleSpec` + `classify.py`), portal UX, and the existing **`/learn` Confirm → `runs/live/`** promote path. See [2026-07-03-explicit-rule-authoring.md](./2026-07-03-explicit-rule-authoring.md).

## Workaround vs end state

| | **Today (workaround)** | **End state (this product)** |
|---|------------------------|------------------------------|
| Engine | Copy tickets into Gemini chat | Portal + weighted rule classifier |
| Rules | Prose in chat / ad hoc notes | `classifier_rules.json` in `runs/live/`, edited via Rules UI |
| “Why this category?” | Gemini rationale | `classify_row_with_explanation` + explain pane (done) |
| Re-review by category | Manual export or chat | Category drill-down (done) |
| Apply rule changes | Manual JSON / engineer | **Confirm** in portal → live on next `/run` |
| LLM in production? | Yes, for review only | **No** — aligns with [prd.md](../prd.md) NG-01 |

When this document says “LLM” or “Gemini,” read it as **the capability the client needs**. Runtime classification stays deterministic ([prd.md](../prd.md) NG-01). The only LLM in the end state is **compile-only** rule authoring (NL → `RuleSpec`, human Confirm) — see [explicit rule authoring](./2026-07-03-explicit-rule-authoring.md).

## End state (refined from PDF patterns)

Distilled from [gemini-conversation-patterns](./2026-07-03-gemini-conversation-patterns.md) and the implementation plan:

| Client habit (Gemini today) | Native delivery |
|----------------------------|-----------------|
| Versioned master prompt (V13→V37+) | `runs/live/classifier_rules.json` + optional export — not a prose-only store |
| “Did u read my file?” | Compile grounded in exemplar ticket + explain evidence |
| `Update: Map "phrase" → tier` | Chat compile + input normalizer; few-shots in `rule_compile_corpus.py` |
| Shield rules first (live-chat, Stefan, junk) | `override` + weight bands (≥20 / ≥18 / ≥16) + `exclude_blob` for CRITICAL negatives |
| “Next 10 TBC” → fix one ID → map phrase | TBC queue (Phase 3) → explain → compile chat prefill → Confirm |
| 4-tier Gem labels | Compiler maps to workbook **5-tuple**; allow-list wins |
| “Give me the master prompt” | Optional `GET /rules/export` (live JSON + metadata) |

**Compile corpus (golden fixtures):** `src/cs_tickets/rule_compile_corpus.py` — Rosetta, Stripe, Stefan, live-chat, renewal, junk patterns for mocked CI tests.

**Do not replicate:** full-batch LLM on `/run`, unbounded corp keyword lists, claiming 0 TBC without golden tests.

**Locked decisions (2026-07-06):** [2026-07-06-christine-workflow-decisions.md](./2026-07-06-christine-workflow-decisions.md) — **Model B** (analysts propose rules, leads Confirm); Phase 1 no single-ticket relabel; re-classify run after Confirm.

## Native product mapping (summary)

| Pain in this doc | Plan / status |
|------------------|---------------|
| Re-review by category, inspect details | [2026-07-02-category-review-and-drill-down.md](./2026-07-02-category-review-and-drill-down.md) — **Phases 1–2 done** |
| “Why categorized this way” | Explain endpoint — **done** (rule evidence, not chat rationale) |
| Rules CRUD, disable, strict IF→THEN | [2026-07-03-explicit-rule-authoring.md](./2026-07-03-explicit-rule-authoring.md) — **chat input → LLM compile → RuleSpec → Confirm** |
| TBC batch review (chunks of 10) | TBC queue UI — **Phase 3** of rule authoring; Gem table columns; no batch LLM classify |
| Rule health / override metrics | Phase 3 of rule authoring plan — **future** |
| Business rules spec (client prose) | [2026-07-03-gemini-conversation-patterns.md](./2026-07-03-gemini-conversation-patterns.md) — distilled from client PDF export |
| Iterative TBC → rule loop (10 at a time) | TBC queue → compile chat prefill → Confirm (not prompt version bump) |
| Precedence / shield rules (“Stefan Rule”, junk filter) | Weight bands + `override` + `exclude_blob`; corpus in `rule_compile_corpus.py` |
| Sender / domain rules | `any_requester` / `any_requester_domain` on `RuleSpec` (Phase 1 engine) |
| Portable “master prompt” | Confirm → live JSON; optional rules export |

**Source material:** Client’s **CS Christine** Gemini export (`Gemini.pdf`, ~320 pages). Patterns doc captures the loop; this file stays the product brief.

> **Note:** Sections below (“Original notes”, “Design outline”, “Product Brief”) describe the **client pain and early brainstorming**, much of which assumed LLM batch categorization. The **authoritative end-state design** is [2026-07-03-explicit-rule-authoring.md](./2026-07-03-explicit-rule-authoring.md): deterministic `/run`, compile-only LLM for rules, Confirm gate.

---

## Original notes (client context)

Organized thoughts (what the client is doing + what they want)
Current workflow (manual, Gemini-driven)
Batch review of TBC tickets: Gemini groups TBC tickets in small batches(eg 10), and reviews each batch in detail
Rich context per ticket: They include ticket details in the prompt.
Output expectation: Gemini returns a suggested category + explanation (why).
Rule discovery happens “in-chat”: While recategorizing, they notice patterns and propose explicit routing rules (e.g., “if sender is X, always category Y”).
Key gaps in our product/system
No rule/context interface: There’s no direct UI to add/maintain “rules” (agent context) that guide categorization.
Excel loop is unnecessary for this use case: For TBC review, they don’t want to export → edit → reupload; they want to apply decisions + add rules immediately.
Some rules can’t be mined reliably: Certain strict rules are too specific to expect automatic discovery; they need a human-maintained context list.
No easy re-review / audit:
They want to re-review tickets in a chosen category
They want to inspect details for a subset (spot-check, QA, edge cases)
Rules become outdated:
Older categorization guidance may no longer be valid
They need a way to remove/disable specific rules
They want a feedback loop so outdated rules don’t keep causing miscategorization

Draft plan (product + workflow)
1) Implement “Guidance / Rules” as first-class context (no Excel needed)
Create a Rules store (simple to start):
Each rule: IF conditions → THEN category, plus priority, status (active/disabled), owner, created_at, last_used, notes
Add a lightweight UI to manage rules:
Add rule, edit rule, disable rule, search rules, view rule history
Make rules available to the LLM step:
For any ticket review/categorization call, attach only relevant rules (by sender/domain/keywords/etc.) plus a short “global rules” section.
2) Build a “TBC Review” screen optimized for batch Gemini review
Queue and batch controls:
Filter = category == TBC, batch size default 10
“Send batch for review” generates a structured prompt: ticket summaries + required output format
Structured output capture:
For each ticket: category + rationale
Optional: “proposed new rules” section (Gemini suggestions), which user can accept/edit into the Rules UI
3) Add recategorization + audit tools (re-review and drill-down)
Re-review by category:
Pick a category, view tickets, sample N, or filter by time range/sender
Ticket detail inspection:
Quick view: sender, subject, key fields, conversation snippet, current category, applied rules
Audit trail: “why categorized this way” (rule matched vs LLM reasoning)
4) Add a feedback loop to keep rules current
Rule health signals:
Track when a rule is overridden (human changes category after suggestion)
Track confusion patterns (same ticket type bouncing categories)
Rule lifecycle actions:
“Disable rule” (soft delete) with reason
“Replace rule” flow: disable old, create new, link them
Periodic review workflow:
“Rules needing review” list (high override rate, not used recently, conflicting outcomes)
5) Rollout approach (minimize risk, ship fast)
Phase 1 (MVP): Rules UI + TBC batch review + apply category changes without Excel
Phase 2: Category re-review tools + audit trail (“why”)
Phase 3: Rule analytics + conflict detection + guided cleanup workflows
6) Success criteria (so we know it worked)
Reduce TBC backlog time (tickets/hour reviewed increases)
Higher consistency (fewer category flips for same pattern)
Less Excel usage (near-zero for TBC review loop)
Rule quality improves over time (override rate decreases; outdated rules get retired)
If you want, I can turn this into a one-pager PRD-style spec (screens, data model, and acceptance criteria) tailored to your existing repo structure.


Design outline: TBC review + rules-as-context + re-review loop
Goals
Faster, higher-quality TBC resolution by enabling chunked review with strong ticket context.
Rules become first-class (add/edit/disable) and are injected as LLM guidance.
Easy re-review / audit by category and by “why” a ticket was categorized.
Feedback loop to detect and retire outdated rules.
Non-goals (for initial scope)
Fully automated rule mining with high confidence for all cases.
Perfect “global” rule inference without human approval.
Replacing existing bulk upload flows (keep them, but don’t require them for TBC review).

Primary user journeys
1) Review TBC tickets in manageable chunks
Entry: “TBC Review” view
User actions:
Choose chunk size (default 10)
Send current chunk to LLM
Accept/edit suggested category per ticket
System outputs:
Category suggestions + explanation per ticket
Optional “suggested rules” for user to approve
2) Add and maintain rules (agent context) inline
Entry: From TBC review (“Add rule from this case”) or Rules page
User actions:
Create rule: conditions → category + priority + notes
Disable / edit / replace rule
System behavior:
Attach relevant active rules to LLM prompts
Log which rules were shown/applied for traceability
3) Re-review tickets by category / spot-check quality
Entry: “Category Review” view
User actions:
Filter tickets by category, date range, sender/domain, keyword
Sample N tickets
Trigger re-review (LLM) or manual adjustments
System outputs:
Audit trail: prior category, new category, reason, rule influence
4) Rule cleanup feedback loop
Triggers:
Frequent human overrides after suggestions
Conflicting rules, low usage, or aging rules
User actions:
Review “Rules needing attention”
Disable/replace with reason
System outputs:
Rule health metrics (override rate, last used, conflict flags)

UI / screens
TBC Review
Ticket chunk list (10 at a time): subject, sender, snippet, created time, current category
Ticket detail drawer: full thread excerpt + extracted fields
LLM suggestion panel: category + rationale + confidence (optional)
Actions: accept, edit category, mark needs human-only, add rule, next chunk
Rules (Guidance) Management
Rule list: search/filter, status, priority, last used
Rule editor: conditions builder + target category + notes + examples
Lifecycle controls: disable, replace, view history
Category Review / Audit
Filters: category, time, sender/domain, tags, “categorized by (rule vs LLM vs human)”
Audit timeline per ticket: what changed, when, by whom/what, and why

Data model (conceptual)
Ticket
id, sender, subject, body/thread, metadata (timestamps, channel), current_category
CategorizationEvent (audit trail)
ticket_id, from_category, to_category
source: human | llm | rule
llm_run_id (optional), rationale, timestamp, actor
Rule (Guidance item)
id, status: active | disabled
priority, conditions (structured), target_category
created_by, created_at, last_used_at
notes, examples, replaced_by_rule_id (optional)
LLMRun (optional but useful)
id, prompt_version, model, ticket_ids
rules_included (ids), raw_response, parsed_output, timestamp

LLM prompt/response contract
Prompt inputs
Ticket chunk (structured)
Allowed categories (controlled vocabulary)
Relevant active rules (and a short global rules section)
Output schema requirement
Output
Per-ticket: category + rationale (and optional confidence)
Optional: “proposed rules” list (clearly labeled as suggestions requiring approval)

Key system behaviors
Rule selection for a ticket
Retrieve active rules matching sender/domain/keywords/metadata
Include top-N by priority and/or relevance (avoid huge prompts)
Ensure rule conflicts are detectable (e.g., multiple matches to different categories)
Applying a decision
When user accepts/edits:
Update ticket category
Append CategorizationEvent
Attribute to llm or human (and link LLMRun if applicable)
Updating rules
Disabling rules never deletes history
Replacing rules links old → new for traceability

Risks + mitigations
Prompt bloat / degraded quality: limit to relevant rules; summarize; strict schema.
Rule conflicts: priority ordering + conflict warnings + audit visibility.
Outdated guidance persists: rule health dashboard + override-triggered review.
Inconsistent categories: enforce controlled category list + validation.

Phased delivery (outline)
Phase 1: TBC Review chunking + apply category in-app + basic Rules CRUD + inject rules into LLM prompt
Phase 2: Category Review screen + audit trail visibility + “add rule from case”
Phase 3: Rule health metrics, conflict detection, guided cleanup workflow


Product Brief: Next-Gen TBC Review & Rules Engine
The Problem & Opportunity
The current process of using Excel exports to review "To Be Confirmed" (TBC) tickets breaks user flow. Users are naturally discovering routing rules mid-chat with Gemini, but they lack a system to capture, test, or enforce those rules.
We need to transition from an Excel-dependent workflow to an in-app, rule-guided feedback loop.
Core Objectives (Goals vs. Non-Goals)
Goals: Chunked TBC ticket review (batches of 10), human-in-the-loop rule management (CRUD), detailed audit trails ("why" a category was picked), and automated flags for outdated/overridden rules.
Non-Goals: Full automation without human oversight, automatic global rule-writing without approval, or replacing existing bulk upload features.
1. Core Workflows & User Journeys
Journey A: The TBC Review Queue (The Core Engine)
Batch Load: System pulls a batch of 10 TBC tickets.
LLM Evaluation: Gemini receives the ticket data alongside only relevant active rules (matched by sender, domain, or keywords).
Human Review: The UI displays Gemini’s suggested category, its rationale, and any newly proposed rules based on current patterns.
Commit: User accepts or edits the decision. The system updates the ticket and logs the audit event.
Journey B: Inline Rule & Context Management
Users can build strict routing rules (IF [Condition] → THEN [Category]) directly from a case or via a dedicated Rules UI.
Lifecycle Control: Rules are never hard-deleted. They are marked as active, disabled, or replaced_by_id to preserve historical integrity.
Journey C: Audit & Quality Assurance
Spot-checking: Managers can filter categorized tickets by date, sender, or "Categorized By" (Rule vs. LLM vs. Manual).
The "Why" Check: A dedicated timeline view displays exactly which rules matched or what the LLM's rationale was at the moment of categorization.
2. System Architecture & Data Schema
Core Data Model
[Ticket] ── (1:N) ── [CategorizationEvent] (Audit Trail)
                            │
                            └── (Optional Links to) ── [LLMRun] & [Rule]


Entity
Key Fields / Schema
Purpose
Ticket
id, sender, subject, body_thread, metadata, current_category
Core data record.
Rule
id, status (active/disabled), priority, conditions (JSON), target_category, replaced_by_rule_id, metrics (override_rate)
Human-maintained routing context.
CategorizationEvent
id, ticket_id, from_category, to_category, source (human/llm/rule), llm_run_id, rationale
The immutable audit trail.
LLMRun
id, prompt_version, model, rules_included (IDs), raw_response
Debugging and prompt quality tracking.

LLM Prompt / Response Contract
Inputs: Structured ticket chunk (10 max) + Controlled vocabulary list (Allowed categories) + Filtered active rules list.
Expected JSON Output:
JSON
{
  "ticket_id": "123",
  "suggested_category": "Billing",
  "rationale": "Matches domain patterns and keyword 'invoice'.",
  "proposed_rules": [{"condition": "sender domain is X", "then_category": "Billing"}]
}


3. Phased Implementation Roadmap
Phase 1: MVP (Core Loop)     ─►   Phase 2: Audit & Inline       ─►   Phase 3: Optimization & Health
• 10-ticket batch UI             • "Add rule from case" button       • Rule health dashboard
• Rules CRUD store               • Category Review / Spot-check UI   • Multi-rule conflict warnings
• Basic rule injection to LLM     • Full historical audit timeline    • Proactive cleanup workflows
Success Metrics
Velocity: Reduced TBC backlog processing time (higher tickets/hour reviewed).
Consistency: Drastic reduction in "category flipping" for identical ticket patterns.
Tool Consolidation: Near-zero reliance on Excel for the TBC review loop.
Rule Health: Downward trend in human overrides of LLM/Rule recommendations.


