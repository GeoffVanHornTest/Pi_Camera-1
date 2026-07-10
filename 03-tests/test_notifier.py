import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "02-scripts"))

import notifier


def test_send_alert_respects_cooldown(monkeypatch, tmp_path):
    """Second call within cooldown window must not attempt to send an email."""
    monkeypatch.setattr(notifier, "_last_sent", 0)

    snapshot = tmp_path / "snapshot.jpg"
    snapshot.write_bytes(b"fake image data")

    with patch("notifier.smtplib.SMTP") as mock_smtp:
        mock_smtp.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

        notifier.send_alert(str(snapshot))
        notifier.send_alert(str(snapshot))

        # SMTP should only have been called once — second call hit the cooldown
        assert mock_smtp.call_count == 1


def test_send_alert_updates_last_sent(monkeypatch, tmp_path):
    """After a successful send, _last_sent must be updated to prevent immediate resend."""
    monkeypatch.setattr(notifier, "_last_sent", 0)

    snapshot = tmp_path / "snapshot.jpg"
    snapshot.write_bytes(b"fake image data")

    with patch("notifier.smtplib.SMTP") as mock_smtp:
        mock_smtp.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

        notifier.send_alert(str(snapshot))

    assert notifier._last_sent > 0


def test_send_alert_skips_when_in_cooldown(monkeypatch, tmp_path):
    """Call made during active cooldown must return without touching SMTP."""
    import time
    monkeypatch.setattr(notifier, "_last_sent", time.time())

    snapshot = tmp_path / "snapshot.jpg"
    snapshot.write_bytes(b"fake image data")

    with patch("notifier.smtplib.SMTP") as mock_smtp:
        notifier.send_alert(str(snapshot))
        assert mock_smtp.call_count == 0