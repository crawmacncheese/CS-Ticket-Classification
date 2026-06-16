"""Constants and version helpers for runs/live/ runtime config."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

CONFIG_VERSION_FILE = "config_version.json"
TAXONOMY_FILE = "Taxonomy.csv"
RULES_FILE = "classifier_rules.json"
WORKBOOK_FILE = "CS_ticket_new_categorizations.xlsx"


def _utc_now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def read_config_version(live_dir: Path) -> int:
    path = live_dir / CONFIG_VERSION_FILE
    if not path.is_file():
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    return int(data.get("version", 0))


def write_config_version(
    live_dir: Path,
    *,
    version: int,
    proposal_id: str,
    upload_id: str,
) -> None:
    payload = {
        "version": version,
        "updated_at": _utc_now_iso(),
        "proposal_id": proposal_id,
        "upload_id": upload_id,
    }
    (live_dir / CONFIG_VERSION_FILE).write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
