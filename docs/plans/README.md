# Implementation plans index

Dated design and implementation records under `docs/plans/`. Use this index to find **current** specs vs **historical** context.

**Rule of thumb:** For how the system works today, prefer [HANDOFF.md](../HANDOFF.md), [design.md](../design.md), and [architecture/agent-skills-framework.md](../architecture/agent-skills-framework.md). Plans explain *why* and *how we built it*; some are superseded.

Companion `*-notes.md` files capture implementation rationale — read the main plan first.

---

## Status legend

| Tag | Meaning |
|-----|---------|
| **Current** | Still authoritative for the shipped feature |
| **Historical** | Implemented; kept for audit trail — may describe interim UX |
| **Superseded** | Replaced by a later plan — see pointer |
| **Backlog** | Not fully shipped or ongoing tuning |

---

## Current — active features (2026-07)

| Plan | Topic | Notes |
|------|-------|-------|
| [2026-07-15-atomic-skills-architecture.md](./2026-07-15-atomic-skills-architecture.md) | Atomic skills migration | **Current** — see also [agent-skills-framework.md](../architecture/agent-skills-framework.md) |
| [2026-07-13-christine-orchestration-skill.md](./2026-07-13-christine-orchestration-skill.md) | Christine orchestrator | **Current** |
| [2026-07-07-category-audit-workflow.md](./2026-07-07-category-audit-workflow.md) | Category audit workbench | **Current** |
| [2026-07-03-explicit-rule-authoring.md](./2026-07-03-explicit-rule-authoring.md) | Rules chat + compile | **Current** |
| [2026-07-06-christine-workflow-decisions.md](./2026-07-06-christine-workflow-decisions.md) | Orchestration decisions | **Current** reference |
| [2026-06-16-drive-live-config-alignment.md](./2026-06-16-drive-live-config-alignment.md) | Drive `runs/live/` sync | **Current** for deployment |
| [2026-06-11-tbc-trend-dashboard.md](./2026-06-11-tbc-trend-dashboard.md) | TBC trends dashboard | **Current** |
| [2026-05-14-tier-classifier-improvements.md](./2026-05-14-tier-classifier-improvements.md) | Classifier rule batches | **Backlog** — living tuning log |

---

## Superseded or merged

| Plan | Superseded by | Notes |
|------|---------------|-------|
| [2026-07-07-christine-category-audit-workflow.md](./2026-07-07-christine-category-audit-workflow.md) | [2026-07-13-christine-orchestration-skill.md](./2026-07-13-christine-orchestration-skill.md) | Merged into Christine skill plan |
| [2026-07-02-category-review-and-drill-down.md](./2026-07-02-category-review-and-drill-down.md) | [2026-07-07-category-audit-workflow.md](./2026-07-07-category-audit-workflow.md) | Early category review UX |
| [2026-06-10-portal-ux-improvement.md](./2026-06-10-portal-ux-improvement.md) | [2026-07-15-portal-ux-declutter.md](./2026-07-15-portal-ux-declutter.md) | UX iteration |
| [2026-06-06-allowlist-training-feature.md](./2026-06-06-allowlist-training-feature.md) | Learn New (`/learn`) + [prd-phase2](../prd-phase2-learning-feedback.md) | **Training** renamed/redirects to Learn |
| [2026-06-09-training-rule-proposals.md](./2026-06-09-training-rule-proposals.md) | Explicit rules + Learn confirm path | Partial merge |

---

## Historical — shipped, archive value

These document delivered work. Behaviour may have changed in later UX passes.

| Plan | Topic |
|------|-------|
| [2026-07-15-portal-ux-declutter.md](./2026-07-15-portal-ux-declutter.md) | Portal nav / declutter |
| [2026-06-25-commit-verdict-checklist.md](./2026-06-25-commit-verdict-checklist.md) | Confirm checklist |
| [2026-06-24-ticket-preview-tbc-reasons.md](./2026-06-24-ticket-preview-tbc-reasons.md) | TBC reason buckets in preview |
| [2026-06-17-learn-preview-beginner-ux.md](./2026-06-17-learn-preview-beginner-ux.md) | Learn wizard UX |
| [2026-06-12-hybrid-allowlist-update.md](./2026-06-12-hybrid-allowlist-update.md) | Hybrid allow-list updates |
| [2026-06-10-training-ux-wizard-and-impact-preview.md](./2026-06-10-training-ux-wizard-and-impact-preview.md) | Training wizard |
| [2026-06-10-classifier-coverage-thread-and-rules.md](./2026-06-10-classifier-coverage-thread-and-rules.md) | Thread enrichment + coverage |
| [2026-06-09-batch-allowlist-impact-analysis.md](./2026-06-09-batch-allowlist-impact-analysis.md) | Batch allow-list tests |
| [2026-06-09-allowlist-testing-architecture.md](./2026-06-09-allowlist-testing-architecture.md) | Allow-list test architecture |
| [2026-06-08-allowlist-training-fixes.md](./2026-06-08-allowlist-training-fixes.md) | Training bug fixes |

Each has a matching `*-notes.md` where listed in the repo.

---

## LLM / conversation design (reference)

| Plan | Topic |
|------|-------|
| [2026-07-03-gemini-conversation-patterns.md](./2026-07-03-gemini-conversation-patterns.md) | Conversation patterns |
| [Gemini-update-notes.md](./Gemini-update-notes.md) | Provider notes |
| [2026-07-06-tbc-queue-review-focus-notes.md](./2026-07-06-tbc-queue-review-focus-notes.md) | TBC queue + focus |

LLM is used for **compile / suggest only**, not `/run` classification ([agent-skills-framework.md](../architecture/agent-skills-framework.md)).

---

## Adding a new plan

1. Name: `YYYY-MM-DD-short-topic.md` (+ optional `*-notes.md`).
2. Link from this README under **Current** or **Historical**.
3. When superseding an older plan, add a row to **Superseded or merged** above.
4. Promote stable operator facts into [HANDOFF.md](../HANDOFF.md) or [design.md](../design.md) — plans are not the primary onboarding path.
