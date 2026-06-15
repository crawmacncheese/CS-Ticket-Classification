# TBC Trend Dashboard — Plan

> **For implementer:** Document execution steps and final decisions in [2026-06-11-tbc-trend-dashboard-notes.md](./2026-06-11-tbc-trend-dashboard-notes.md).

**Goal:** Track **manual review (TBC) rate and hotspots** by Zendesk tag and normalized subject cluster over time, so maintainers can see whether rule batches shrink recurring TBC patterns and analysts can spot persistent buckets.

**Architecture:** Classify NDJSON exports → append ticket-level rows to a local SQLite DB → rollups via CLI markdown/CSV and portal `GET /dashboard`. See [implementation notes](./2026-06-11-tbc-trend-dashboard-notes.md) for design rationale.

**Tech stack:** Python 3.11, `cs_tickets.pipeline` / `classify_row_with_explanation`, SQLite (`reports/tbc_trends/tbc_trends.db`), pytest.

**Depends on:** [prd.md](../prd.md) Phase 3, `tools/audit_classifier.py` (TBC tag/subject counters), `portal_stats.is_manual_review_row` (TBC definition).

---

## Context

### Product question

| Question | v1 answer |
|----------|-----------|
| Is TBC % improving week over week? | `weekly_rollup.csv` — `tbc_pct` by ISO week of `created_at` |
| Which tags correlate with TBC? | `tag_rollup.csv` — top tags per week on TBC rows |
| Which subject patterns persist? | `cluster_rollup.csv` — normalized `subject_cluster_key` per week |
| Why are tickets still TBC? | `tbc_reason_rollup.csv` — `zero_candidate`, `lost_margin`, etc. |

### TBC definition (unchanged)

A row is TBC when `decision.fallback_used` or `"tbc" in decision.tier[3].lower()` — same as `audit_classifier.py` and `portal_stats.py`.

### Time axis

**Primary:** ISO week bucket (`2025-W01`) from ticket `created_at`.  
**Secondary (metadata):** `captured_at` on snapshot run and `export_id` (NDJSON filename stem).

### Subject clustering (v1)

Deterministic fingerprint — no ML:

1. Lowercase, strip `re:` / `fw:` / `fwd:` prefix
2. Replace runs of 4+ digits with `#`
3. Collapse whitespace; truncate to 80 chars

Cluster display label = most frequent raw subject in the bucket (computed at report time).

---

## v1 deliverables (shipped in this plan)

| Artifact | Role |
|----------|------|
| `src/cs_tickets/tbc_trends.py` | Clustering, record iteration, SQLite schema, rollups |
| `tools/tbc_trend_snapshot.py` | Classify NDJSON → append DB |
| `tools/tbc_trend_report.py` | DB → `summary.md` + CSV rollups |
| `tests/test_tbc_trends.py` | Clustering + snapshot/report integration |

### CLI usage

```bash
# Append one or more exports
.\.venv\Scripts\python.exe tools/tbc_trend_snapshot.py \
  --ndjson-dir data/ \
  --db reports/tbc_trends/tbc_trends.db

# Generate rollups
.\.venv\Scripts\python.exe tools/tbc_trend_report.py \
  --db reports/tbc_trends/tbc_trends.db \
  --output-dir reports/tbc-trends/
```

---

## Data model

### `exports`

| Column | Description |
|--------|-------------|
| `export_id` | Filename stem |
| `source_path` | Absolute or relative path processed |
| `captured_at` | UTC ISO timestamp |
| `row_count`, `tbc_count` | Run totals |
| `classifier_version` | SHA-256 prefix of `classifier_rules.json` + `doc/training_rules.json` |

### `tickets`

One row per ticket (`ticket_id` PK). Re-snapshot replaces the row (`INSERT OR REPLACE`).

| Column | Description |
|--------|-------------|
| `week_bucket` | ISO week from `created_at` |
| `segment` | `Tier1_Segment` |
| `is_tbc` | 0/1 |
| `tbc_reason` | From `classify.tbc_reason()` |
| `subject`, `subject_cluster` | Raw + fingerprint |

### `ticket_tags`

Exploded tags per ticket for tag rollups.

---

## Phase 2 (shipped)

| Artifact | Role |
|----------|------|
| `src/cs_tickets/portal_trends.py` | Dashboard HTML (weekly table, tag/cluster/reason panels) |
| `portal_app.py` | `GET /dashboard`; optional snapshot on `POST /run` |
| `tests/test_portal_trends.py` | Empty DB, populated DB, events, auto-snapshot |

- Portal `GET /dashboard` reading configured DB path (`TBC_TRENDS_DB_PATH`)
- Auto-snapshot after portal `/run` when `TBC_TRENDS_ENABLED=1`
- Optional rule-batch timeline via `reports/tbc_trends/events.json` (`TBC_TRENDS_EVENTS_PATH`)

## Phase 3 (future)

- Tag-pair clusters and prefix templates from classifier backlog
- Workbook upload ingest (`--classified-xlsx`) as first-class CLI flag

---

## Acceptance criteria

### v1

- [x] `subject_cluster_key("RE: Order 12345")` normalizes reply prefix and digits
- [x] Snapshot on `tests/fixtures/five_tickets.ndjson` populates DB without error
- [x] Report emits `summary.md`, `weekly_rollup.csv`, `tag_rollup.csv`, `cluster_rollup.csv`, `tbc_reason_rollup.csv`
- [x] `pytest tests/test_tbc_trends.py -q` passes

### Phase 2

- [x] `GET /dashboard` renders weekly TBC table and hotspot panels when DB exists
- [x] Empty state when DB missing (links to Classify + CLI instructions)
- [x] `TBC_TRENDS_ENABLED=1` appends portal upload; result page confirms snapshot
- [x] `pytest tests/test_portal_trends.py -q` passes
