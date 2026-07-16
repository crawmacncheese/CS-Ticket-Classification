# Configuration reference

Environment variables and runtime paths for `cs-tickets`. Values shown are examples — confirm production settings in `k8s/prod/deploy/deployment.yaml` and your team's secret store.

Copy [`.env.example`](../.env.example) to `.env` for local Drive-aligned dev.

---

## Repository paths

| Variable | Default / resolution | Purpose |
|----------|----------------------|---------|
| `CS_TICKETS_REPO_ROOT` | Auto-detect from package, `$HOME/site/wwwroot`, or cwd | Root containing `doc/` and `runs/` |

Runtime config directory: `{repo_root}/runs/live/` (see [README](../README.md#runtime-live-config-runslive)).

---

## Google Drive

| Variable | Required when | Purpose |
|----------|---------------|---------|
| `GOOGLE_APPLICATION_CREDENTIALS` | Drive sync or upload | Path to service account JSON |
| `RUNTIME_CONFIG_DRIVE_ENABLED` | Multi-replica / prod parity | Pull `runs/live/` from Drive on startup and before runs |
| `GOOGLE_DRIVE_LIVE_FOLDER_ID` | Runtime config sync | Live taxonomy, workbook, rules folder |
| `GOOGLE_DRIVE_LIVE_FOLDER_URL` | Alternative to ID | Resolved to folder ID at startup |
| `DRIVE_UPLOAD_ENABLED` | Run / Learn uploads | Upload run artifacts and live config after Confirm |
| `GOOGLE_DRIVE_RUNS_FOLDER_ID` | Run uploads | Classify run output folder |
| `GOOGLE_DRIVE_RUNS_FOLDER_URL` | Alternative to ID | Resolved to folder ID |
| `GOOGLE_DRIVE_SUPPORTS_ALL_DRIVES` | Shared drives | Set `true` for team drives |
| `GOOGLE_DRIVE_USE_FULL_SCOPE` | Some shared-drive setups | Set `true` when metadata scope is insufficient |

Service account (documented in README): `ai-daily-job-sa@editor-sub-editing-assistant.iam.gserviceaccount.com` — needs **Editor** on both folders.

---

## TBC trends

| Variable | Default | Purpose |
|----------|---------|---------|
| `TBC_TRENDS_ENABLED` | off | Snapshot each portal `POST /run` into SQLite |
| `TBC_TRENDS_DB_PATH` | `runs/tbc_trends/tbc_trends.db` | SQLite database path |
| `TBC_TRENDS_EVENTS_PATH` | optional | JSON timeline markers for dashboard |

Batch ingest: `tools/tbc_trend_snapshot.py`, report: `tools/tbc_trend_report.py`.

---

## Rule compile (LLM — not used by `/run`)

| Variable | Default | Purpose |
|----------|---------|---------|
| `RULE_COMPILE_PROVIDER` | `gemini` | `qwen`, `dashscope`, `gemini`, `deepseek`, `openai` |
| `RULE_COMPILE_API_KEY` | — | Explicit API key override |
| `GEMINI_API_KEY` | — | Gemini fallback |
| `QWEN_API_KEY_INTERNATIONAL` | — | Preferred for intl DashScope |
| `DASHSCOPE_API_KEY` | — | Alias for Qwen/DashScope |
| `DEEPSEEK_API_KEY` | — | DeepSeek fallback |
| `RULE_COMPILE_MODEL` | provider-specific | e.g. `qwen-plus`, Gemini model id |
| `RULE_COMPILE_API_BASE` | provider-specific | OpenAI-compatible base URL |

Used by Rules chat (`POST /rules/compile`) and optional TBC AI suggestions.

---

## Portal behaviour

| Variable | Default | Purpose |
|----------|---------|---------|
| `PORTAL_ALLOW_CONFIRM` | off | Allow `POST /rules/confirm*` and Learn Confirm in this process |
| `TBC_AUTO_SUGGEST` | on (`1`) | Auto category suggestions on TBC queue |
| `ALLOW_TIER1_PROMOTE` | off | Allow promote paths that change Tier1 (guard rail) |
| `CS_TICKETS_THREAD_ENRICHMENT` | off | Merge parent ticket context before classify |

---

## Live config files (`runs/live/`)

| File | Role |
|------|------|
| `Taxonomy.csv` | Runtime taxonomy tree |
| `CS_ticket_new_categorizations.xlsx` | Reference workbook 5-tuples |
| `classifier_rules.json` | Runtime rules (merged with training rules on bootstrap) |
| `config_version.json` | Monotonic version for cache invalidation and revert guards |
| `backup/{version}/` | Snapshots created on Learn Confirm |

Bootstrap: when live files are missing, copied from `references/` or `doc/`.

---

## Verification checklist

After deploy or env change:

1. `GET /health` → `ok`
2. Upload small NDJSON → results page loads with tier breakdown
3. If Drive enabled: confirm `config_version.json` matches expected version
4. If LLM enabled: `POST /rules/compile` with test phrase returns draft or clarify (not 500)
5. `pytest` passes on CI commit

---

## Related documents

- [README § Runtime live config](../README.md#runtime-live-config-runslive)
- [design.md §8 Deployment](./design.md#8-deployment-architecture)
- [HANDOFF.md §10](./HANDOFF.md#10-deployment-notes)
