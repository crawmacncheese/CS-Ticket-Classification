# Product Requirements Document — CS Ticket Automation

**Product:** CS Ticket Automation (`cs-tickets`)  
**Owner:** SCMP Customer Support / ITBS (engineering)  
**Status:** Phase 1 — in production (CLI, classifier, portal); ongoing classifier tuning  
**Last updated:** 2026-05-19

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
| **Operational surfaces** | CLI for batch jobs; web portal for upload, preview, and Excel download. |

### Success metrics

| Metric | Target (direction) | Notes |
|--------|------------------|-------|
| **TBC (Manual Review) rate** | Decrease over time | Baseline ~21–29% on recent exports; post–rule batch ~14–20%. |
| **Classifier warnings** | Near zero | Coercion / allow-list violations should be rare. |
| **Processing throughput** | Full export in minutes | Streaming NDJSON; no ML inference latency. |
| **Rule maintainability** | Add rules without code deploy (where possible) | JSON `RuleSpec` for simple patterns; computed rules for disambiguation. |

### Non-goals (Phase 1)

- Replacing Zendesk as the system of record.
- Fully automated closure or routing of tickets without human review.
- ML/LLM-based classification in production.
- Fuzzy matching against taxonomy labels without explicit signals.

---

## 3. Users and stakeholders

| Persona | Needs |
|---------|--------|
| **CS analyst / team lead** | Upload export, see tier breakdown, download Excel for review and reporting. |
| **Operations engineer** | Run CLI in CI or locally; deploy portal to dev/prod Kubernetes. |
| **Taxonomy owner** | Update `doc/Taxonomy.csv` and reference workbook; expect allow-list to reflect changes. |
| **Classifier maintainer** | Add rules from TBC audits; run `tools/audit_classifier.py`; read implementation plan in `docs/plans/`. |

---

## 4. User stories

### Must have (delivered)

1. **As an analyst**, I upload a Zendesk NDJSON export and receive an Excel workbook with all master columns plus a tier breakdown sheet.
2. **As an engineer**, I run `cs-tickets-pipeline` against a file path and write a CSV of categorized tickets.
3. **As a maintainer**, I add data-driven rules in `classifier_rules.json` for high-confidence tag/text/url patterns.
4. **As a maintainer**, I audit TBC rate and top fallback tags/subjects on a sample export before merging rule changes.
5. **As a taxonomy owner**, I know that only tier tuples present in the workbook, taxonomy CSV, or pipeline fallbacks can appear on output.

### Should have (partial / in progress)

6. **As a maintainer**, I reduce TBC for recurring patterns (PR noise, cancel/non-renewal, access/login, order confirmations) without increasing misclassification.
7. **As an analyst**, I understand from documentation how scoring and TBC fallback work (portal docs + README).

### Could have (future)

8. **As an analyst**, I trigger categorization from Google Sheets / Apps Script against a hosted API.
9. **As a maintainer**, I classify reply threads using parent ticket tags or full conversation text, not subject-only snippets.
10. **As a maintainer**, I label ambiguous buckets (e.g. AlipayHK auto-debit notices) once, then encode stable rules.

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
| FR-OUT-03 | Portal provides HTML tier breakdown, ticket preview (first N rows), and `.xlsx` download (Tickets + Tier breakdown sheets). |

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

### Phase 1 — Current (shipped)

- NDJSON → master rows pipeline
- Weighted classifier + allow-list
- CLI + local/deployed FastAPI portal
- GitLab CI → Kaniko → K8s (dev/prod)
- Audit tooling and iterative rule batches

### Phase 2 — Planned (see README / local plans)

- Apps Script or sheet integration calling hosted pipeline
- Richer export flattening (parent ticket, latest public comment)
- Targeted rules for retention offers, activation, newsletter/unsubscribe, regulatory (OFCA)

### Phase 3 — Optional

- Feedback loop: manual relabel → rule proposals
- Dashboard for TBC trend by tag/subject cluster over time

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
| README vs portal doc drift | Keep portal footer in sync with README (or generate from single source later). |
| AlipayHK / system emails | Hold bulk mapping until sampled; exclude from generic cancel blobs. |
| Unreachable taxonomy leaves | Audit `unreachable_allow_tuples`; add scorers when volume justifies. |

---

## 11. Acceptance criteria (Phase 1)

- [x] `pytest` passes on default CI/local setup.
- [x] CLI produces CSV with all `MASTER_COLUMNS`.
- [x] Portal upload → tier breakdown → Excel download works.
- [x] All output tiers ∈ allow-list (with rare coercion warnings logged).
- [x] `audit_classifier` reports TBC rate and top signals.
- [x] Documented in README and `docs/design.md`.

---

## 12. References

- [README.md](../README.md) — setup, CLI, portal
- [design.md](./design.md) — technical architecture
- [plans/2026-05-14-tier-classifier-improvements.md](./plans/2026-05-14-tier-classifier-improvements.md) — classifier iteration log and rule backlog
