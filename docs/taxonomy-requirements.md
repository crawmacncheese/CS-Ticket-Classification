# CS Ticket Taxonomy Requirements

> **Role:** Stable protocol state — category definitions, edge cases, precedence, and compile phrasing.
> **Not:** Per-batch session notes (those live in `docs/sessions/`).
> **Runtime:** This file is **not** read by `/run`. The deterministic classifier uses `classifier_rules.json` + `classify.py`.
> **Compile-time:** Skill and `/rules/compile` auto-inject global precedence + scoped
> sections from this file (plus a live shield weight table) when drafting or refining rules.
> **Version:** Increment `protocol_version` when edge cases or precedence change.

**protocol_version:** 1  
**last_reviewed:** 2026-07-13  
**owner:** taxonomy owner / classifier maintainer  
**workbook_wins:** true — 5-tuple paths must exist in allow-list; Gem 4-tier labels are hints only

---

## How to use this file

| Consumer | When | What to read |
|----------|------|--------------|
| **Christine workflow skill** | Start of prefilter; before proposing rule drafts | Global precedence, sweep cross-refs, edge cases for categories in scope |
| **`/rules/compile`** | Each compile call (auto-inject via `taxonomy_requirements`) | Precedence + edge cases for target category + disambiguation notes |
| **Category audit sweeps** | When sweep match disagrees with classifier | `sweep_id` entries under each category |
| **Session requirements MD** | Each batch review | Link here; do not duplicate stable edge cases |

When chat or audit discovers a new edge case: add it here first, then compile → preview → Confirm to `classifier_rules.json`.

---

## Global precedence (shields — evaluate first)

Order matters. Shield rules use `override: true` and weight ≥ 16.

1. **No Content / live-chat auto-trigger** — subject contains `Conversation with` and body is URL-only or subscribe landing → General Support > No Content - Live chat auto-trigger. **Not** Sales Lead.
2. **Stefan Rule** — moderation friction, deleted comments, biased moderators → Account Management > Comments being block. Beats refund/cancel keywords in the same ticket.
3. **External junk / vendor / HR** — PR pitches, job applications → Junk. Never Upgrade or Sales Leads.
4. **Financial / growth / B2B** — normal weighted rules (billing, refund, cancel, bugs, corp names).

---

## Cross-cutting routing rules

Named rules that apply across multiple categories. Link from category sections; do not duplicate prose.

### Rosetta System Email footer

- **sweep_id:** `rosetta_footer`
- **signals:** description contains `Thanks. Rosetta System Email`
- **target:** Billing & Admin > System Report (B2C path per allow-list)
- **not:** Cancellation Request, Refund Request
- **compile_phrase:** If it contains "Thanks. Rosetta System Email", that is system email — NOT cancellation request. Update: Map those tickets to Billing & Admin > System Report.
- **live_rule_id:** `billing.system_report.rosetta_renewal.b2c`
- **status:** shipped

### Posties / Young Post → B2B segment

- **sweep_id:** `posties_young_post`
- **signals:** any mention of `Posties` or `Young Post` in blob
- **target:** B2B segment (pick matching allow-list 5-tuple for Print/B2B context)
- **not:** B2C Cancellation or Complaint buckets
- **compile_phrase:** Update: If it contains "Posties" or "Young Post", route to B2B segment (any mention).
- **live_rule_id:** partial — `complaint.cancel_posties.b2c` is narrow; segment remap may need new rule
- **status:** gap — audit often finds miscategorizations

### ESP / Print internal notes → B2B

- **sweep_id:** `esp_print`
- **signals:** `ESP-OPP`, `ESP-INV`, print distribution context, internal ESP tags
- **target:** B2B segment
- **compile_phrase:** Update: If it contains "ESP-OPP" or "ESP-INV" or Print distribution context, route to B2B segment / Print.
- **status:** partial in classifier

### Refund + cancel precedence

- **sweep_id:** `refund_precedence`
- **signals:** both `refund` and `cancel` (or equivalent) in same ticket
- **target:** Complaint > Refund > Refund Request (workbook path — validate allow-list)
- **not:** Cancellation Request when refund intent is primary
- **compile_phrase:** Refund precedence: if the ticket contains both "refund" and "cancel", update mapping to Refund Request (not Cancellation).
- **notes:** Christine session prefers Refund; some computed logic historically preferred Cancellation — **resolve once** and document chosen precedence here.
- **status:** conflict to resolve

---

## Core categories

Each category section uses the same field set. Omit optional fields when not applicable.

**Field glossary**

| Field | Meaning |
|-------|---------|
| **path** | Workbook 5-tuple or tier4 label (must resolve via allow-list) |
| **description** | What belongs in this bucket |
| **required_signals** | Strong positive signals (not all required unless stated) |
| **exclude_signals** | If present, route elsewhere (link cross-cutting rule) |
| **edge_cases** | Named exceptions with target override |
| **common_confusions** | Buckets this is often mistaken for |
| **sweep_ids** | Category audit sweeps to run when auditing this bucket |
| **compile_hints** | Extra phrasing for `/rules/compile` |

