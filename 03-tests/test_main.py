import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

# Mock camera before importing main — prevents hardware initialisation at module level.
_mock_camera = MagicMock()
sys.modules["camera"] = _mock_camera

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "02-scripts"))

import main  # noqa: E402


def test_arm_watchdog_fires_split_event(monkeypatch):
    """_arm_watchdog() must set _split_event after MAX_RECORD_SEC elapses."""
    monkeypatch.setattr(main.config, "MAX_RECORD_SEC", 0.05)
    main._arm_watchdog()
    time.sleep(0.15)
    assert main._split_event.is_set()
    main._cancel_watchdog()


def test_cancel_watchdog_prevents_split_event(monkeypatch):
    """_cancel_watchdog() must prevent the timer from setting _split_event."""
    monkeypatch.setattr(main.config, "MAX_RECORD_SEC", 0.15)
    main._arm_watchdog()
    main._cancel_watchdog()
    time.sleep(0.25)
    assert not main._split_event.is_set()


def test_cancel_watchdog_clears_watchdog_reference():
    main._arm_watchdog()
    main._cancel_watchdog()
    assert main._watchdog is None


def test_finish_clip_calls_stop_recording():
    """_finish_clip() must call camera.stop_recording with on_complete=_upload_and_notify."""
    _mock_camera.reset_mock()
    with patch.object(main.motion_detector, "reset_motion_state"):
        main._finish_clip()
    _mock_camera.stop_recording.assert_called_once()
    _, kwargs = _mock_camera.stop_recording.call_args
    assert kwargs.get("on_complete") is main._upload_and_notify


def test_finish_clip_resets_motion_state():
    """_finish_clip() must reset the motion detector state."""
    _mock_camera.reset_mock()
    with patch.object(main.motion_detector, "reset_motion_state") as mock_reset:
        main._finish_clip()
    mock_reset.assert_called_once()


def test_finish_clip_cancels_watchdog(monkeypatch):
    """_finish_clip() must cancel any running watchdog and clear _split_event."""
    monkeypatch.setattr(main.config, "MAX_RECORD_SEC", 5.0)
    main._arm_watchdog()
    _mock_camera.reset_mock()
    with patch.object(main.motion_detector, "reset_motion_state"):
        main._finish_clip()
    assert not main._split_event.is_set()
    assert main._watchdog is None


# --- #65: watchdog-split branch ---

def test_watchdog_split_calls_split_recording(monkeypatch):
    """When _split_event fires during recording, main() must call camera.split_recording."""
    monkeypatch.setattr(main, "_validate_config", lambda: None)
    monkeypatch.setattr(main.config, "MAX_RECORD_SEC", 9999)
    monkeypatch.setattr(main.config, "POST_MOTION_BUFFER_SEC", 9999)
    monkeypatch.setattr(main.storage, "cleanup_old_clips", lambda days=7: None)
    monkeypatch.setattr(main.storage, "get_video_path", lambda: "/clips/test.mp4")
    monkeypatch.setattr(main.storage, "save_snapshot", lambda f: "/clips/snap.jpg")
    monkeypatch.setattr(main.motion_detector, "detect", lambda f: (True, f))
    monkeypatch.setattr(main.motion_detector, "new_event_allowed", lambda: True)
    monkeypatch.setattr(main.motion_detector, "reset_motion_state", lambda: None)
    monkeypatch.setattr(main.telegram_notifier, "send_photo", lambda *a, **kw: None)
    monkeypatch.setattr(main.telegram_notifier, "_last_photo_sent", 0.0)

    _mock_camera.reset_mock()
    call_count = [0]

    def fake_get_frame():
        call_count[0] += 1
        if call_count[0] == 2:
            # Simulate watchdog firing between iterations
            main._split_event.set()
        if call_count[0] > 3:
            raise KeyboardInterrupt
        return MagicMock()

    _mock_camera.get_frame.side_effect = fake_get_frame

    with pytest.raises(KeyboardInterrupt):
        main.main()

    main._cancel_watchdog()

    _mock_camera.split_recording.assert_called_once()
    _, kwargs = _mock_camera.split_recording.call_args
    assert kwargs.get("on_complete") is main._upload_and_notify


# --- #74: on_complete callback chain ---

def test_upload_and_notify_sends_link_on_success(monkeypatch):
    """_upload_and_notify() must send the Dropbox URL via Telegram on success."""
    monkeypatch.setattr(main.dropbox_uploader, "upload", lambda path: "https://dropbox.com/clip")
    mock_send = MagicMock()
    monkeypatch.setattr(main.telegram_notifier, "send_message", mock_send)
    main._upload_and_notify("/clips/test.mp4")
    mock_send.assert_called_once_with("Clip ready: https://dropbox.com/clip")


def test_upload_and_notify_sends_failure_on_no_url(monkeypatch):
    """_upload_and_notify() must send a failure message when Dropbox upload returns None."""
    monkeypatch.setattr(main.dropbox_uploader, "upload", lambda path: None)
    mock_send = MagicMock()
    monkeypatch.setattr(main.telegram_notifier, "send_message", mock_send)
    main._upload_and_notify("/clips/test.mp4")
    mock_send.assert_called_once_with("Clip recorded but Dropbox upload failed.")


# --- #78: snapshot failure must not break recording state ---

def test_recording_continues_when_snapshot_raises(monkeypatch):
    """If save_snapshot() raises, currently_recording must still be set True.

    A snapshot failure must not leave the camera recording while the main
    loop thinks currently_recording is False — that would prevent the
    POST_MOTION_BUFFER_SEC stop condition from ever firing.
    """
    monkeypatch.setattr(main, "_validate_config", lambda: None)
    monkeypatch.setattr(main.config, "MAX_RECORD_SEC", 9999)
    monkeypatch.setattr(main.config, "POST_MOTION_BUFFER_SEC", 9999)
    monkeypatch.setattr(main.storage, "cleanup_old_clips", lambda days=7: None)
    monkeypatch.setattr(main.storage, "get_video_path", lambda: "/clips/test.mp4")
    failing_snapshot = MagicMock(side_effect=RuntimeError("disk full"))
    monkeypatch.setattr(main.storage, "save_snapshot", failing_snapshot)
    monkeypatch.setattr(main.motion_detector, "reset_motion_state", lambda: None)
    monkeypatch.setattr(main.motion_detector, "new_event_allowed", lambda: True)

    call_count = [0]

    def fake_detect(frame):
        call_count[0] += 1
        if call_count[0] > 2:
            raise KeyboardInterrupt
        return (True, frame)

    monkeypatch.setattr(main.motion_detector, "detect", fake_detect)
    _mock_camera.reset_mock()
    _mock_camera.get_frame.side_effect = None
    _mock_camera.get_frame.return_value = MagicMock()

    with pytest.raises(KeyboardInterrupt):
        main.main()

    main._cancel_watchdog()

    # Recording must have started despite the snapshot failure
    _mock_camera.start_recording.assert_called_once()