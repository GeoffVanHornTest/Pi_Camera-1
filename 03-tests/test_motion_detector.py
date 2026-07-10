import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "02-scripts"))

import numpy as np
import motion_detector


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


def test_cooldown_prevents_rapid_retriggering(monkeypatch):
    """Second detection within cooldown window must return False even on genuine motion."""
    # Reset last_motion to 0 so the first call can fire
    monkeypatch.setattr(motion_detector, "_last_motion", 0)

    # Feed enough frames to let MOG2 settle, then inject a white frame
    for _ in range(30):
        motion_detector.detect(static_frame())

    white_frame = np.full((1080, 1920, 3), 255, dtype=np.uint8)
    motion1, _ = motion_detector.detect(white_frame)

    # Immediately call again — cooldown should suppress the second trigger
    motion2, _ = motion_detector.detect(white_frame)
    assert motion2 is False