"""Dropbox uploader for the PI Camera system.

Uploads video clips to Dropbox and returns a shareable link.
Uses the refresh token flow so credentials never expire.
"""

import json
import os
import time

import config
import requests

_TOKEN_URL = "https://api.dropbox.com/oauth2/token"
_UPLOAD_URL = "https://content.dropboxapi.com/2/files/upload"
_SHARE_URL = "https://api.dropboxapi.com/2/sharing/create_shared_link_with_settings"

_TOKEN_TTL = 4 * 3600       # Dropbox access tokens are valid for 4 hours
_TOKEN_MARGIN = 60           # refresh this many seconds before expiry
_cached_token = None
_token_fetched_at = 0.0


def _get_access_token():
    """Return a valid access token, fetching a new one only when the cached token has expired."""
    global _cached_token, _token_fetched_at
    if _cached_token and time.time() - _token_fetched_at < _TOKEN_TTL - _TOKEN_MARGIN:
        return _cached_token
    response = requests.post(
        _TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": config.DROPBOX_REFRESH_TOKEN,
            "client_id": config.DROPBOX_APP_KEY,
            "client_secret": config.DROPBOX_APP_SECRET,
        },
        timeout=15,
    )
    response.raise_for_status()
    _cached_token = response.json()["access_token"]
    _token_fetched_at = time.time()
    return _cached_token


def upload(filepath):
    """Upload a file to Dropbox and return a shareable link.

    Args:
        filepath: Path to the local file to upload.

    Returns:
        str: A shareable URL, or None if the upload failed.
    """
    try:
        token = _get_access_token()
        filename = os.path.basename(filepath)
        dropbox_path = f"/PI_Camera/{filename}"

        with open(filepath, "rb") as f:
            upload_response = requests.post(
                _UPLOAD_URL,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Dropbox-API-Arg": json.dumps({"path": dropbox_path, "mode": "add"}),
                    "Content-Type": "application/octet-stream",
                },
                data=f,
                timeout=120,
            )
        upload_response.raise_for_status()

        share_response = requests.post(
            _SHARE_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={"path": dropbox_path, "settings": {"requested_visibility": "public"}},
            timeout=15,
        )
        share_response.raise_for_status()
        return share_response.json().get("url")

    except Exception as e:
        print(f"Dropbox upload failed: {e}")
        return None
