# Flow diagrams

Visual reference for the main operator and system flows. Source of truth for behaviour remains the linked design docs; these diagrams are for onboarding and orientation.

**Related:** [HANDOFF.md](./HANDOFF.md) · [design.md](./design.md) · [architecture/agent-skills-framework.md](./architecture/agent-skills-framework.md) · [api-reference.md](./api-reference.md)

---

## 1. System overview

End-to-end: Zendesk export in → classified master rows out → optional maintenance back into live config.

```mermaid
flowchart LR
  ZD[Zendesk NDJSON]
  CLI[CLI cs-tickets-pipeline]
  PORTAL[Portal FastAPI]
  CORE[Pipeline + classifier]
  LIVE[(runs/live + Drive)]
  OUT[CSV / XLSX]

  ZD --> CLI --> CORE --> OUT
  ZD --> PORTAL --> CORE
  LIVE --> CORE
  PORTAL -->|Confirm| LIVE
  CORE --> PORTAL
```

---

## 2. Per-ticket classify path (`/run` and CLI)

Deterministic hot path — **no LLM**.

```mermaid
flowchart TB
  NDJSON[NDJSON line] --> FLAT[flatten_ticket]
  FLAT --> SIG[_signals: tags / subject / blob / url]
  SIG --> DATA[Data-driven RuleSpec matches]
  SIG --> CODE[Computed rules in classify.py]
  DATA --> SCORE[Sum weights by 5-tuple]
  CODE --> SCORE
  ALLOW[(AllowList)] -.->|only valid tuples| SCORE
  SCORE --> PICK[Pick best candidate]
  PICK --> GATE{score + margin OK?}
  GATE -->|yes| MASTER[Master row with tiers]
  GATE -->|no| FALL[B2B TBC if print else B2C TBC]
  FALL --> MASTER
```

Confidence gate: score ≥ `SCORE_THRESHOLD` (5.0) **and** (score ≥ `HIGH_CONFIDENCE_SCORE` (12.0) **or** margin ≥ `MIN_SCORE_MARGIN` (2.0)).

