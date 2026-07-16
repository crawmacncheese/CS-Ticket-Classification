# Product Requirements Document — CS Ticket Automation

**Product:** CS Ticket Automation (`cs-tickets`)  
**Owner:** SCMP Customer Support / ITBS (engineering)  
**Status:** Phase 2 — portal maintenance workflows shipped; ongoing classifier tuning  
**Last updated:** 2026-07-16

---

## 1. Problem statement

SCMP support receives a high volume of Zendesk tickets across B2C digital, B2B print, billing, logistics, and noise (PR, spam, system notifications). Analysts maintain a **master categorization sheet** with a five-level tier taxonomy (`Tier1_Segment` through `Granular_Tech_UI_Type`). Manual tagging is slow, inconsistent, and hard to scale when exports contain hundreds of tickets per batch.

The business needs a **repeatable, explainable** way to turn Zendesk NDJSON exports into master-sheet rows with tier columns filled in—reducing manual review while keeping invalid categories impossible at the output boundary.

---

## 2. Goals and success metrics

### Primary goals

| Goal | Description |
|------|-------------|
| **Automate tier assignment** | Map each ticket to an allow-listed 5-tuple tier classification. |
| **Preserve taxonomy integrity** | Never emit a tier combination outside the approved allow-list. |
| **Explain decisions** | Support audit of why a ticket received a tier (rules, scores, fallbacks). |
| **Operational surfaces** | CLI for batch jobs; web portal for upload, review workbenches, rule maintenance, and Excel download. |

### Success metrics

| Metric | Target (direction) | Notes |
|--------|------------------|-------|
| **TBC (Manual Review) rate** | Decrease over time | Baseline ~21–29% on recent exports; post–rule batch ~14–20%. |
| **Classifier warnings** | Near zero | Coercion / allow-list violations should be rare. |
| **Processing throughput** | Full export in minutes | Streaming NDJSON; no ML inference latency. |
| **Rule maintainability** | Add rules without code deploy (where possible) | JSON `RuleSpec`, Rules chat compile, Learn confirm; computed rules for disambiguation. |

### Non-goals

- Replacing Zendesk as the system of record.
- Fully automated closure or routing of tickets without human review.
- **LLM/ML-based classification on the `/run` hot path** (LLM is allowed for rule *drafting* and optional TBC suggestions only).
- Fuzzy matching against taxonomy labels without explicit signals.
- Auto-commit of rule or allow-list changes without human Confirm.

---

## 3. Users and stakeholders

| Persona | Needs |
|---------|--------|
| **CS analyst** | Upload export, review tier breakdown, TBC queue, category audit, download Excel. |
| **CS team lead** | Confirm rule and allow-list changes, preview impact, revert bad promotes. |
| **Operations engineer** | Run CLI in CI or locally; deploy portal to dev/prod Kubernetes. |
| **Taxonomy owner** | Update taxonomy protocol; review Learn New commits to live config on Drive. |
| **Classifier maintainer** | Add rules from TBC audits; Rules chat; run `tools/audit_classifier.py`; Christine sessions. |

---

## 4. User stories

### Must have (delivered)

1. **As an analyst**, I upload a Zendesk NDJSON export and receive an Excel workbook with all master columns plus a tier breakdown sheet.
2. **As an engineer**, I run `cs-tickets-pipeline` against a file path and write a CSV of categorized tickets.
3. **As a maintainer**, I add data-driven rules in `classifier_rules.json` for high-confidence tag/text/url patterns.
4. **As a maintainer**, I audit TBC rate and top fallback tags/subjects on a sample export before merging rule changes.
5. **As a taxonomy owner**, I know that only tier tuples present in the workbook, taxonomy CSV, or pipeline fallbacks can appear on output.

### Phase 2 — delivered (portal maintenance)

6. **As an analyst**, I review category buckets on a classified run and drill into mismatches (Category audit).
7. **As an analyst**, I work through TBC tickets in a queue with filters, explanations, and optional AI suggestions.
8. **As a maintainer**, I draft routing rules in natural language, preview impact on a live run, and hand off to a lead for Confirm.
9. **As a lead**, I Confirm accepted rules and allow-list tuples into live config on Drive without redeploying the image.
10. **As a maintainer**, I revert the last Learn confirm when `config_version` still matches.
11. **As a maintainer**, I run Christine orchestration (Cursor skill or session runner) against the same portal APIs.

### Should have (partial / in progress)

