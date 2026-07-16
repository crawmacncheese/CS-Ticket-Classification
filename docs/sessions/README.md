# Review sessions

Per-batch review state for the Christine orchestration skill.

## Files

| File | Purpose |
|------|---------|
| [_template-session-requirements.md](./_template-session-requirements.md) | Copy to start a new session |
| `YYYY-MM-DD-<batch>-requirements.md` | One file per review batch |

Stable category protocol lives in [../taxonomy-requirements.md](../taxonomy-requirements.md) — do not duplicate edge cases in session files; link and promote after Confirm.

**taxonomy_version:** read `protocol_version` from the taxonomy header when creating a session.

## Workflow

1. Copy the template (or let the runner create it with `--init-session-md`).
2. Set goals and scope before or right after profiling.
3. After `POST /run`, record `run_id` (runner patches this when `--session-md` is set).
4. Append rows to **Execution log** as the skill runner or manual steps complete.
5. After preview, record match counts; after Confirm + reclassify, update **Results**.
6. Move stable corrections upstream into `taxonomy-requirements.md`.
7. **Revert playbook (Open items):** if a Confirm goes bad, only call `POST /learn/revert` when live `config_version` still equals this session's `config_version_after`; otherwise stop and escalate (another promote may have landed).

## Auto-create + append from runner

```bash
# Create session MD from template and run Rosetta demo (portal must be up)
python scripts/run_christine_session.py --demo rosetta --persona ANALYST \
  --init-session-md --session-md docs/sessions/2026-07-14-christine-requirements.md

# Append to an existing session file
python scripts/run_christine_session.py --package path/to/package.json --run-id <uuid> \
  --session-md docs/sessions/2026-07-14-christine-requirements.md
```

Python helper: `cs_tickets.session_md` (`create_session_md`, `append_execution_log`, `append_runner_log`).

## Skill

See [.cursor/skills/christine-workflow/SKILL.md](../../.cursor/skills/christine-workflow/SKILL.md).

## Plan

See [../plans/2026-07-13-christine-orchestration-skill.md](../plans/2026-07-13-christine-orchestration-skill.md).
