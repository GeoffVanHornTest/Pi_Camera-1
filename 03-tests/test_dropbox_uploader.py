import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "02-scripts"))

import dropbox_uploader
import pytest


@pytest.fixture(autouse=True)
def reset_token_cache(monkeypatch):
    """Reset the module-level token cache before each test."""
    monkeypatch.setattr(dropbox_uploader, "_cached_token", None)
    monkeypatch.setattr(dropbox_uploader, "_token_fetched_at", 0.0)


def _mock_token_response(token="test-access-token"):
    mock = MagicMock()
    mock.json.return_value = {"access_token": token}
    mock.raise_for_status = MagicMock()
    return mock


def _mock_upload_response():
    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    return mock


def _mock_share_response(url="https://www.dropbox.com/s/abc/motion.mp4"):
    mock = MagicMock()
    mock.json.return_value = {"url": url}
    mock.raise_for_status = MagicMock()
    return mock


def test_upload_returns_shareable_url(tmp_path, monkeypatch):
    """upload() must return the shareable URL from Dropbox."""
    monkeypatch.setattr("config.DROPBOX_APP_KEY", "key")
    monkeypatch.setattr("config.DROPBOX_APP_SECRET", "secret")
    monkeypatch.setattr("config.DROPBOX_REFRESH_TOKEN", "refresh")

    clip = tmp_path / "motion.mp4"
    clip.write_bytes(b"fake video")

    with patch("dropbox_uploader.requests.post") as mock_post:
        mock_post.side_effect = [
            _mock_token_response(),
            _mock_upload_response(),
            _mock_share_response("https://www.dropbox.com/s/abc/motion.mp4"),
        ]
        result = dropbox_uploader.upload(str(clip))

    assert result == "https://www.dropbox.com/s/abc/motion.mp4"


def test_upload_returns_none_on_failure(tmp_path, monkeypatch):
    """upload() must return None (not raise) when the API fails."""
    monkeypatch.setattr("config.DROPBOX_APP_KEY", "key")
    monkeypatch.setattr("config.DROPBOX_APP_SECRET", "secret")
    monkeypatch.setattr("config.DROPBOX_REFRESH_TOKEN", "refresh")

    clip = tmp_path / "motion.mp4"
    clip.write_bytes(b"fake video")

    with patch("dropbox_uploader.requests.post", side_effect=Exception("network error")):
        result = dropbox_uploader.upload(str(clip))

    assert result is None


def test_upload_uses_correct_dropbox_path(tmp_path, monkeypatch):
    """upload() must place the file under /PI_Camera/ in Dropbox."""
    monkeypatch.setattr("config.DROPBOX_APP_KEY", "key")
    monkeypatch.setattr("config.DROPBOX_APP_SECRET", "secret")
    monkeypatch.setattr("config.DROPBOX_REFRESH_TOKEN", "refresh")

    clip = tmp_path / "motion_2026-07-11_10-00-00.mp4"
    clip.write_bytes(b"fake video")

    with patch("dropbox_uploader.requests.post") as mock_post:
        mock_post.side_effect = [
            _mock_token_response(),
            _mock_upload_response(),
            _mock_share_response(),
        ]
        dropbox_uploader.upload(str(clip))

    upload_call = mock_post.call_args_list[1]
    api_arg = upload_call[1]["headers"]["Dropbox-API-Arg"]
    assert "/PI_Camera/motion_2026-07-11_10-00-00.mp4" in api_arg


def test_upload_api_arg_header_is_valid_json(tmp_path, monkeypatch):
    """Dropbox-API-Arg header must be valid JSON regardless of filename content."""
    import json

    monkeypatch.setattr("config.DROPBOX_APP_KEY", "key")
    monkeypatch.setattr("config.DROPBOX_APP_SECRET", "secret")
    monkeypatch.setattr("config.DROPBOX_REFRESH_TOKEN", "refresh")

    # Filename with characters that would break an f-string JSON construction
    clip = tmp_path / 'motion_"tricky"_\\path.mp4'
    clip.write_bytes(b"fake video")

    with patch("dropbox_uploader.requests.post") as mock_post:
        mock_post.side_effect = [
            _mock_token_response(),
            _mock_upload_response(),
            _mock_share_response(),
        ]
        dropbox_uploader.upload(str(clip))

    upload_call = mock_post.call_args_list[1]
    api_arg = upload_call[1]["headers"]["Dropbox-API-Arg"]
    parsed = json.loads(api_arg)  # raises if not valid JSON
    assert parsed["mode"] == "add"
    assert parsed["path"].startswith("/PI_Camera/")


def test_get_access_token_caches_token(monkeypatch):
    """_get_access_token() must not POST again while the cached token is still valid."""
    monkeypatch.setattr("config.DROPBOX_APP_KEY", "key")
    monkeypatch.setattr("config.DROPBOX_APP_SECRET", "secret")
    monkeypatch.setattr("config.DROPBOX_REFRESH_TOKEN", "refresh")

    with patch("dropbox_uploader.requests.post") as mock_post:
        mock_post.return_value = _mock_token_response("cached-token")
        first = dropbox_uploader._get_access_token()
        second = dropbox_uploader._get_access_token()

    assert first == "cached-token"
    assert second == "cached-token"
    assert mock_post.call_count == 1  # only one network call


def test_get_access_token_refreshes_when_expired(monkeypatch):
    """_get_access_token() must fetch a new token when the cached one has expired."""
    import time

    monkeypatch.setattr("config.DROPBOX_APP_KEY", "key")
    monkeypatch.setattr("config.DROPBOX_APP_SECRET", "secret")
    monkeypatch.setattr("config.DROPBOX_REFRESH_TOKEN", "refresh")
    monkeypatch.setattr(dropbox_uploader, "_cached_token", "old-token")
    # Simulate a token fetched well beyond the TTL
    monkeypatch.setattr(
        dropbox_uploader, "_token_fetched_at",
        time.time() - dropbox_uploader._TOKEN_TTL - 1,
    )

    with patch("dropbox_uploader.requests.post") as mock_post:
        mock_post.return_value = _mock_token_response("new-token")
        token = dropbox_uploader._get_access_token()

    assert token == "new-token"
    mock_post.assert_called_once()


def test_get_access_token_uses_refresh_token(monkeypatch):
    """_get_access_token() must POST the refresh token to get a new access token."""
    monkeypatch.setattr("config.DROPBOX_APP_KEY", "mykey")
    monkeypatch.setattr("config.DROPBOX_APP_SECRET", "mysecret")
    monkeypatch.setattr("config.DROPBOX_REFRESH_TOKEN", "myrefresh")

    with patch("dropbox_uploader.requests.post") as mock_post:
        mock_post.return_value = _mock_token_response("new-token")
        token = dropbox_uploader._get_access_token()

    assert token == "new-token"
    data = mock_post.call_args[1]["data"]
    assert data["refresh_token"] == "myrefresh"
    assert data["grant_type"] == "refresh_token"
