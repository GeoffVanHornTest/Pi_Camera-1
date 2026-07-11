"""Google Drive uploader for the PI Camera system.

Uploads video clips to a configured Drive folder and returns a shareable link.
Uses a service account for headless authentication — no browser OAuth flow required.
"""

import os

import config
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

_SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def _service():
    creds = service_account.Credentials.from_service_account_file(
        config.DRIVE_SERVICE_ACCOUNT_JSON, scopes=_SCOPES
    )
    return build("drive", "v3", credentials=creds)


def upload(filepath):
    """Upload a file to the configured Drive folder and return its shareable link.

    Args:
        filepath: Path to the local file to upload.

    Returns:
        str: The shareable webViewLink URL, or None if the upload failed.
    """
    try:
        svc = _service()
        file_metadata = {
            "name": os.path.basename(filepath),
            "parents": [config.DRIVE_FOLDER_ID],
        }
        media = MediaFileUpload(filepath, resumable=True)
        uploaded = (
            svc.files()
            .create(body=file_metadata, media_body=media, fields="id,webViewLink")
            .execute()
        )

        svc.permissions().create(
            fileId=uploaded["id"],
            body={"type": "anyone", "role": "reader"},
        ).execute()

        return uploaded.get("webViewLink")
    except Exception as e:
        print(f"Drive upload failed: {e}")
        return None
