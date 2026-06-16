"""Upload categorized run workbooks to a Google Drive folder."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DRIVE_SCOPE_FILE = "https://www.googleapis.com/auth/drive.file"
DRIVE_SCOPE_FULL = "https://www.googleapis.com/auth/drive"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
JSON_MIME = "application/json"
CSV_MIME = "text/csv"
FOLDER_MIME = "application/vnd.google-apps.folder"
# K8s mount paths (see k8s/*/deploy/deployment.yaml); env GOOGLE_APPLICATION_CREDENTIALS wins.
K8S_CREDENTIALS_PATHS: tuple[str, ...] = (
    "/config/credentials.json",
    "/var/secrets/google/credentials.json",
)


@dataclass(frozen=True)
class DriveUploadResult:
    file_id: str
    filename: str
    web_view_link: str | None


class DriveUploadError(Exception):
    """Drive API or configuration failure."""


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def drive_folder_id() -> str | None:
    raw = (os.environ.get("GOOGLE_DRIVE_RUNS_FOLDER_ID") or "").strip()
    return raw or None


def drive_runs_folder_url() -> str:
    """Browser URL for the shared runs folder (Run History link in portal)."""
    explicit = (os.environ.get("GOOGLE_DRIVE_RUNS_FOLDER_URL") or "").strip()
    if explicit:
        return explicit
    folder_id = drive_folder_id()
    if folder_id:
        return f"https://drive.google.com/drive/folders/{folder_id}?usp=drive_link"
    return (
        "https://drive.google.com/drive/folders/"
        "15H0su7yspJnDJCbauglYmjPA1FthVPGI?usp=drive_link"
    )


def drive_upload_enabled() -> bool:
    return _truthy(os.environ.get("DRIVE_UPLOAD_ENABLED")) and bool(drive_folder_id())


def drive_upload_configured() -> bool:
    """Upload is expected to be attempted (enabled flag + folder id)."""
    return drive_upload_enabled()


def credentials_file_path() -> str | None:
    """Path to service-account JSON, if configured or present on the K8s mount."""
    explicit = (os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
    if explicit:
        return explicit
    for path in K8S_CREDENTIALS_PATHS:
        if os.path.isfile(path):
            return path
    return None


def _drive_scopes() -> list[str]:
    if _truthy(os.environ.get("GOOGLE_DRIVE_USE_FULL_SCOPE")):
        return [DRIVE_SCOPE_FULL]
    return [DRIVE_SCOPE_FILE]


def _supports_all_drives() -> bool:
    raw = os.environ.get("GOOGLE_DRIVE_SUPPORTS_ALL_DRIVES")
    if raw is None or raw.strip() == "":
        return True
    return _truthy(raw)


def service_account_email_from_credentials(credentials: Any) -> str | None:
    email = getattr(credentials, "service_account_email", None)
    if email:
        return str(email)
    path = credentials_file_path()
    if not path:
        return None
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    client = data.get("client_email")
    return str(client) if client else None


def _load_drive_credentials() -> Any:
    scopes = _drive_scopes()
    path = credentials_file_path()
    if path:
        if not os.path.isfile(path):
            raise DriveUploadError(f"Google credentials file not found: {path}")
        try:
            from google.oauth2 import service_account
        except ImportError as exc:
            raise DriveUploadError(
                'Google auth libraries are not installed. Install with: pip install -e ".[portal]"'
            ) from exc
        logger.debug("Loading Drive credentials from %s", path)
        return service_account.Credentials.from_service_account_file(path, scopes=scopes)

    try:
        import google.auth
    except ImportError as exc:
        raise DriveUploadError(
            'Google auth libraries are not installed. Install with: pip install -e ".[portal]"'
        ) from exc

    try:
        credentials, _ = google.auth.default(scopes=scopes)
        return credentials
    except google.auth.exceptions.DefaultCredentialsError as exc:
        raise DriveUploadError(
            "Google credentials not found. Set GOOGLE_APPLICATION_CREDENTIALS to a "
            "service-account JSON key, or mount secret editorial-service-account "
            f"(e.g. {K8S_CREDENTIALS_PATHS[0]}) on GKE."
        ) from exc


def _supports_all_drives_kwargs() -> dict[str, Any]:
    if _supports_all_drives():
        return {"supportsAllDrives": True}
    return {}


def _list_kwargs() -> dict[str, Any]:
    if _supports_all_drives():
        return {"supportsAllDrives": True, "includeItemsFromAllDrives": True}
    return {}


def build_drive_service() -> Any:
    credentials = _load_drive_credentials()
    try:
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise DriveUploadError(
            "Google Drive libraries are not installed. "
            'Install with: pip install -e ".[portal]"'
        ) from exc
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def find_child_file(
    service: Any,
    parent_id: str,
    name: str,
    *,
    folder: bool = False,
) -> dict[str, Any] | None:
    escaped = name.replace("'", "\\'")
    query = f"'{parent_id}' in parents and name = '{escaped}' and trashed = false"
    if folder:
        query += f" and mimeType = '{FOLDER_MIME}'"
    else:
        query += f" and mimeType != '{FOLDER_MIME}'"
    response = (
        service.files()
        .list(q=query, fields="files(id,name,mimeType,webViewLink)", **_list_kwargs())
        .execute()
    )
    files = response.get("files") or []
    return files[0] if files else None


def ensure_child_folder(service: Any, parent_id: str, name: str) -> str:
    existing = find_child_file(service, parent_id, name, folder=True)
    if existing and existing.get("id"):
        return str(existing["id"])
    body: dict[str, Any] = {
        "name": name,
        "mimeType": FOLDER_MIME,
        "parents": [parent_id],
    }
    created = service.files().create(body=body, fields="id", **_supports_all_drives_kwargs()).execute()
    folder_id = str(created.get("id") or "")
    if not folder_id:
        raise DriveUploadError(f"Drive API returned no folder id for {name!r}")
    return folder_id


def download_file_bytes(service: Any, file_id: str) -> bytes:
    from googleapiclient.http import MediaIoBaseDownload

    request = service.files().get_media(fileId=file_id, **_supports_all_drives_kwargs())
    buffer = BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buffer.getvalue()


def upload_or_update_bytes(
    service: Any,
    *,
    parent_id: str,
    filename: str,
    payload: bytes,
    mime_type: str,
) -> DriveUploadResult:
    from googleapiclient.http import MediaIoBaseUpload

    credentials = getattr(getattr(service, "_http", None), "credentials", None)
    existing = find_child_file(service, parent_id, filename)
    media = MediaIoBaseUpload(BytesIO(payload), mimetype=mime_type, resumable=True)
    fields = "id,name,webViewLink"
    try:
        if existing and existing.get("id"):
            updated = (
                service.files()
                .update(
                    fileId=str(existing["id"]),
                    media_body=media,
                    fields=fields,
                    **_supports_all_drives_kwargs(),
                )
                .execute()
            )
            file_id = str(updated.get("id") or existing["id"])
            link = updated.get("webViewLink") or existing.get("webViewLink")
            return DriveUploadResult(
                file_id=file_id,
                filename=str(updated.get("name") or filename),
                web_view_link=str(link) if link else None,
            )
        created = (
            service.files()
            .create(
                body={"name": filename, "parents": [parent_id]},
                media_body=media,
                fields=fields,
                **_supports_all_drives_kwargs(),
            )
            .execute()
        )
    except Exception as exc:
        raise DriveUploadError(
            _format_drive_http_error(exc, parent_folder_id=parent_id, credentials=credentials)
        ) from exc

    file_id = str(created.get("id") or "")
    if not file_id:
        raise DriveUploadError("Drive API returned no file id")
    link = created.get("webViewLink")
    return DriveUploadResult(
        file_id=file_id,
        filename=str(created.get("name") or filename),
        web_view_link=str(link) if link else None,
    )


def _format_drive_http_error(exc: Exception, *, parent_folder_id: str, credentials: Any) -> str:
    try:
        from googleapiclient.errors import HttpError
    except ImportError:
        return str(exc)

    if not isinstance(exc, HttpError):
        return str(exc)

    sa_email = service_account_email_from_credentials(credentials) or "(see credentials JSON client_email)"
    if exc.resp.status == 404 and parent_folder_id in str(exc):
        return (
            f"Drive folder not found for this service account ({sa_email}). "
            f"Folder id: {parent_folder_id}. "
            "Share the runs folder with that exact email as Editor (not only ai-daily-job-sa "
            "unless that is the same key). For Shared drives, keep GOOGLE_DRIVE_SUPPORTS_ALL_DRIVES=true."
        )
    if exc.resp.status == 403:
        return (
            f"Drive permission denied for {sa_email}. "
            f"Grant Editor on folder {parent_folder_id}."
        )
    return str(exc)


def upload_workbook(
    payload: bytes,
    *,
    filename: str,
    folder_id: str | None = None,
) -> DriveUploadResult:
    """Upload an xlsx workbook into the configured runs folder."""
    parent = (folder_id or drive_folder_id() or "").strip()
    if not parent:
        raise DriveUploadError("GOOGLE_DRIVE_RUNS_FOLDER_ID is not set")

    try:
        from googleapiclient.http import MediaIoBaseUpload
    except ImportError as exc:
        raise DriveUploadError(
            "Google Drive libraries are not installed. "
            'Install with: pip install -e ".[portal]"'
        ) from exc

    service = build_drive_service()
    credentials = _load_drive_credentials()
    body: dict[str, Any] = {"name": filename, "parents": [parent]}
    media = MediaIoBaseUpload(BytesIO(payload), mimetype=XLSX_MIME, resumable=True)
    kwargs: dict[str, Any] = {
        "body": body,
        "media_body": media,
        "fields": "id,name,webViewLink",
        **_supports_all_drives_kwargs(),
    }

    try:
        created = service.files().create(**kwargs).execute()
    except Exception as exc:
        raise DriveUploadError(
            _format_drive_http_error(exc, parent_folder_id=parent, credentials=credentials)
        ) from exc

    file_id = str(created.get("id") or "")
    if not file_id:
        raise DriveUploadError("Drive API returned no file id")

    link = created.get("webViewLink")
    return DriveUploadResult(
        file_id=file_id,
        filename=str(created.get("name") or filename),
        web_view_link=str(link) if link else None,
    )


def try_upload_workbook(
    payload: bytes,
    *,
    filename: str,
) -> tuple[DriveUploadResult | None, str | None]:
    """Upload when enabled; return (result, error_message). Never raises."""
    if not drive_upload_enabled():
        return None, None
    try:
        result = upload_workbook(payload, filename=filename)
        logger.info("Uploaded run workbook to Drive: %s (%s)", result.filename, result.file_id)
        return result, None
    except DriveUploadError as exc:
        logger.warning("Drive upload failed: %s", exc)
        return None, str(exc)
    except Exception as exc:
        logger.exception("Unexpected Drive upload failure")
        return None, str(exc)
