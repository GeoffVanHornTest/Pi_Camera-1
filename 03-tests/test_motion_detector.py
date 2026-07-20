import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "02-scripts"))

import config
import motion_detector
import numpy as np

# Frame shape must match production resolution so MOTION_THRESHOLD contour-area
# values are evaluated against the same pixel counts as the real camera.
_W, _H = config.RESOLUTION  # RESOLUTION is (width, height)
_SHAPE = (_H, _W, 3)        # numpy uses (height, width, channels)


def static_frame():
    return np.zeros(_SHAPE, dtype=np.uint8)


def white_frame():
    """Solid white frame — maximally different from a black background model."""
    return np.full(_SHAPE, 255, dtype=np.uint8)


def _warm_up():
    """Feed 30 static frames so MOG2 settles its background model."""
    for _ in range(30):
        motion_detector.detect(static_frame())
    motion_detector.reset_motion_state()


# --- Return-type tests ---


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


# --- Static-scene tests ---


def test_static_frame_does_not_trigger_motion():
    """MOG2 needs several frames to build its background model before it stabilises."""
    for _ in range(30):
        motion, _ = motion_detector.detect(static_frame())
    assert motion is False


# --- Consecutive-frame gate tests (issue #26) ---


def test_motion_requires_min_consecutive_frames():
    """detect() must return False until MIN_CONSECUTIVE_FRAMES have passed."""
    _warm_up()
    results = []
    for _ in range(config.MIN_CONSECUTIVE_FRAMES):
        motion, _ = motion_detector.detect(white_frame())
        results.append(motion)

    # Only the last frame (frame N) should return True; all earlier ones are False.
    assert results[-1] is True
    assert all(r is False for r in results[:-1])


def test_motion_returns_true_on_sustained_motion():
    """Once the gate is open, subsequent motion frames keep returning True."""
    _warm_up()
    # Open the gate
    for _ in range(config.MIN_CONSECUTIVE_FRAMES):
        motion_detector.detect(white_frame())
    # Frames beyond MIN_CONSECUTIVE_FRAMES should also return True
    motion1, _ = motion_detector.detect(white_frame())
    motion2, _ = motion_detector.detect(white_frame())
    assert motion1 is True
    assert motion2 is True


def test_consecutive_counter_resets_on_no_motion():
    """A static frame between motion frames must reset the consecutive counter."""
    _warm_up()
    # Partial run — not enough to open the gate
    for _ in range(config.MIN_CONSECUTIVE_FRAMES - 1):
        motion_detector.detect(white_frame())
    # Static frame resets the counter
    motion_detector.detect(static_frame())
    # Now the counter is back to 0 — first white frame should return False again
    motion, _ = motion_detector.detect(white_frame())
    assert motion is False


# --- reset_motion_state tests ---


def test_reset_motion_state_clears_consecutive_counter():
    """reset_motion_state() must reset the counter so the gate closes again."""
    _warm_up()
    # Open the gate
    for _ in range(config.MIN_CONSECUTIVE_FRAMES):
        motion_detector.detect(white_frame())
    # Reset
    motion_detector.reset_motion_state()
    # Gate should be closed — need to earn MIN_CONSECUTIVE_FRAMES again
    motion, _ = motion_detector.detect(white_frame())
    assert motion is False


# --- Cooldown tests ---


def test_new_event_allowed_blocks_rapid_retriggering(monkeypatch):
    """new_event_allowed() must return False when called within the cooldown window."""
    monkeypatch.setattr(motion_detector, "_last_motion", 0)
    assert motion_detector.new_event_allowed() is True  # first call fires
    assert motion_detector.new_event_allowed() is False  # immediate second call blocked


def test_new_event_allowed_fires_after_cooldown(monkeypatch):
    """new_event_allowed() must return True once MOTION_COOLDOWN_SEC has elapsed."""
    monkeypatch.setattr(
        motion_detector, "_last_motion", time.time() - config.MOTION_COOLDOWN_SEC - 1
    )
    assert motion_detector.new_event_allowed() is True
