# Tools

Offline CLI utilities (no portal required unless noted). Run from repo root with `PYTHONPATH=src` or after `pip install -e ".[dev,portal]"`.

---

## Classifier audit

```bash
PYTHONPATH=src python tools/audit_classifier.py --input data/export.json
```

Reports row count, TBC %, top tiers, TBC tag/subject hotspots, scored tuples, and unreachable allow-list tuples.

---

## TBC trends

```bash
python tools/tbc_trend_snapshot.py --ndjson-dir data/
python tools/tbc_trend_report.py --output-dir reports/tbc-trends/
```

Append classified snapshots to SQLite and generate markdown + CSV rollups. Portal dashboard reads the same DB (`TBC_TRENDS_DB_PATH`).

Plan: [docs/plans/2026-06-11-tbc-trend-dashboard.md](../docs/plans/2026-06-11-tbc-trend-dashboard.md).

---

## Allow-list testing

```bash
python tools/run_allowlist_test.py --profile ci
python tools/run_allowlist_test.py --spec .cursor/skills/batch-allowlist-test/specs/probe-commit.json
python tools/batch_allowlist_compare.py --help
```

Batch ablation, commit simulation, and JSON-spec test suites. Architecture: [docs/plans/2026-06-09-allowlist-testing-architecture.md](../docs/plans/2026-06-09-allowlist-testing-architecture.md).

Skill: [.cursor/skills/batch-allowlist-test/SKILL.md](../.cursor/skills/batch-allowlist-test/SKILL.md).

---

## Drive / training helpers

| Tool | Purpose |
|------|---------|
| `resolve_live_folder.py` | Resolve Drive folder ID from URL (debug) |
| `build_training_test_upload.py` | Build controlled xlsx for Training test cases |

---

## See also

- [scripts/README.md](../scripts/README.md) — portal session runners
- [docs/HANDOFF.md](../docs/HANDOFF.md) — maintenance guide
