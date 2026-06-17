from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cs_tickets.drive_live_config import (
    drive_live_config_enabled,
    live_folder_id,
    sync_live_from_drive,
    sync_live_to_drive,
)
from cs_tickets.live_config import CONFIG_VERSION_FILE, RULES_FILE, TAXONOMY_FILE, WORKBOOK_FILE


def test_live_folder_id_prefers_explicit_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_DRIVE_LIVE_FOLDER_ID", "live-folder-xyz")
    assert live_folder_id() == "live-folder-xyz"


@patch("cs_tickets.drive_live_config.build_drive_service")
def test_live_folder_id_discovers_child(mock_build: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_DRIVE_LIVE_FOLDER_ID", raising=False)
    monkeypatch.setenv("DRIVE_UPLOAD_ENABLED", "true")
    monkeypatch.setenv("GOOGLE_DRIVE_RUNS_FOLDER_ID", "runs-root")
    api = MagicMock()
    api.files().list().execute.return_value = {"files": [{"id": "live123", "name": "live"}]}
    mock_build.return_value = api
    assert live_folder_id() == "live123"


@patch("cs_tickets.drive_live_config.upload_or_update_bytes")
@patch("cs_tickets.drive_live_config.ensure_child_folder")
@patch("cs_tickets.drive_live_config.build_drive_service")
def test_sync_live_to_drive_uploads_config_files(
    mock_build: MagicMock,
    mock_ensure_folder: MagicMock,
    mock_upload: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    live = tmp_path / "live"
    live.mkdir()
    (live / TAXONOMY_FILE).write_text("Tier1_Segment,Tier2_Stream,Tier3_Cat,Tier4_Type\n", encoding="utf-8")
    (live / RULES_FILE).write_text("[]\n", encoding="utf-8")
    (live / CONFIG_VERSION_FILE).write_text('{"version": 2}\n', encoding="utf-8")
    (live / WORKBOOK_FILE).write_bytes(b"PK\x03\x04workbook")

    monkeypatch.setenv("GOOGLE_DRIVE_LIVE_FOLDER_ID", "live-folder")
    monkeypatch.setenv("DRIVE_UPLOAD_ENABLED", "true")
    monkeypatch.setenv("GOOGLE_DRIVE_RUNS_FOLDER_ID", "runs-root")

    api = MagicMock()
    api.files().get().execute.return_value = {"webViewLink": "https://drive.google.com/drive/folders/live-folder"}
    mock_build.return_value = api
    mock_ensure_folder.return_value = "subfolder"

    result, err = sync_live_to_drive(live)
    assert err is None
    assert result is not None
    assert result.files_uploaded == 4
    assert mock_upload.call_count == 4


@patch("cs_tickets.drive_live_config.download_file_bytes")
@patch("cs_tickets.drive_live_config.find_child_file")
@patch("cs_tickets.drive_live_config.build_drive_service")
def test_sync_live_from_drive_writes_local_cache(
    mock_build: MagicMock,
    mock_find: MagicMock,
    mock_download: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    live = tmp_path / "live"
    live.mkdir()
    monkeypatch.setenv("GOOGLE_DRIVE_LIVE_FOLDER_ID", "live-folder")
    monkeypatch.setenv("DRIVE_UPLOAD_ENABLED", "true")

    mock_find.return_value = {"id": "file1"}
    mock_download.return_value = b'{"version": 9}\n'
    mock_build.return_value = MagicMock()

    err = sync_live_from_drive(live)
    assert err is None
    assert (live / CONFIG_VERSION_FILE).read_bytes() == b'{"version": 9}\n'


def test_drive_live_config_enabled_requires_runtime_flag(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    creds = tmp_path / "sa.json"
    creds.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(creds))
    monkeypatch.setenv("DRIVE_UPLOAD_ENABLED", "true")
    monkeypatch.setenv("GOOGLE_DRIVE_RUNS_FOLDER_ID", "runs-root")
    monkeypatch.setenv("GOOGLE_DRIVE_LIVE_FOLDER_ID", "live-folder")
    assert drive_live_config_enabled() is False
    monkeypatch.setenv("RUNTIME_CONFIG_DRIVE_ENABLED", "true")
    assert drive_live_config_enabled() is True
