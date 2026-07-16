"""Version-guarded live revert tests (Phase D.5)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cs_tickets.feedback.promote import (
    PromoteError,
    backup_live_dir,
    read_config_version,
    revert_latest_live_backup,
    write_config_version,
)
from cs_tickets.runtime_config import ensure_live_bootstrapped


def test_revert_refuses_when_expected_version_mismatches(
    repo_root: Path, tmp_path: Path
) -> None:
    # Bootstrap from repo docs into an isolated live dir
    target = tmp_path / "root"
    (target / "doc").mkdir(parents=True)
    for name in ("Taxonomy.csv", "classifier_rules.json", "CS_ticket_new_categorizations.xlsx"):
        src = repo_root / "doc" / name
        if src.is_file():
            (target / "doc" / name).write_bytes(src.read_bytes())
    live = ensure_live_bootstrapped(target)
    version_before = read_config_version(live)
    backup_live_dir(live, live / "backup" / str(version_before))
    write_config_version(
        live,
        version=version_before + 1,
        proposal_id="test",
        upload_id="test",
    )
    current = read_config_version(live)
    assert current == version_before + 1

    with pytest.raises(PromoteError, match="Config moved"):
        revert_latest_live_backup(live, expected_version=current + 99)

    restored = revert_latest_live_backup(live, expected_version=current)
    assert restored == version_before
    assert read_config_version(live) == version_before