Detail: [design.md §5](./design.md#5-classifier-design) · [README](../README.md).

---

## 3. After upload — analyst journey

What an analyst does after `POST /run` succeeds.

```mermaid
flowchart TB
  UP[Upload NDJSON on /] --> RES[Results /run/id/results]
  RES --> DL[Download XLSX]
  RES --> AUD[Category audit]
  RES --> TBC[TBC queue]
  RES --> CHAT[Review chat]
  AUD --> CHAT
  TBC --> CHAT
  CHAT --> DRAFT[Draft rule]
  DRAFT --> PREV[Preview impact]
  PREV --> HAND{Persona?}
  HAND -->|ANALYST| QUEUE[Queue for lead Confirm]
  HAND -->|LEAD + PORTAL_ALLOW_CONFIRM| CONF[Confirm → live config]
  CONF --> RECL[Reclassify run]
```

---

## 4. Rule maintenance (Christine / Review chat loop)

Primary maintenance loop for routing rules.

```mermaid
sequenceDiagram
  actor Analyst
  participant UI as Review chat / Rules
  participant Orch as Intent router
  participant Profile as profile-run
  participant Propose as propose-rule
  participant Preview as preview-rule
  participant GW as Consistency Gateway
  participant Lead as Lead Confirm
  participant Live as runs/live

  Analyst->>UI: Upload / open run
  Analyst->>UI: “review B2C …”
  UI->>Orch: route intent
  Orch->>Profile: focus → sweeps / counts
  Profile-->>UI: profile cards
  Analyst->>UI: “Map … / draft a rule”
  Orch->>Propose: POST /rules/compile
  Propose->>GW: validate + risk
  Propose-->>UI: draft RuleSpec
  Orch->>Preview: POST /rules/preview
  Preview-->>UI: deltas + shield overlap
  alt ANALYST
    UI-->>Analyst: handoff — Confirm blocked
  else LEAD
    Lead->>Live: POST /rules/confirm
    Lead->>UI: POST …/reclassify
  end
```

Framework: [agent-skills-framework.md](./architecture/agent-skills-framework.md).

---

## 5. Review chat intent routing

How natural language is routed (never invents a rule when unclear).

```mermaid
flowchart TB
  MSG[User message] --> I1{TBC / manual review?}
  I1 -->|yes| TBC[Handoff → /run/id/tbc<br/>never compile]
  I1 -->|no| I2{Compile phrase?<br/>Map / draft a rule}
  I2 -->|yes| PROP[propose-rule]
  PROP --> PREV[auto preview-rule if run_id]
  I2 -->|no| I3{Focus / profile / audit?}
  I3 -->|yes| PROF[profile-run]
  I3 -->|no| CLAR[Clarify options<br/>never invent a rule]
```

---

## 6. TBC queue review

Chat **routes into** the queue; it does not replace the workbench.

```mermaid
flowchart TB
  START[Results or Review chat<br/>“show all TBC”] --> PAGE[/run/id/tbc]
  PAGE --> FILT[Optional NL focus filter]
  FILT --> LIST[Paginated TBC tickets]
  LIST --> EXPL[Explain ticket]
  LIST --> SUG[Optional AI suggest]
  LIST --> ACK[Ack chunk]
  LIST --> OVR[Run-scoped override]
  LIST --> RULE[Draft rule for recurring pattern]
  RULE --> COMP[POST /rules/compile]
  COMP --> PREV[Preview → Confirm path]
```

---

## 7. Learn New (allow-list + rules from workbook)

```mermaid
flowchart TB
  UP[Upload classified .xlsx] --> PROC[POST /learn/process]
  PROC --> REV[Review new 5-tuples / proposals]
  REV --> PREV[POST /learn/preview<br/>optional NDJSON A/B]
  PREV --> CONF{Lead Confirm?}
  CONF -->|yes| LIVE[Write runs/live]
  LIVE --> DRIVE[Upload to Drive if enabled]
  LIVE --> BACK[Snapshot backup/version]
  CONF -->|cancel| DROP[Drop session]
  BAD[Bad promote] --> REV2[POST /learn/revert]
  REV2 --> GUARD{config_version matches?}
  GUARD -->|yes| REST[Restore backup]
  GUARD -->|no| STOP[Stop — escalate]
```

---

## 8. Live config and Drive sync

```mermaid
flowchart TB
  subgraph seeds [Bootstrap only]
    REF[references/ or doc/]
  end

  subgraph runtime [Runtime]
    DISK[(Pod runs/live/)]
    DRIVE[(Google Drive live folder)]
  end

  subgraph writers [Writers]
    LEARN[Learn Confirm]
    RULES[Rules Confirm]
  end

  subgraph readers [Readers]
    RUN[POST /run classify]
    CLI[CLI pipeline]
  end

  REF -->|missing live files| DISK
  DRIVE <-->|sync when RUNTIME_CONFIG_DRIVE_ENABLED| DISK
  LEARN --> DISK
  RULES --> DISK
  LEARN --> DRIVE
  RULES --> DRIVE
  DISK --> RUN
  DISK --> CLI
```

---

## 9. Category audit

```mermaid
flowchart TB
  RES[Run results] --> AUD[/run/id/category_audit]
  AUD --> FOCUS[NL parse focus]
  AUD --> SWEEP[GET sweeps by tier1 / categories]
  SWEEP --> BUCKET[Bucket cards]
  BUCKET --> EXPL[Explain ticket]
  BUCKET --> PROP[Propose rule from pattern]
  PROP --> RULES[Rules compile / preview]
  AUD --> CSV[Export CSV]
```

---

## 10. Deploy (CI → GKE)

```mermaid
flowchart LR
  PUSH[Push to branch] --> BUILD[Kaniko build]
  BUILD --> SCAN[Prisma scans]
  BUILD --> DEPLOY[k8s/deploy.sh]
  DEPLOY --> DEV[dev branch → auto]
  DEPLOY --> PROD[master → manual]
  DEV --> POD1[GKE itbs-general]
  PROD --> POD2[GKE itbs-general]
  POD2 --> DRIVE[(Drive live config)]
```

Detail: [ops-runbook.md](./ops-runbook.md).

---

## 11. Agent skills ↔ portal APIs

```mermaid
flowchart TB
  subgraph orch [Orchestration]
    CW[christine-workflow]
    RJ[rules.js intent router]
  end

  subgraph skills [Atomic skills]
    PR[profile-run]
    PO[propose-rule]
    PV[preview-rule]
    EX[explain-ticket]
    FT[filter-tickets]
    CR[confirm-rule]
  end

  subgraph api [Portal]
    T[POST …/review_chat/turn]
    C[POST /rules/compile]
    P[POST /rules/preview]
    CF[POST /rules/confirm]
    E[GET …/explain/…]
  end

  CW --> PR & PO & PV & EX & FT & CR
  RJ --> PR & PO & PV
  PR --> T
  PO --> C
  PV --> P
  CR --> CF
  EX --> E
```

---

## Quick links by role

| Role | Start with |
|------|------------|
| New engineer | §1, §2, §8 |
| Analyst / lead | §3, §4, §6, §7 |
| Agent / Christine | §4, §5, §11 |
| Ops | §8, §10 |
