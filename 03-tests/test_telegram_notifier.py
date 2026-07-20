import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "02-scripts"))

import telegram_notifier


def _ok_response():
    """Return a mock requests.Response with ok=True."""
    mock = MagicMock()
    mock.json.return_value = {"ok": True}
    return mock


def test_send_photo_calls_sendphoto_endpoint(tmp_path, monkeypatch):
    """send_photo() must POST to the sendPhoto endpoint."""
    monkeypatch.setattr("config.TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr("config.TELEGRAM_CHAT_ID", "123")
    monkeypatch.setattr(telegram_notifier, "_last_photo_sent", 0.0)

    img = tmp_path / "snap.jpg"
    img.write_bytes(b"fake jpeg")

    with patch("telegram_notifier.requests.post", return_value=_ok_response()) as mock_post:
        telegram_notifier.send_photo(str(img))
        url = mock_post.call_args[0][0]
        assert "sendPhoto" in url
        assert "test-token" in url


def test_send_photo_includes_chat_id(tmp_path, monkeypatch):
    """send_photo() must pass the configured chat_id in the POST data."""
    monkeypatch.setattr("config.TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr("config.TELEGRAM_CHAT_ID", "456")
    monkeypatch.setattr(telegram_notifier, "_last_photo_sent", 0.0)

    img = tmp_path / "snap.jpg"
    img.write_bytes(b"fake jpeg")

    with patch("telegram_notifier.requests.post", return_value=_ok_response()) as mock_post:
        telegram_notifier.send_photo(str(img))
        data = mock_post.call_args[1]["data"]
        assert data["chat_id"] == "456"


def test_send_photo_uses_caption(tmp_path, monkeypatch):
    """send_photo() must include the caption in the POST data."""
    monkeypatch.setattr("config.TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr("config.TELEGRAM_CHAT_ID", "123")
    monkeypatch.setattr(telegram_notifier, "_last_photo_sent", 0.0)

    img = tmp_path / "snap.jpg"
    img.write_bytes(b"fake jpeg")

    with patch("telegram_notifier.requests.post", return_value=_ok_response()) as mock_post:
        telegram_notifier.send_photo(str(img), caption="Test caption")
        data = mock_post.call_args[1]["data"]
        assert data["caption"] == "Test caption"


def test_send_photo_suppressed_within_cooldown(tmp_path, monkeypatch):
    """send_photo() must skip the API call if called within NOTIFICATION_COOLDOWN_SEC."""
    monkeypatch.setattr("config.TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr("config.TELEGRAM_CHAT_ID", "123")
    monkeypatch.setattr("config.NOTIFICATION_COOLDOWN_SEC", 60)
    import time
    monkeypatch.setattr(telegram_notifier, "_last_photo_sent", time.time())

    img = tmp_path / "snap.jpg"
    img.write_bytes(b"fake jpeg")

    with patch("telegram_notifier.requests.post") as mock_post:
        telegram_notifier.send_photo(str(img))
        mock_post.assert_not_called()


def test_send_message_calls_sendmessage_endpoint(monkeypatch):
    """send_message() must POST to the sendMessage endpoint."""
    monkeypatch.setattr("config.TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr("config.TELEGRAM_CHAT_ID", "123")

    with patch("telegram_notifier.requests.post") as mock_post:
        telegram_notifier.send_message("hello")
        url = mock_post.call_args[0][0]
        assert "sendMessage" in url


def test_send_message_includes_text(monkeypatch):
    """send_message() must pass the text in the POST data."""
    monkeypatch.setattr("config.TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr("config.TELEGRAM_CHAT_ID", "123")

    with patch("telegram_notifier.requests.post") as mock_post:
        telegram_notifier.send_message("clip ready")
        data = mock_post.call_args[1]["data"]
        assert data["text"] == "clip ready"
