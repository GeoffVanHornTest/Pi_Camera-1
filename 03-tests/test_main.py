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
    _free = MagicMock()
    _free.free = 10 * 1024 ** 3
    monkeypatch.setattr(main.shutil, "disk_usage", lambda p: _free)

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


# --- #80: shutdown mid-clip must finalise the recording ---

def test_shutdown_calls_finish_clip_when_recording(monkeypatch):
    """_shutdown() must call camera.stop_recording if a clip is in progress."""
    monkeypatch.setattr(main, "_shutdown_called", False)
    monkeypatch.setattr(main.threading, "Timer", lambda *a, **kw: MagicMock())
    monkeypatch.setattr(main, "_currently_recording", True)
    monkeypatch.setattr(main.motion_detector, "reset_motion_state", lambda: None)
    _mock_camera.reset_mock()

    with pytest.raises(SystemExit):
        main._shutdown()

    _mock_camera.stop_recording.assert_called_once()


def test_shutdown_skips_finish_clip_when_not_recording(monkeypatch):
    """_shutdown() must not call camera.stop_recording if no clip is in progress."""
    monkeypatch.setattr(main, "_shutdown_called", False)
    monkeypatch.setattr(main.threading, "Timer", lambda *a, **kw: MagicMock())
    monkeypatch.setattr(main, "_currently_recording", False)
    _mock_camera.reset_mock()

    with pytest.raises(SystemExit):
        main._shutdown()

    _mock_camera.stop_recording.assert_not_called()


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
    _free = MagicMock()
    _free.free = 10 * 1024 ** 3
    monkeypatch.setattr(main.shutil, "disk_usage", lambda p: _free)

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


# --- #90: consecutive-error escalation ---

def test_main_raises_after_max_consecutive_errors(monkeypatch):
    """main() must raise RuntimeError after _MAX_CONSECUTIVE_ERRORS consecutive failures."""
    monkeypatch.setattr(main, "_validate_config", lambda: None)
    monkeypatch.setattr(main, "_MAX_CONSECUTIVE_ERRORS", 3)
    monkeypatch.setattr(main.storage, "cleanup_old_clips", lambda days=7: None)
    failing_detect = MagicMock(side_effect=RuntimeError("cam fail"))
    monkeypatch.setattr(main.motion_detector, "detect", failing_detect)

    _mock_camera.reset_mock()
    _mock_camera.get_frame.side_effect = None
    _mock_camera.get_frame.return_value = MagicMock()

    with pytest.raises(RuntimeError, match="consecutive errors"):
        main.main()


def test_consecutive_error_counter_resets_on_success(monkeypatch):
    """A successful frame must reset the consecutive-error counter to zero."""
    monkeypatch.setattr(main, "_validate_config", lambda: None)
    monkeypatch.setattr(main, "_MAX_CONSECUTIVE_ERRORS", 3)
    monkeypatch.setattr(main.storage, "cleanup_old_clips", lambda days=7: None)
    monkeypatch.setattr(main.motion_detector, "new_event_allowed", lambda: False)

    call_count = [0]

    def fake_detect(frame):
        call_count[0] += 1
        if call_count[0] < 3:
            raise RuntimeError("transient error")
        if call_count[0] == 3:
            return (False, frame)  # success — resets counter
        raise KeyboardInterrupt

    monkeypatch.setattr(main.motion_detector, "detect", fake_detect)
    _mock_camera.reset_mock()
    _mock_camera.get_frame.side_effect = None
    _mock_camera.get_frame.return_value = MagicMock()

    # Should NOT raise RuntimeError — the counter reset on frame 3
    with pytest.raises(KeyboardInterrupt):
        main.main()


# --- #107: low-disk guard ---


def test_recording_skipped_when_disk_full(monkeypatch):
    """start_recording must not be called when free disk space is below MIN_FREE_DISK_MB."""
    monkeypatch.setattr(main, "_validate_config", lambda: None)
    monkeypatch.setattr(main.config, "POST_MOTION_BUFFER_SEC", 9999)
    monkeypatch.setattr(main.config, "MIN_FREE_DISK_MB", 500)
    monkeypatch.setattr(main.storage, "cleanup_old_clips", lambda days=7: None)
    monkeypatch.setattr(main.motion_detector, "new_event_allowed", lambda: True)
    _full = MagicMock()
    _full.free = 100 * 1024 * 1024  # 100 MB — below threshold
    monkeypatch.setattr(main.shutil, "disk_usage", lambda p: _full)

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
    _mock_camera.start_recording.assert_not_called()