12. **As a maintainer**, I reduce TBC for recurring patterns without increasing misclassification.
13. **As an analyst**, I understand scoring and TBC fallback (portal docs + README + HANDOFF).

### Could have (future)

14. **As an analyst**, I trigger categorization from Google Sheets / Apps Script against a hosted API.
15. **As a maintainer**, I classify reply threads using parent ticket tags or full conversation text by default.
16. **As a maintainer**, I label ambiguous buckets once, then encode stable rules.
17. **As an analyst**, I use a persistent run store across portal replicas (today: in-memory, ephemeral).

---

## 5. Functional requirements

### 5.1 Inputs

| ID | Requirement |
|----|-------------|
| FR-IN-01 | Accept Zendesk API ticket JSON, **one object per line** (NDJSON). |
| FR-IN-02 | Load allow-list from `doc/Taxonomy.csv`, `doc/CS_ticket_new_categorizations.xlsx`, and pipeline fallback tuples in code. |
| FR-IN-03 | Load classifier rules from packaged `classifier_rules.json`. |

### 5.2 Processing

| ID | Requirement |
|----|-------------|
| FR-PR-01 | Flatten each ticket to `BASE_COLUMNS` (ids, subjects, description, tags as JSON string, etc.). |
| FR-PR-02 | Score allow-listed tier 5-tuples using weighted rules on tags, subject, description, and URL. |
| FR-PR-03 | Accept a winning tier only if score ≥ threshold and (high confidence OR sufficient margin over runner-up). |
| FR-PR-04 | If no acceptable winner, assign **B2B TBC** when print-support context detected, else **B2C TBC**. |
| FR-PR-05 | Expose `classify_row_with_explanation()` with rule evidence and candidate scores. |
| FR-PR-06 | Stream rows without loading entire export into memory. |

### 5.3 Outputs

| ID | Requirement |
|----|-------------|
| FR-OUT-01 | Emit rows conforming to `MASTER_COLUMNS` (base fields + five tier columns). |
| FR-OUT-02 | CLI writes CSV to a specified path. |
| FR-OUT-03 | Portal provides HTML tier breakdown, ticket preview, `.xlsx` download, category audit, TBC queue, and rule maintenance flows. |

### 5.5 Portal maintenance (Phase 2)

| ID | Requirement |
|----|-------------|
| FR-PM-01 | **Learn New** (`/learn`): upload classified workbook, preview NDJSON impact, Confirm to `runs/live/` (+ Drive). |
| FR-PM-02 | **Rules chat** (`/rules`): compile RuleSpec drafts via LLM, preview on live run, Confirm with lead gate. |
| FR-PM-03 | **Category audit**: bucket review, sweeps, CSV export, NL focus parsing on a run. |
| FR-PM-04 | **TBC queue**: paginated manual-review workbench with explain, optional suggest, chunk ack. |
| FR-PM-05 | **Review chat**: orchestrated profile → propose → preview; TBC handoff without auto-compile. |
| FR-PM-06 | **Revert**: version-guarded restore of last Learn confirm from backup. |
| FR-PM-07 | **Consistency Gateway**: validate proposals, risk grades, soft conflicts — no auto-write. |

### 5.4 Operations

| ID | Requirement |
|----|-------------|
| FR-OP-01 | Container image build and deploy to Kubernetes (dev/prod) via GitLab CI. |
| FR-OP-02 | Health endpoint for load balancers (`/health`). |
| FR-OP-03 | Resolve `doc/` from repo root, `CS_TICKETS_REPO_ROOT`, or App Service `wwwroot` in deployed environments. |

---

## 6. Non-functional requirements

| ID | Category | Requirement |
|----|----------|-------------|
| NFR-01 | **Explainability** | Every non-fallback classification traceable to rule ids and weights. |
| NFR-02 | **Safety** | Allow-list is the hard boundary; invalid tuples never scored or emitted without coercion warning. |
| NFR-03 | **Performance** | Process typical exports (hundreds–low thousands of lines) on a single pod without GPU. |
| NFR-04 | **Dependencies** | Python 3.11+, stdlib + Typer, openpyxl; portal adds FastAPI/uvicorn. |
| NFR-05 | **Testability** | Pytest coverage for flatten, taxonomy, classify, pipeline, portal. |
| NFR-06 | **Data hygiene** | Large Zendesk exports stay local/gitignored under `data/`. |

---

## 7. Tier taxonomy (product model)

Each ticket receives exactly one **5-tuple**:

