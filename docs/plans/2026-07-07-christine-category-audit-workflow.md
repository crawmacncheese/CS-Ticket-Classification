# Christine Category Audit Workflow — Reference Excerpt

> **Status:** Captured from live review session (June 24 batch, B2C segment).  
> **Purpose:** Preserve the **category audit** loop Christine runs in Gemini so the portal can mirror it natively.  
> **Implementation plan:** [2026-07-07-category-audit-workflow.md](./2026-07-07-category-audit-workflow.md)  
> **Related:** [2026-07-06-christine-workflow-decisions.md](./2026-07-06-christine-workflow-decisions.md) (TBC loop), [2026-07-02-category-review-and-drill-down.md](./2026-07-02-category-review-and-drill-down.md) (drill-down UI), [2026-07-03-gemini-conversation-patterns.md](./2026-07-03-gemini-conversation-patterns.md).

---

## What this workflow is (vs TBC queue)

Christine runs **two** review loops:

| Loop | Input | Goal |
|------|-------|------|
| **TBC queue** | Tickets with `fallback_used` / manual-review tier | Resolve ambiguous tickets → propose rules |
| **Category audit** *(this doc)* | Tickets **already classified** into a category bucket | Spot miscategorizations, apply segment/routing rules, produce weekly report |

The conversation excerpt below is the **category audit** loop on already-classified B2C buckets.

---

## Example session (June 24 batch)

### Step 1 — Pick segment + categories

User requests review of B2C categories:

1. Access Loop and Bug
2. Cancellation
3. Refund
4. UI/UX Enquiry

Christine returns per category:

- **Volume** in batch
- **Insights** (pattern summary)
- **Representative examples** (3 ticket IDs + one-line context)

### Step 2 — Drill into one category: list all tickets with full content

User: *"list the ticket no. and the content"* for Access Loop and Bug.

Christine lists **every** ticket in the bucket:

| Field per ticket |
|------------------|
| Ticket # |
| Subject |
| Full description / thread context |
| Agent resolution notes (when relevant) |

**8 tickets** in Access Loop and Bug — all read and summarized individually.

### Step 3 — Move to next category; validate + recategorize

User: *"let's move to Cancellation, read thru ticket content, see if any recategorization is needed."*

Christine:

1. Lists first 10 tickets with full conversations
2. Gives per-ticket **Verdict: Correct** or flags miscategorization
3. User corrects: *"if it contains Rosetta System Email, that is system email — NOT cancellation request"*
4. Christine re-scans **all** cancellation tickets, finds 17 Rosetta system notifications → moves to **Billing & Admin > System Report**
5. Remaining count updates (33 → 19 → 16 after further sweeps)

### Step 4 — Cross-cutting validation sweeps

After user corrections, Christine runs **global scans** across the remaining set:

| Sweep | Trigger | Action |
|-------|---------|--------|
| **Rosetta footer** | `"Thanks. Rosetta System Email"` in description | → System Report (not Cancellation) |
| **ESP / Print** | `ESP-OPP-…`, internal ESP tags, Print context | → B2B segment |
| **Posties / Young Post** | Any mention | → B2B segment (new rule mid-session) |
| **Account deletion** | GDPR / data erasure language | → Account Management > Request to delete account |
| **Invoice** | User demanding invoice (not cancel) | → Billing & Admin > Invoices and PO request |
| **Refund precedence** | Cancel + refund in same ticket | → Complaint > Refund > Refund Request |

### Step 5 — Final list with corrections applied

