import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "02-scripts"))

import motion_detector
import numpy as np


def static_frame():
    return np.zeros((1080, 1920, 3), dtype=np.uint8)


def test_detect_returns_tuple():
    result = motion_detector.detect(static_frame())
    assert isinstance(result, tuple)


def test_detect_returns_two_values():
    result = motion_detector.detect(static_frame())
    assert len(result) == 2


def test_detect_first_value_is_bool():
    motion, _ = motion_detector.detect(static_frame())
    assert isinstance(motion, bool)


def test_detect_second_value_is_ndarray():
    _, frame = motion_detector.detect(static_frame())
    assert isinstance(frame, np.ndarray)


def test_static_frame_does_not_trigger_motion():
    """MOG2 needs several frames to build its background model before it stabilises."""
    # Feed the same blank frame many times to let MOG2 build its background model
    for _ in range(30):
        motion, _ = motion_detector.detect(static_frame())
    assert motion is False


def test_detect_returns_true_on_consecutive_motion_frames():
    """detect() returns True on every motion frame — no cooldown applied."""
    for _ in range(30):
        motion_detector.detect(static_frame())

    white_frame = np.full((1080, 1920, 3), 255, dtype=np.uint8)
    motion1, _ = motion_detector.detect(white_frame)
    motion2, _ = motion_detector.detect(white_frame)
    # both calls should return True — cooldown is no longer detect()'s responsibility
    assert motion1 is True
    assert motion2 is True


def test_new_event_allowed_blocks_rapid_retriggering(monkeypatch):
    """new_event_allowed() must return False when called within the cooldown window."""
    monkeypatch.setattr(motion_detector, "_last_motion", 0)
    assert motion_detector.new_event_allowed() is True  # first call fires
    assert motion_detector.new_event_allowed() is False  # immediate second call blocked


def test_new_event_allowed_fires_after_cooldown(monkeypatch):
    """new_event_allowed() must return True once MOTION_COOLDOWN_SEC has elapsed."""
    import config

    monkeypatch.setattr(
        motion_detector, "_last_motion", time.time() - config.MOTION_COOLDOWN_SEC - 1
    )
    assert motion_detector.new_event_allowed() is True