1. **Tier1_Segment** — e.g. `B2C`, `B2B`
2. **Tier2_Stream** — e.g. `Service Task`, `Complaint`, `Junk`
3. **Tier3_Cat** — e.g. `General Support`, `Billing & Admin`
4. **Tier4_Type** — e.g. `Rate or Renewal Inquiry`, `TBC (Manual Review)`
5. **Granular_Tech_UI_Type** — product/UI granularity or `N/A`

**TBC (Manual Review)** is an explicit product bucket for low-confidence or unmapped cases—not a failure mode. The product objective is to **minimize avoidable TBC** while keeping ambiguous cases reviewable.

---

## 8. Release phases

### Phase 1 — Shipped

- NDJSON → master rows pipeline
- Weighted classifier + allow-list
- CLI + FastAPI portal (classify, download)
- GitLab CI → Kaniko → K8s (dev/prod)
- Audit tooling and iterative rule batches

### Phase 2 — Shipped (portal maintenance)

- Learn New / live config on Google Drive (`runs/live/`)
- Explicit rule authoring (Rules chat + compile/preview/confirm)
- Category audit and TBC queue workbenches
- Review chat + Christine orchestration (Cursor skills + session runner)
- TBC trends dashboard (`/dashboard`)
- Consistency Gateway and version-guarded revert

Details: [prd-phase2-learning-feedback.md](./prd-phase2-learning-feedback.md), [architecture/agent-skills-framework.md](./architecture/agent-skills-framework.md).

### Phase 3 — Planned

- Apps Script or sheet integration calling hosted pipeline
- Richer export flattening (parent ticket, latest public comment) — partial via `thread_enrich`
- Persistent run store for multi-replica portal
- Targeted rules for retention offers, activation, newsletter/unsubscribe, regulatory (OFCA)

---

## 9. Dependencies and constraints

| Dependency | Impact |
|------------|--------|
| Zendesk export format | Field names and tag conventions must remain stable or rules updated. |
| `doc/Taxonomy.csv` + workbook | Source of truth for valid tiers; drift breaks allow-list union. |
| Tagging quality in Zendesk | `miscellaneous` / `other_departments` tags weakly predict intent. |
| Reply-thread subjects (`RE:`) | Limited signal without thread enrichment. |

---

## 10. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Misclassification on aggressive rules | Confidence gates, margin checks, high weights only for unambiguous phrases; audit before merge. |
| README vs portal doc drift | Canonical: README + HANDOFF; portal collapse copy in `portal_copy.py`; diagram in `portal_docs.py` — see [design.md §6.4](./design.md#64-documentation-in-ui) |
| AlipayHK / system emails | Hold bulk mapping until sampled; exclude from generic cancel blobs. |
| Unreachable taxonomy leaves | Audit `unreachable_allow_tuples`; add scorers when volume justifies. |

---

## 11. Acceptance criteria

### Phase 1

- [x] `pytest` passes on default CI/local setup.
- [x] CLI produces CSV with all `MASTER_COLUMNS`.
- [x] Portal upload → tier breakdown → Excel download works.
- [x] All output tiers ∈ allow-list (with rare coercion warnings logged).
- [x] `audit_classifier` reports TBC rate and top signals.
- [x] Documented in README and `docs/design.md`.

### Phase 2

- [x] Learn New confirm writes to `runs/live/` and syncs to Drive when enabled.
- [x] Rules compile + preview + confirm (lead-gated) promotes RuleSpec to live rules.
- [x] Category audit and TBC queue available per run.
- [x] Review chat routes to profile / compile / TBC handoff per intent table.
- [x] Documented in HANDOFF, api-reference, agent-skills-framework.

---

## 12. References

- [README.md](../README.md) — setup, CLI, portal
- [HANDOFF.md](./HANDOFF.md) — maintainer onboarding
- [design.md](./design.md) — technical architecture
- [api-reference.md](./api-reference.md) — portal HTTP routes
- [ops-runbook.md](./ops-runbook.md) — deploy and rollback
- [architecture/agent-skills-framework.md](./architecture/agent-skills-framework.md) — Review chat and skills
- [prd-phase2-learning-feedback.md](./prd-phase2-learning-feedback.md) — Learn New / feedback loop spec
- [plans/README.md](./plans/README.md) — implementation plan index
- [plans/2026-05-14-tier-classifier-improvements.md](./plans/2026-05-14-tier-classifier-improvements.md) — classifier iteration log
