import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "02-scripts"))

import drive_uploader


def _mock_service(web_view_link="https://drive.google.com/file/test"):
    """Build a fully mocked Drive service object."""
    mock_svc = MagicMock()
    mock_svc.files().create().execute.return_value = {
        "id": "file123",
        "webViewLink": web_view_link,
    }
    return mock_svc


def test_upload_returns_web_view_link(tmp_path, monkeypatch):
    """upload() must return the webViewLink from the Drive API response."""
    monkeypatch.setattr("config.DRIVE_FOLDER_ID", "folder123")
    monkeypatch.setattr("config.DRIVE_SERVICE_ACCOUNT_JSON", "/fake/path.json")

    clip = tmp_path / "motion.mp4"
    clip.write_bytes(b"fake video")

    with patch("drive_uploader._service", return_value=_mock_service()):
        result = drive_uploader.upload(str(clip))

    assert result == "https://drive.google.com/file/test"


def test_upload_sets_public_permission(tmp_path, monkeypatch):
    """upload() must call permissions().create() with role=reader."""
    monkeypatch.setattr("config.DRIVE_FOLDER_ID", "folder123")
    monkeypatch.setattr("config.DRIVE_SERVICE_ACCOUNT_JSON", "/fake/path.json")

    clip = tmp_path / "motion.mp4"
    clip.write_bytes(b"fake video")

    mock_svc = _mock_service()
    with patch("drive_uploader._service", return_value=mock_svc):
        drive_uploader.upload(str(clip))

    call_kwargs = mock_svc.permissions().create.call_args[1]
    assert call_kwargs["body"]["role"] == "reader"
    assert call_kwargs["body"]["type"] == "anyone"


def test_upload_uses_correct_folder(tmp_path, monkeypatch):
    """upload() must set the configured DRIVE_FOLDER_ID as the file parent."""
    monkeypatch.setattr("config.DRIVE_FOLDER_ID", "my-folder-id")
    monkeypatch.setattr("config.DRIVE_SERVICE_ACCOUNT_JSON", "/fake/path.json")

    clip = tmp_path / "motion.mp4"
    clip.write_bytes(b"fake video")

    mock_svc = _mock_service()
    with patch("drive_uploader._service", return_value=mock_svc):
        drive_uploader.upload(str(clip))

    call_kwargs = mock_svc.files().create.call_args[1]
    assert "my-folder-id" in call_kwargs["body"]["parents"]


def test_upload_returns_none_on_failure(tmp_path, monkeypatch):
    """upload() must return None (not raise) when the Drive API fails."""
    monkeypatch.setattr("config.DRIVE_FOLDER_ID", "folder123")
    monkeypatch.setattr("config.DRIVE_SERVICE_ACCOUNT_JSON", "/fake/path.json")

    clip = tmp_path / "motion.mp4"
    clip.write_bytes(b"fake video")

    with patch("drive_uploader._service", side_effect=Exception("API error")):
        result = drive_uploader.upload(str(clip))

    assert result is None
