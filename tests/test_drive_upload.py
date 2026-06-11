from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cs_tickets.drive_upload import (
    DriveUploadError,
    credentials_file_path,
    drive_upload_enabled,
    try_upload_workbook,
    upload_workbook,
)
from cs_tickets.run_metadata import build_workbook_filename


def test_drive_upload_disabled_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DRIVE_UPLOAD_ENABLED", raising=False)
    monkeypatch.delenv("GOOGLE_DRIVE_RUNS_FOLDER_ID", raising=False)
    assert drive_upload_enabled() is False
    result, err = try_upload_workbook(b"PK", filename="test.xlsx")
    assert result is None
    assert err is None


def test_drive_upload_enabled_requires_folder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DRIVE_UPLOAD_ENABLED", "true")
    monkeypatch.setenv("GOOGLE_DRIVE_RUNS_FOLDER_ID", "folder123")
    assert drive_upload_enabled() is True


def test_credentials_file_path_prefers_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    custom = tmp_path / "custom.json"
    custom.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(custom))
    assert credentials_file_path() == str(custom)


def test_credentials_file_path_uses_k8s_mount(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    import cs_tickets.drive_upload as du

    mount = tmp_path / "credentials.json"
    mount.write_text("{}", encoding="utf-8")
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.setattr(du, "K8S_CREDENTIALS_PATHS", (str(mount),))
    assert credentials_file_path() == str(mount)


def test_service_account_email_from_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cs_tickets.drive_upload as du

    key = tmp_path / "sa.json"
    key.write_text(
        '{"client_email":"bot@project.iam.gserviceaccount.com"}',
        encoding="utf-8",
    )
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(key))
    assert (
        du.service_account_email_from_credentials(object())
        == "bot@project.iam.gserviceaccount.com"
    )


def test_build_workbook_filename_sanitizes_stem() -> None:
    name = build_workbook_filename(
        source_filename="export-2026-05-14 bad!.json",
        run_id="abcdef12-3456-7890-abcd-ef1234567890",
    )
    assert name.startswith("master_")
    assert name.endswith("_abcdef12.xlsx")
    assert " " not in name


@patch("googleapiclient.discovery.build")
@patch("cs_tickets.drive_upload._load_drive_credentials")
def test_upload_workbook_calls_drive_api(
    mock_creds: MagicMock, mock_build: MagicMock
) -> None:
    api = MagicMock()
    api.files().create().execute.return_value = {
        "id": "file123",
        "name": "master_20260519_sample_abcdef12.xlsx",
        "webViewLink": "https://drive.google.com/file/d/file123/view",
    }
    mock_build.return_value = api

    result = upload_workbook(
        b"fake-xlsx",
        filename="master_20260519_sample_abcdef12.xlsx",
        folder_id="15H0su7yspJnDJCbauglYmjPA1FthVPGI",
    )
    assert result.file_id == "file123"
    assert result.web_view_link is not None
    create_kwargs = api.files().create.call_args.kwargs
    assert create_kwargs["body"]["parents"] == ["15H0su7yspJnDJCbauglYmjPA1FthVPGI"]
    assert create_kwargs["supportsAllDrives"] is True


@patch("cs_tickets.drive_upload.upload_workbook", side_effect=DriveUploadError("quota"))
def test_try_upload_workbook_returns_error(_mock: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DRIVE_UPLOAD_ENABLED", "true")
    monkeypatch.setenv("GOOGLE_DRIVE_RUNS_FOLDER_ID", "folder123")
    result, err = try_upload_workbook(b"x", filename="a.xlsx")
    assert result is None
    assert err == "quota"