Christine outputs the **final** genuine cancellation list (ticket # + full content) after all sweeps.

**Final B2C Cancellation tickets (after corrections):**

| Ticket | Notes |
|--------|-------|
| #169894 | Auto-renewal disabled confirmation — Correct |
| #169942 | AlipayHK auto-debit cancellation confirmation to user — Correct |
| #169950 | Agent helping user cancel — Correct |
| #170076 | Auto-renewal disabled confirmation — Correct |
| #170148 | User asks discontinue at expiry — Correct |
| #170224 | Disable auto-renewal follow-up — Correct |
| #170358 | How to disable auto-renew (not cancel subscription) — Correct |
| #170361 | "I do not want auto renewal" — Correct |

**Recategorized out of Cancellation:**

| Ticket | Was | Now |
|--------|-----|-----|
| #169849 | Cancellation | B2B (ESP internal note) |
| #169856, #169855, … (17) | Cancellation | System Report (Rosetta) |
| #170013 | Cancellation | Request to delete account |
| #170032 | Cancellation | Invoices and PO request |
| #170051, #170151, #170156 | Cancellation | B2B (ESP) or Refund |
| #170092, #170133 | Cancellation | B2B (Posties / Young Post) |
| #170209 | Cancellation | Request to delete account |

### Step 6 — Offer next steps

Christine asks: drill down further, compare to previous batches, or move to next category (Refund, UI/UX).

---

## Rules locked from this session

These are **audit-time routing rules** Christine applied (some overlap with classifier / compile corpus):

```text
1. "Thanks. Rosetta System Email" footer → Billing & Admin > System Report (NOT Cancellation)
2. ESP / Print references (ESP-OPP-…, internal ESP tags) → B2B segment
3. Posties / Young Post → B2B segment (any mention)
4. Account deletion + data erasure (GDPR) → Account Management > Request to delete account
5. Invoice demand (e.g. 发票 / invoice request) → Billing & Admin > Invoices and PO request
6. Cancel + refund in same ticket → Refund Request takes precedence
7. AlipayHK auto-debit webhook (without Rosetta) → still Cancellation or System Report (context-dependent)
8. Auto-renewal disabled confirmation emails TO user → Cancellation Request (correct)
```

---

## Portal parity map

| Christine step | Native feature today | Gap |
|----------------|---------------------|-----|
| Pick B2C + category list | TBC queue NL focus (`review B2C 1. access loop 2. cancellation`) or category drill-down dropdown | Category audit uses **classified** rows, not TBC — drill-down works but no numbered-category NL parser on results page |
| Volume + insights + examples | Tier breakdown table on `/run` results | No narrative **insights** paragraph; no auto-picked representative examples |
| List all tickets with **full content** | Ticket preview detail pane (per-row click) | No **bulk list** export of # + subject + full thread for entire category in one view |
| Per-ticket verdict (Correct / Recategorize) | Explain pane shows rule evidence | No **verdict UI**; no one-click "flag miscategorized" |
| User correction → global re-scan | NL focus + batch rule draft (`tbc_draft_rule_for_filter`) | Re-scan is **manual** — no "apply rule → show all matches in this category → bulk preview impact" on classified buckets |
| Update master dataset | Confirm rule → `reclassify` run | No direct row-level relabel (Phase 1 decision); corrections require **rule + reclassify**, not instant bucket move |
| Cross-cutting ESP / Posties / Rosetta sweeps | Partial in `classify.py` + `classifier_rules.json` | See **Rule implementation gaps** below |
| Compare to previous batches | — | **Not implemented** |
| Weekly report narrative | — | Phase C backlog |
| Duplicate webhook detection (#169855 + #169856) | — | **Not implemented** |

---

## Rule implementation gaps (classifier vs Christine)

| Rule | Classifier status | Gap |
|------|-------------------|-----|
| Rosetta System Email → System Report | `billing.system_report.rosetta_renewal.b2c` + `_is_rosetta_system_email()` | Shipped; golden reclassify acceptance still open |
| ESP → B2B | `_apply_esp_b2b_segment()` on `ESP-OPP` / `ESP-Inv` patterns | Internal CS notes with ESP may be missed if not in export blob |
| Posties / Young Post → B2B | `complaint.cancel_posties.b2c` only (narrow `any_blob`) | **No segment remap** for general Posties/Young Post mentions |
| Refund > Cancellation | `computed:refund_cancel.b2c` prefers cancel when both present | Christine prefers **Refund** — **conflict to resolve** (noted in gemini-conversation-patterns.md) |
| Account deletion | — | **No dedicated rule** |
| Invoice demand | — | **No dedicated rule** (may fall through to TBC or wrong bucket) |
| Auto-renewal disabled confirmation | Cancellation scoring | Generally correct; distinguish from Rosetta system emails |

---

## What we need to build to mirror this workflow

### High priority (category audit parity)

1. **Category audit mode on run results** — Filter classified (non-TBC) tickets by category; show count + list all ticket IDs in bucket (not capped at preview 200 for export).
2. **Bulk ticket content view** — For a category slice: table of `# | subject | description excerpt | full thread expand` so analyst can read all tickets without clicking one-by-one (Christine's list format).
3. **Validation sweep panel** — Run named checks against current category slice:
   - "Contains Rosetta System Email"
   - "Contains ESP / Print"
   - "Contains Posties / Young Post"
   - "Account deletion language"
   - "Invoice request language"
   
   Output: list of matching ticket IDs + suggested target tier + "draft rule" CTA.
4. **Recategorization path for audit** — Either:
   - **Phase 2 run-scoped relabel** (quick report fix), or
   - **Rule propose → preview matches in slice → Confirm → reclassify** with before/after counts for the category.
5. **Refund vs Cancellation precedence** — Align classifier with Christine: when both intents present, prefer Refund Request.

### Medium priority (reporting + efficiency)

6. **Category slice CSV export** (Phase C item 8) — Download current category filter as XLSX/CSV.
7. **Representative examples** — Auto-pick 3 diverse tickets per category (by subject length, sender domain, tag variety) for weekly summary template.
8. **Duplicate / near-duplicate detection** — Same sender + same subject pattern within batch (webhook retries).
9. **Batch-over-batch comparison** — Store run summaries; show volume delta per category vs last run.

### Lower priority / already planned

10. **Weekly narrative summary** — Phase C; optional LLM later.
11. **`GET /rules/export`** — Portable rule set ("master prompt" equivalent).
12. **Random sample N** — Category review Phase 3.

---

## Suggested portal flow (target)

```text
1. POST /run → results
2. Tier breakdown → click "Access Loop or Bug" (or NL: "review B2C cancellation")
3. Category audit panel:
     - N tickets in bucket
     - [List all] [Export CSV] [Run validation sweeps]
4. Read tickets (bulk list or chunk of 10)
5. Flag miscategorizations OR propose rule from example ticket
6. Validation sweep → "17 tickets match Rosetta" → Draft rule → Preview → [lead] Confirm
7. Reclassify run → category count updates
8. Repeat for next category; Finish → weekly summary template
```

---

## Acceptance criteria (category audit)

- [ ] Analyst can list **all** tickets in a classified category with full content (not only TBC queue).
- [ ] Named validation sweeps (Rosetta, ESP, Posties, delete-account, invoice) return match lists against current category slice.
- [ ] Proposed rule from sweep shows **match count in slice** before Confirm.
- [ ] After Confirm + reclassify, category bucket count decreases for swept tickets.
- [ ] Refund + cancel combo routes to Refund Request (aligned with Christine).
- [ ] Posties / Young Post mentions remap to B2B segment globally.
- [ ] Category slice exportable without re-uploading Zendesk export.

---

## References

- [2026-07-06-christine-workflow-decisions.md](./2026-07-06-christine-workflow-decisions.md) — TBC loop, Model B roles, no Phase 1 relabel
- [2026-07-06-tbc-queue-review-focus-notes.md](./2026-07-06-tbc-queue-review-focus-notes.md) — NL focus, batch rules (closest native feature today)
- [2026-07-02-category-review-and-drill-down-notes.md](./2026-07-02-category-review-and-drill-down-notes.md) — drill-down UI (Phase 1–2 done)
- [2026-07-03-explicit-rule-authoring.md](./2026-07-03-explicit-rule-authoring.md) — compile + Confirm
- [rule_compile_corpus.py](../../src/cs_tickets/rule_compile_corpus.py) — Rosetta golden fixture