---

## Cancellation Request

- **path:** Complaint > Refund > Cancellation Request (validate 5-tuple)
- **description:** User-initiated request to cancel subscription or stop auto-renewal; agent-assisted cancel workflows.
- **required_signals:** user asks to cancel, discontinue, stop auto-renewal, unsubscribe (intent from user, not system notification)
- **exclude_signals:**
  - Rosetta System Email footer → see cross-cutting **Rosetta**
  - Invoice / 发票 / PO demand → Invoices and PO request
  - GDPR / delete account → Request to delete account
  - Posties / Young Post → B2B
  - ESP internal notes → B2B
- **edge_cases:**
  - **Auto-renewal disabled confirmation TO user** — still Cancellation (correct); distinguish from Rosetta system emails.
  - **AlipayHK auto-debit webhook** — context-dependent; may be System Report or Cancellation; prefer TBC if ambiguous.
- **common_confusions:** System Report (Rosetta), Refund Request (refund+cancel combo), Request to delete account
- **sweep_ids:** `rosetta_footer`, `esp_print`, `posties_young_post`, `account_deletion`, `invoice_request`, `refund_precedence`
- **compile_hints:** When fixing Cancellation slice, run all sweep_ids before drafting rules.

---

## System Report

- **path:** Billing & Admin > System Report
- **description:** Automated system notifications, payment confirmations, renewal notices, Rosetta-generated emails — not user-initiated service requests.
- **required_signals:** Rosetta footer, Stripe payment completed, payment advice, auto-debit notification without user cancel intent
- **exclude_signals:** explicit user cancel/refund request in same thread (may need split or precedence review)
- **edge_cases:**
  - **Rosetta + cancel keywords** — Rosetta footer wins; route to System Report.
- **common_confusions:** Cancellation Request
- **sweep_ids:** `rosetta_footer`
- **compile_hints:** Use `exclude_blob` for cancel keywords when mapping Rosetta footer.

---

## Refund Request

- **path:** Complaint > Refund > Refund Request
- **description:** User wants money back, billing correction, or refund status — including when cancel and refund appear together.
- **required_signals:** refund, money back, charge dispute, billing error (user-initiated)
- **edge_cases:**
  - **Refund + cancel in same ticket** — Refund Request takes precedence over Cancellation (per Christine session).
  - **Stefan Rule** — moderation context beats refund keywords → Account Management.
- **common_confusions:** Cancellation Request, Technical Bug
- **sweep_ids:** `refund_precedence`
- **compile_hints:** Document precedence in rule `notes` when encoding refund+cancel combo.

---

## Request to delete account

- **path:** Account Management > Request to delete account
- **description:** GDPR, data erasure, permanent account deletion requests.
- **required_signals:** GDPR, delete my account, data erasure, right to be forgotten
- **exclude_signals:** mere unsubscribe / cancel subscription without deletion language
- **edge_cases:** Account deletion language inside Cancellation-heavy thread → deletion intent wins.
- **common_confusions:** Cancellation Request
- **sweep_ids:** `account_deletion`
- **compile_phrase:** Update: Map tickets mentioning "GDPR", "delete my account", or "data erasure" to Account Management > Request to delete account.
- **status:** gap — dedicated live rule may be missing

---

## Invoices and PO request

- **path:** Billing & Admin > Invoices and PO request
- **description:** User requests invoice, receipt, PO, tax document — not cancellation.
- **required_signals:** invoice, 发票, PO, purchase order, receipt for payment
- **exclude_signals:** cancel/unsubscribe as primary intent without invoice language
- **common_confusions:** Cancellation Request, System Report
- **sweep_ids:** `invoice_request`
- **compile_phrase:** Update: Map tickets mentioning "invoice" or "发票" or "PO" to Billing & Admin > Invoices and PO request.
- **status:** gap — dedicated live rule may be missing

---

## No Content - Live chat auto-trigger

- **path:** General Support > No Content - Live chat auto-trigger
- **description:** Zopim/live-chat auto-triggers with URL-only or empty substantive body.
- **required_signals:** subject `Conversation with`, zopim_chat tag, subscribe URL patterns per computed rules
- **exclude_signals:** sales lead phrases, substantive user question in body
- **edge_cases:**
  - **CRITICAL:** Do NOT mark Conversation with + URL-only as Sales Lead.
- **common_confusions:** Sales Leads, Access Loop
- **compile_hints:** Shield rule — `override: true`, weight ≥ 20

---

## Disambiguation (Gem labels → workbook)

| Client / Gem label | Workbook path (allow-list wins) |
|--------------------|----------------------------------|
| Service Task > Need help for Cancellation | Complaint > Refund > Cancellation Request |
| Account Management > Comments blocked | Account Management > Comments being block |

Add rows when audit finds systematic label drift.

---

## Changelog

| Date | Version | Change |
|------|---------|--------|
| 2026-07-13 | 1 | Initial template from Christine June 24 session + gemini-conversation-patterns |
