import os
import sys
import time
from unittest.mock import MagicMock, patch

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
    """_finish_clip() must call camera.stop_recording with an on_complete callback."""
    _mock_camera.reset_mock()
    with patch.object(main.motion_detector, "reset_motion_state"):
        main._finish_clip("/clips/test.mp4")
    _mock_camera.stop_recording.assert_called_once()
    _, kwargs = _mock_camera.stop_recording.call_args
    assert callable(kwargs.get("on_complete"))


def test_finish_clip_resets_motion_state():
    """_finish_clip() must reset the motion detector state."""
    _mock_camera.reset_mock()
    with patch.object(main.motion_detector, "reset_motion_state") as mock_reset:
        main._finish_clip("/clips/test.mp4")
    mock_reset.assert_called_once()


def test_finish_clip_cancels_watchdog(monkeypatch):
    """_finish_clip() must cancel any running watchdog and clear _split_event."""
    monkeypatch.setattr(main.config, "MAX_RECORD_SEC", 5.0)
    main._arm_watchdog()
    _mock_camera.reset_mock()
    with patch.object(main.motion_detector, "reset_motion_state"):
        main._finish_clip("/clips/test.mp4")
    assert not main._split_event.is_set()
    assert main._watchdog is None