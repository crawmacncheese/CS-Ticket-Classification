"""Sync runtime config (runs/live/) with Google Drive."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from cs_tickets.drive_upload import (
    CSV_MIME,
    DriveUploadError,
    JSON_MIME,
    XLSX_MIME,
    build_drive_service,
    download_file_bytes,
    drive_folder_id,
    drive_upload_enabled,
    ensure_child_folder,
    find_child_file,
    upload_or_update_bytes,
    _supports_all_drives_kwargs,
)
from cs_tickets.live_config import (
    CONFIG_VERSION_FILE,
    RULES_FILE,
    TAXONOMY_FILE,
    WORKBOOK_FILE,
)

logger = logging.getLogger(__name__)

LIVE_FOLDER_NAME = "live"
PROPOSALS_FOLDER_NAME = "proposals"
BACKUP_FOLDER_NAME = "backup"

_LIVE_FILES: tuple[tuple[str, str], ...] = (
    (TAXONOMY_FILE, CSV_MIME),
    (RULES_FILE, JSON_MIME),
    (CONFIG_VERSION_FILE, JSON_MIME),
    (WORKBOOK_FILE, XLSX_MIME),
)


def live_file_mime(filename: str) -> str:
    if filename.endswith(".json"):
        return JSON_MIME
    if filename.endswith(".xlsx"):
        return XLSX_MIME
    return CSV_MIME


@dataclass(frozen=True)
class DriveLiveSyncResult:
    live_folder_id: str
    live_folder_url: str | None
    files_uploaded: int
    proposal_files_uploaded: int


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def live_folder_id() -> str | None:
    explicit = (os.environ.get("GOOGLE_DRIVE_LIVE_FOLDER_ID") or "").strip()
    if explicit:
        return explicit
    runs_id = drive_folder_id()
    if not runs_id or not drive_upload_enabled():
        return None
    try:
        service = build_drive_service()
        child = find_child_file(service, runs_id, LIVE_FOLDER_NAME, folder=True)
        if child and child.get("id"):
            return str(child["id"])
    except DriveUploadError as exc:
        logger.warning("Could not resolve Drive live folder: %s", exc)
    return None


def drive_live_folder_url() -> str | None:
    folder_id = live_folder_id()
    if not folder_id:
        return None
    explicit = (os.environ.get("GOOGLE_DRIVE_LIVE_FOLDER_URL") or "").strip()
    if explicit:
        return explicit
    return f"https://drive.google.com/drive/folders/{folder_id}?usp=drive_link"


def drive_live_sync_readiness() -> tuple[bool, str]:
    if not _truthy(os.environ.get("RUNTIME_CONFIG_DRIVE_ENABLED")):
        return False, "Set RUNTIME_CONFIG_DRIVE_ENABLED=true to upload live config to Drive."
    folder_id = live_folder_id()
    if not folder_id:
        return (
            False,
            "Set GOOGLE_DRIVE_LIVE_FOLDER_ID (your live folder) or place a subfolder named "
            "'live' under GOOGLE_DRIVE_RUNS_FOLDER_ID.",
        )
    from cs_tickets.drive_upload import credentials_file_path

    if not credentials_file_path():
        return False, "Set GOOGLE_APPLICATION_CREDENTIALS to the service-account JSON key path."
    return True, ""


def drive_live_config_enabled() -> bool:
    ready, _ = drive_live_sync_readiness()
    return ready


def sync_live_from_drive(live_dir: Path) -> str | None:
    """Download live config files from Drive into local cache. Returns error message."""
    folder_id = live_folder_id()
    if not folder_id:
        return None
    live_dir.mkdir(parents=True, exist_ok=True)
    try:
        service = build_drive_service()
        downloaded = 0
        for filename, _mime in _LIVE_FILES:
            remote = find_child_file(service, folder_id, filename)
            if not remote or not remote.get("id"):
                continue
            payload = download_file_bytes(service, str(remote["id"]))
            (live_dir / filename).write_bytes(payload)
            downloaded += 1
        if downloaded:
            logger.info("Synced %s live config file(s) from Drive folder %s", downloaded, folder_id)
        return None
    except DriveUploadError as exc:
        logger.warning("Drive live config download failed: %s", exc)
        return str(exc)
    except Exception as exc:
        logger.exception("Unexpected Drive live config download failure")
        return str(exc)


def _upload_directory_files(
    service: object,
    *,
    parent_id: str,
    directory: Path,
) -> int:
    if not directory.is_dir():
        return 0
    count = 0
    for path in sorted(directory.iterdir()):
        if not path.is_file():
            continue
        mime = live_file_mime(path.name)
        upload_or_update_bytes(
            service,
            parent_id=parent_id,
            filename=path.name,
            payload=path.read_bytes(),
            mime_type=mime,
        )
        count += 1
    return count


def sync_live_to_drive(
    live_dir: Path,
    *,
    proposals_dir: Path | None = None,
    backup_version: int | None = None,
) -> tuple[DriveLiveSyncResult | None, str | None]:
    """Upload merged live config (+ optional backup/proposal bundle) to Drive."""
    folder_id = live_folder_id()
    if not folder_id:
        return None, None
    try:
        service = build_drive_service()
        uploaded = 0
        for filename, mime in _LIVE_FILES:
            path = live_dir / filename
            if not path.is_file():
                continue
            upload_or_update_bytes(
                service,
                parent_id=folder_id,
                filename=filename,
                payload=path.read_bytes(),
                mime_type=mime,
            )
            uploaded += 1

        proposal_uploads = 0
        if backup_version is not None:
            backup_local = live_dir / BACKUP_FOLDER_NAME / str(backup_version)
            if backup_local.is_dir():
                backup_parent = ensure_child_folder(service, folder_id, BACKUP_FOLDER_NAME)
                version_folder = ensure_child_folder(service, backup_parent, str(backup_version))
                proposal_uploads += _upload_directory_files(
                    service,
                    parent_id=version_folder,
                    directory=backup_local,
                )

        if proposals_dir and proposals_dir.is_dir():
            runs_id = drive_folder_id()
            if not runs_id:
                raise DriveUploadError("GOOGLE_DRIVE_RUNS_FOLDER_ID is not set")
            proposals_parent = ensure_child_folder(service, runs_id, PROPOSALS_FOLDER_NAME)
            bundle_folder = ensure_child_folder(service, proposals_parent, proposals_dir.name)
            proposal_uploads += _upload_directory_files(
                service,
                parent_id=bundle_folder,
                directory=proposals_dir,
            )

        meta = service.files().get(
            fileId=folder_id, fields="webViewLink", **_supports_all_drives_kwargs()
        ).execute()
        link = meta.get("webViewLink")

        result = DriveLiveSyncResult(
            live_folder_id=folder_id,
            live_folder_url=str(link) if link else drive_live_folder_url(),
            files_uploaded=uploaded,
            proposal_files_uploaded=proposal_uploads,
        )
        logger.info(
            "Uploaded live config to Drive (%s files, %s audit files)",
            uploaded,
            proposal_uploads,
        )
        return result, None
    except DriveUploadError as exc:
        logger.warning("Drive live config upload failed: %s", exc)
        return None, str(exc)
    except Exception as exc:
        logger.exception("Unexpected Drive live config upload failure")
        return None, str(exc)


def try_sync_live_to_drive(
    live_dir: Path,
    *,
    proposals_dir: Path | None = None,
    backup_version: int | None = None,
) -> tuple[DriveLiveSyncResult | None, str | None, str | None]:
    """Return (result, error, skipped_reason). skipped_reason is set when Drive sync was not attempted."""
    ready, reason = drive_live_sync_readiness()
    if not ready:
        return None, None, reason
    result, error = sync_live_to_drive(
        live_dir,
        proposals_dir=proposals_dir,
        backup_version=backup_version,
    )
    return result, error, None
