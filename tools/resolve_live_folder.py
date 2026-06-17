#!/usr/bin/env python3
"""Print the Google Drive folder id for the live runtime config folder."""

from __future__ import annotations

import sys

from cs_tickets.drive_live_config import drive_live_config_enabled, drive_live_folder_url, live_folder_id


def main() -> int:
    folder_id = live_folder_id()
    if not folder_id:
        print(
            "Could not resolve live folder. Set GOOGLE_DRIVE_LIVE_FOLDER_ID or create a "
            "'live' subfolder under GOOGLE_DRIVE_RUNS_FOLDER_ID and share it with the service account.",
            file=sys.stderr,
        )
        return 1
    print(f"GOOGLE_DRIVE_LIVE_FOLDER_ID={folder_id}")
    url = drive_live_folder_url()
    if url:
        print(f"GOOGLE_DRIVE_LIVE_FOLDER_URL={url}")
    print(f"drive_live_config_enabled={drive_live_config_enabled()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