def test_recording_starts_when_disk_has_space(monkeypatch):
    """start_recording must be called when free disk space exceeds MIN_FREE_DISK_MB."""
    monkeypatch.setattr(main, "_validate_config", lambda: None)
    monkeypatch.setattr(main.config, "MAX_RECORD_SEC", 9999)
    monkeypatch.setattr(main.config, "POST_MOTION_BUFFER_SEC", 9999)
    monkeypatch.setattr(main.config, "MIN_FREE_DISK_MB", 500)
    monkeypatch.setattr(main.storage, "cleanup_old_clips", lambda days=7: None)
    monkeypatch.setattr(main.storage, "get_video_path", lambda: "/clips/test.mp4")
    monkeypatch.setattr(main.storage, "save_snapshot", lambda f: "/clips/snap.jpg")
    monkeypatch.setattr(main.motion_detector, "new_event_allowed", lambda: True)
    monkeypatch.setattr(main.motion_detector, "reset_motion_state", lambda: None)
    monkeypatch.setattr(main.telegram_notifier, "send_photo", lambda *a, **kw: None)
    monkeypatch.setattr(main.telegram_notifier, "_last_photo_sent", 0.0)
    _free = MagicMock()
    _free.free = 10 * 1024 ** 3  # 10 GB — above threshold
    monkeypatch.setattr(main.shutil, "disk_usage", lambda p: _free)

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
    _mock_camera.start_recording.assert_called_once()


# --- #126: shutdown deadline must outlast legitimate shutdown work (~195s) ---


def test_shutdown_deadline_is_300s(monkeypatch):
    """_shutdown() must set a 300s hard deadline, not the old 10s value.

    ffmpeg (30s) + Dropbox (120s) + share link (15s) + Telegram (30s) ≈ 195s.
    A 10s deadline fired during every normal shutdown with an active clip.
    """
    timer_calls = []

    def capture_timer(*args, **kwargs):
        timer_calls.append(args)
        return MagicMock()

    monkeypatch.setattr(main, "_shutdown_called", False)
    monkeypatch.setattr(main.threading, "Timer", capture_timer)
    monkeypatch.setattr(main, "_currently_recording", False)

    with pytest.raises(SystemExit):
        main._shutdown()

    assert len(timer_calls) >= 1
    assert timer_calls[0][0] == 300.0, f"deadline was {timer_calls[0][0]}s, expected 300s"


# --- #127: watchdog split must check disk space before splitting ---


def test_watchdog_split_stopped_when_disk_full(monkeypatch):
    """When watchdog fires and disk is full, split_recording is skipped and clip is stopped."""
    monkeypatch.setattr(main, "_validate_config", lambda: None)
    monkeypatch.setattr(main.config, "MAX_RECORD_SEC", 9999)
    monkeypatch.setattr(main.config, "POST_MOTION_BUFFER_SEC", 9999)
    monkeypatch.setattr(main.config, "MIN_FREE_DISK_MB", 500)
    monkeypatch.setattr(main.storage, "cleanup_old_clips", lambda days=7: None)
    monkeypatch.setattr(main.storage, "get_video_path", lambda: "/clips/test.mp4")
    monkeypatch.setattr(main.storage, "save_snapshot", lambda f: "/clips/snap.jpg")
    monkeypatch.setattr(main.motion_detector, "detect", lambda f: (True, f))
    monkeypatch.setattr(main.motion_detector, "new_event_allowed", lambda: True)
    monkeypatch.setattr(main.motion_detector, "reset_motion_state", lambda: None)
    monkeypatch.setattr(main.telegram_notifier, "send_photo", lambda *a, **kw: None)
    monkeypatch.setattr(main.telegram_notifier, "_last_photo_sent", 0.0)

    disk_calls = [0]

    def fake_disk_usage(path):
        disk_calls[0] += 1
        result = MagicMock()
        # First call: pre-start_recording check — plenty of space
        # Subsequent calls: watchdog split check — disk full
        result.free = 10 * 1024 ** 3 if disk_calls[0] == 1 else 100 * 1024 * 1024
        return result

    monkeypatch.setattr(main.shutil, "disk_usage", fake_disk_usage)

    _mock_camera.reset_mock()
    frame_count = [0]

    def fake_get_frame():
        frame_count[0] += 1
        if frame_count[0] == 2:
            main._split_event.set()
        if frame_count[0] > 4:
            raise KeyboardInterrupt
        return MagicMock()

    _mock_camera.get_frame.side_effect = fake_get_frame

    with pytest.raises(KeyboardInterrupt):
        main.main()

    main._cancel_watchdog()

    _mock_camera.split_recording.assert_not_called()
    _mock_camera.stop_recording.assert_called_once()


# --- #130: _shutdown() must be idempotent against concurrent/repeated SIGTERM ---


def test_shutdown_not_reentrant(monkeypatch):
    """A second call to _shutdown() mid-shutdown must return immediately without
    re-entering _finish_clip().

    A second SIGTERM (common in systemd stop sequences) previously called
    camera.stop_recording() a second time concurrently, racing on unlocked
    camera module globals.
    """
    monkeypatch.setattr(main, "_shutdown_called", False)
    monkeypatch.setattr(main.threading, "Timer", lambda *a, **kw: MagicMock())
    monkeypatch.setattr(main, "_currently_recording", True)
    monkeypatch.setattr(main.motion_detector, "reset_motion_state", lambda: None)
    _mock_camera.reset_mock()

    # First call: normal shutdown path, sets _shutdown_called = True.
    with pytest.raises(SystemExit):
        main._shutdown()

    first_stop_count = _mock_camera.stop_recording.call_count

    # Second call: must return immediately — no SystemExit, no stop_recording.
    main._shutdown()

    assert _mock_camera.stop_recording.call_count == first_stop_count, (
        f"stop_recording called {_mock_camera.stop_recording.call_count} times "
        f"(expected {first_stop_count}) — reentrancy guard not working"
    )


