# Scripts

Helper scripts for local portal development and Christine workflow automation. Run from the **repo root** with the portal already running unless noted.

Requires: `pip install -e ".[dev,portal]"` (adds `requests` via dev deps for HTTP scripts).

---

## `start-portal-drive.ps1`

**Platform:** Windows PowerShell

Copies `.env.example` → `.env` if missing, then starts uvicorn with Drive-aligned env (same folder IDs as prod `k8s/prod/deploy/deployment.yaml`).

Prerequisite: service account JSON at `secrets/google/credentials.json`.

---

## `run_christine_session.py`

Execute a **Session Metadata Package** against a live portal — used for demos, regression playlists, and session MD logging.

```bash
# Rosetta demo: create session MD + run packaged steps
python scripts/run_christine_session.py --demo rosetta --persona ANALYST \
  --init-session-md --session-md docs/sessions/2026-07-14-christine-requirements.md

# Run from a JSON package file
python scripts/run_christine_session.py --package path/to/package.json \
  --run-id <uuid> --session-md docs/sessions/my-session.md

# Base URL (default http://127.0.0.1:8777)
python scripts/run_christine_session.py --demo rosetta --base-url http://127.0.0.1:8777
```

**Actions dispatched:** upload, profile, category audit sweeps, compile, preview, confirm (when persona allows), reclassify, execution log append.

Related: [docs/sessions/README.md](../docs/sessions/README.md), [.cursor/skills/christine-workflow/SKILL.md](../.cursor/skills/christine-workflow/SKILL.md).

---

## `replay_christine_workflow.py`

Minimal HTTP replay for integration smoke tests — upload export, parse category-audit focus, sweeps, compile + preview one rule.

```bash
python scripts/replay_christine_workflow.py
python scripts/replay_christine_workflow.py --export tests/fixtures/golden_export.ndjson
```

Uses env `CS_TICKETS_PORTAL_URL` or defaults to `http://127.0.0.1:8777`.

---

## `session_profile.py`

CLI wrapper to call run profiling (`POST /run/{id}/review_chat/turn` or run parse focus) and print `SessionProfile` JSON.

```bash
python scripts/session_profile.py --run-id <uuid> --focus "review B2C Sales Leads"
python scripts/session_profile.py --run-id <uuid> --focus "..." --json
```

Useful when debugging focus parsing without opening the browser.

---

## See also

- [tools/](../tools/) — offline audit and batch analysis (no portal required)
- [docs/HANDOFF.md](../docs/HANDOFF.md) — full maintenance guide
