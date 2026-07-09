# Client Gemini Conversation Patterns (from export PDF)

> **Source:** `Gemini.pdf` — CS team's historical chats with **CS Christine** custom Gem (320 pages).  
> **Purpose:** Inform native portal UX and `rule_compile` prompts. **Not** runtime classification input for `/run`.

**End state:** Replicate these **interaction patterns** in the portal with deterministic classify + LLM **compile-only**.

**Role model (2026-07-06):** [2026-07-06-christine-workflow-decisions.md](./2026-07-06-christine-workflow-decisions.md) — analysts run TBC queue + propose rules; maintainers/leads **Confirm** live.

---

## Core loop (repeated dozens of times)

```text
1. Upload export (CSV/JSON) + paste Master Categorization Protocol (V13…V37+)
2. Gem returns: summary table + full tagged file + TBC count
3. User: "show me tickets needing manual review" / "next 10 TBC"
4. Gem: table of 10 tickets — ID | quote | why TBC | suggested tier
5. User confirms or corrects ("#169856 is NOT cancellation — Rosetta footer")
6. Gem: "Update: Map 'phrase' → Tier3 > Tier4" + bumps protocol version
7. Repeat until TBC ≈ 0; user saves latest Master Prompt for next batch
```

**Portal equivalent:**

| Gemini step | Native feature |
|-------------|----------------|
| Paste master prompt | `runs/live/classifier_rules.json` + business spec doc |
| Categorize batch | `/run` |
| Show 10 TBC | TBC filter + chunk UI (plan: TBC queue) — **shipped**; see [2026-07-06-tbc-queue-review-focus-notes.md](./2026-07-06-tbc-queue-review-focus-notes.md) |
| Suggested mapping table | Explain pane + compile chat |
| "Update: Map X → Y" | Conversational rule compile → Confirm |
| Save prompt V34 | Confirm rule to live store |

---

## Master prompt evolution (what they actually maintain)

- **Versioned prose protocol** (V13 → V14 → V15 → V19 → V28 → V34 → V37…), not isolated rules.
- Each TBC review session adds **edge cases** → prompt bump.
- User explicitly asked: *"can you give me the master prompt?"* — portable **session state**.
- User corrected rushed prompts: *"did u read my file before u write the prompt? dun rush"* — rules must be grounded in **manual workbook**, not generic.

**Implication for `rule_compile`:** inject **allow-list tiers** + **existing live rules** + **short precedence doc** (see below), not a blank slate.

---

## Precedence / "shield" rules (check FIRST)

From V18/V34 protocol — order matters:

1. **No Content / live-chat auto-trigger** — subject `Conversation with` + URL-only body → not Sales Lead.
2. **Moderation friction ("Stefan Rule")** — deleted comments / biased moderators → Account Management, **even if user mentions refund/cancel**.
3. **External junk / vendor / HR** — PR pitches, job applications → Junk, **never Upgrade or Sales Leads**.
4. Then financial/growth categories (refund, cancel, price mismatch, sales, bugs…).

**Implication:** `RuleSpec` needs **`precedence`** (or `override` + ordering) and **`exclude_blob`** for CRITICAL negatives. Compiler must assign shield rules higher priority.

---

## How rules are stated in chat (compile training examples)

Users and Gem converge on this phrasing:

```text
Update: Map "how can i renew my scmp" or "renewal reminder" to Sales Leads > Rate or Renewal Inquiry.
Update: Map "Stripe payment completed" to Billing & Admin > System Report.
Update: Map "payment advice note" to Billing & Admin > System Report.
If it contains Rosetta System Email, that is system email — NOT cancellation request.
CRITICAL: Do NOT mark Conversation with + URL-only as Sales Lead.
```

**Named rules:** e.g. **Stefan Rule** (moderation vs refund keyword trap).

**Implication:** `rule_compile` system prompt should include few-shot examples in this **Update: Map** format; parser accepts paraphrases.

---

## TBC review table shape (UX target)

Gem consistently shows:

| Ticket ID | Context / quote | Why TBC | Suggested classification |
|-----------|-----------------|---------|--------------------------|
| #167391 | "paid but can't access article" | Didn't trigger access rule | Complaint > Technical Bug > Access Loop or App Bug |

User then: *"the rest ok"* or corrects specific IDs.

**Portal target:** TBC queue row → explain → chat prefill: *"When tickets look like #167391, they should be Access Loop or App Bug because…"*

---

## Tier / taxonomy notes from sessions

- Gemini uses **4-tier** labels; portal uses **5-tuple** (`Granular_Tech_UI_Type`). Compile step **must map** to allow-list paths.
- Frequent B2B triggers in prompts: `ESP`, `e-paper`, corporate names (HKEX, DBS, Sino Group…), growing list per batch.
- **Print** stream added as Tier 2 variant in later sessions — taxonomy may drift; compile must validate against `AllowList`.
- Gemini paths sometimes differ from workbook (e.g. `Service Task > Need help for Cancellation` vs `Complaint > Refund > Cancellation Request`) — **workbook/allow-list wins**.

---

## High-value rule patterns to encode (from PDF + master prompt V34)

| Pattern | Target tier (validate allow-list) | Notes |
|---------|-----------------------------------|-------|
| Rosetta System Email footer | Billing & Admin > System Report | User-corrected misclassification as cancel |
| AlipayHK auto-debit **notification** | System Report or TBC | vs user-initiated cancel without Rosetta |
| Stripe payment completed | System Report | |
| Conversation with + URL only | General Support > No Content - Live chat auto-trigger | CRITICAL: not Sales Lead |
| Moderation / deleted comments | Account Management (Comments blocked) | Stefan Rule; beats refund keywords |
| Refund + cancel in same ticket | Refund Request | Client master prompt; portal currently prefers Cancellation — **resolve** |
| Posties / Young Post | B2B segment | In latest master prompt; partial in classifier |
| `privaterelay.appleid.com` | Context for refund/cancel tickets | Sender signal |

---

## What NOT to replicate from Gemini

- **Full-batch LLM categorization** on `/run` (replace with deterministic engine).
- **Prompt version as only rule store** (replace with `RuleSpec` JSON + optional prose spec appendix).
- **Unbounded corporate keyword lists** without allow-list validation.
- **Claiming 0 TBC** without golden tests (Gem sometimes overconfident).

---

## References

- [Gemini-update-notes.md](./Gemini-update-notes.md) — product brief
- [2026-07-03-explicit-rule-authoring.md](./2026-07-03-explicit-rule-authoring.md) — implementation plan
- [2026-07-02-category-review-and-drill-down.md](./2026-07-02-category-review-and-drill-down.md) — audit UI (done)