# --- #131: _currently_recording must be cleared before _finish_clip() in main loop ---


def test_currently_recording_cleared_before_finish_clip(monkeypatch):
    """_currently_recording must be False at the moment _finish_clip() is called
    from the main loop's POST_MOTION_BUFFER_SEC stop branch.

    If it were still True, a SIGTERM arriving mid-_finish_clip() would cause
    _shutdown() to call _finish_clip() a second time concurrently.
    """
    monkeypatch.setattr(main, "_validate_config", lambda: None)
    monkeypatch.setattr(main.config, "MAX_RECORD_SEC", 9999)
    monkeypatch.setattr(main.config, "POST_MOTION_BUFFER_SEC", 0)
    monkeypatch.setattr(main.storage, "cleanup_old_clips", lambda days=7: None)
    monkeypatch.setattr(main.storage, "get_video_path", lambda: "/clips/test.mp4")
    monkeypatch.setattr(main.storage, "save_snapshot", lambda f: "/clips/snap.jpg")
    monkeypatch.setattr(main.motion_detector, "new_event_allowed", lambda: True)
    monkeypatch.setattr(main.motion_detector, "reset_motion_state", lambda: None)
    monkeypatch.setattr(main.telegram_notifier, "send_photo", lambda *a, **kw: None)
    monkeypatch.setattr(main.telegram_notifier, "_last_photo_sent", 0.0)
    _free = MagicMock()
    _free.free = 10 * 1024 ** 3
    monkeypatch.setattr(main.shutil, "disk_usage", lambda p: _free)

    # Capture _currently_recording at the exact moment _finish_clip() is called.
    flag_at_finish = []

    def capturing_finish():
        flag_at_finish.append(main._currently_recording)

    monkeypatch.setattr(main, "_finish_clip", capturing_finish)
    _mock_camera.reset_mock()

    call_count = [0]

    def fake_get_frame():
        call_count[0] += 1
        if call_count[0] > 4:
            raise KeyboardInterrupt
        return MagicMock()

    def fake_detect(frame):
        # Motion on frame 1 only; subsequent frames have no motion so
        # POST_MOTION_BUFFER_SEC=0 fires on frame 2.
        return (call_count[0] == 1, frame)

    _mock_camera.get_frame.side_effect = fake_get_frame
    monkeypatch.setattr(main.motion_detector, "detect", fake_detect)

    with pytest.raises(KeyboardInterrupt):
        main.main()

    assert len(flag_at_finish) >= 1, "_finish_clip was never called"
    assert flag_at_finish[0] is False, (
        f"_currently_recording was {flag_at_finish[0]} when _finish_clip() was called "
        "— it must be False to prevent concurrent _finish_clip() call from _shutdown()"
    )


# --- #134: _currently_recording must be reset if start_recording() raises ---


def test_currently_recording_reset_on_start_recording_failure(monkeypatch):
    """If camera.start_recording() raises, both recording flags must be reset to False.

    _currently_recording is set True before start_recording() to close the #112
    SIGTERM race. If start_recording() then raises (hardware error), the flag
    must be reset — otherwise _shutdown() sees True and calls _finish_clip() on
    a session that was never started.
    """
    monkeypatch.setattr(main, "_validate_config", lambda: None)
    monkeypatch.setattr(main.config, "MAX_RECORD_SEC", 9999)
    monkeypatch.setattr(main.config, "POST_MOTION_BUFFER_SEC", 9999)
    monkeypatch.setattr(main.storage, "cleanup_old_clips", lambda days=7: None)
    monkeypatch.setattr(main.storage, "get_video_path", lambda: "/clips/test.mp4")
    monkeypatch.setattr(main.motion_detector, "detect", lambda f: (True, f))
    monkeypatch.setattr(main.motion_detector, "new_event_allowed", lambda: True)
    _free = MagicMock()
    _free.free = 10 * 1024 ** 3
    monkeypatch.setattr(main.shutil, "disk_usage", lambda p: _free)

    _mock_camera.reset_mock()
    call_count = [0]

    def fake_get_frame():
        call_count[0] += 1
        if call_count[0] > 3:
            raise KeyboardInterrupt
        return MagicMock()

    _mock_camera.get_frame.side_effect = fake_get_frame
    _mock_camera.start_recording.side_effect = RuntimeError("hardware fault")

    with pytest.raises(KeyboardInterrupt):
        main.main()

    assert main._currently_recording is False, (
        "_currently_recording still True after start_recording() failure — "
        "_shutdown() would call _finish_clip() on a session that was never started"
    )