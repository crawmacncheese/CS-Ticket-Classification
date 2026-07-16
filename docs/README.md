# Documentation index

Navigation for the CS Ticket Automation (`cs-tickets`) project. Start with [HANDOFF.md](./HANDOFF.md) if you are taking over maintenance.

---

## Start here

| Document | Audience | Purpose |
|----------|----------|---------|
| [HANDOFF.md](./HANDOFF.md) | New maintainers | Onboarding, daily workflows, ops checklist |
| [flows.md](./flows.md) | Everyone | Mermaid diagrams for classify, portal, Learn, Drive, deploy |
| [../README.md](../README.md) | Developers | Quickstart, CLI, portal, runtime config |
| [../CONTEXT.md](../CONTEXT.md) | Everyone | Domain glossary (allow-list, TBC, Training, etc.) |

---

## Product and architecture

| Document | Purpose |
|----------|---------|
| [prd.md](./prd.md) | Product requirements, metrics, phases |
| [design.md](./design.md) | Technical design: pipeline, classifier, deployment |
| [configuration.md](./configuration.md) | Environment variables and runtime paths |
| [ops-runbook.md](./ops-runbook.md) | Deploy, rollback, production smoke checks |
| [api-reference.md](./api-reference.md) | Portal HTTP routes |
| [architecture/agent-skills-framework.md](./architecture/agent-skills-framework.md) | Review chat, atomic skills, Consistency Gateway |
| [taxonomy-requirements.md](./taxonomy-requirements.md) | Stable category protocol for rule compile |
| [prd-phase2-learning-feedback.md](./prd-phase2-learning-feedback.md) | Phase 2 learning / feedback direction |

---

## Operator and analyst workflows

| Topic | Primary doc | Portal path |
|-------|-------------|-------------|
| Classify an export | [README](../README.md) | `/` → `/run` |
| Download Excel results | [README](../README.md) | `/download/{run_id}` |
| TBC trend dashboard | [plans/2026-06-11-tbc-trend-dashboard.md](./plans/2026-06-11-tbc-trend-dashboard.md) | `/dashboard` |
| Learn New (allow-list + rules) | [README](../README.md) | `/learn` |
| Explicit rule authoring | [plans/2026-07-03-explicit-rule-authoring.md](./plans/2026-07-03-explicit-rule-authoring.md) | `/rules`, `/rules/new` |
| Category audit | [plans/2026-07-07-category-audit-workflow.md](./plans/2026-07-07-category-audit-workflow.md) | `/run/{id}/category_audit` |
| TBC queue | [plans/2026-07-06-tbc-queue-review-focus-notes.md](./plans/2026-07-06-tbc-queue-review-focus-notes.md) | `/run/{id}/tbc_queue` |
| Christine orchestration | [plans/2026-07-13-christine-orchestration-skill.md](./plans/2026-07-13-christine-orchestration-skill.md) | Review chat + Cursor skill |

---

## Code layout

| Path | Role |
|------|------|
| `src/cs_tickets/` | Application package (pipeline, portal, classifier) |
| `tests/` | pytest suite |
| `tools/` | Offline audit, TBC trends, allow-list test harness |
| `scripts/` | Portal session runners (Christine demo / replay) |
| `.cursor/skills/` | Cursor Agent skill definitions (mirror portal APIs) |
| `doc/` | Committed taxonomy CSV + reference workbook |
| `references/` | Bootstrap seeds when `runs/live/` is empty |
| `runs/live/` | Runtime config cache (gitignored) |
| `k8s/` | Kubernetes manifests (dev + prod) |

Module-level detail: [design.md §3](./design.md#3-component-overview) and [README § Key modules](../README.md#key-modules).

---

## Review sessions

Per-batch Christine review logs live under [sessions/](./sessions/). See [sessions/README.md](./sessions/README.md).

---

## Implementation plans (historical)

Dated plans under [plans/](./plans/) record feature design, decisions, and implementation notes (`*-notes.md`). See [plans/README.md](./plans/README.md) for **current vs superseded** index.

Useful entry points:

- [2026-05-14-tier-classifier-improvements.md](./plans/2026-05-14-tier-classifier-improvements.md) — rule batches and TBC baselines
- [2026-06-09-allowlist-testing-architecture.md](./plans/2026-06-09-allowlist-testing-architecture.md) — allow-list impact testing
- [2026-07-15-atomic-skills-architecture.md](./plans/2026-07-15-atomic-skills-architecture.md) — skills migration rationale

---

## Testing

| Resource | Purpose |
|----------|---------|
| [../testcase.md](../testcase.md) | Manual test plan for allow-list Training |
| [README § Tests](../README.md#tests) | pytest and golden fixtures |
| [configuration.md § Verification](./configuration.md#verification-checklist) | Post-deploy smoke checks |

---

## Related repos and deployment

- **Production image:** built from this repo via GitLab CI → Kaniko → GKE (`k8s/prod/`).
- **Live config on Drive:** folder IDs in `.env.example` and [configuration.md](./configuration.md).
- This checkout is the **v2** training / portal codebase. If your org uses a monorepo with a separate v1 Learn portal, confirm layout with your team — paths like `../v1/` may not exist in every export of this repo.
