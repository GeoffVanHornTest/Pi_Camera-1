import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "02-scripts"))

import config
import cv2
import motion_detector
import numpy as np
import pytest

# Frame shape must match production resolution so MOTION_THRESHOLD contour-area
# values are evaluated against the same pixel counts as the real camera.
_W, _H = config.RESOLUTION  # RESOLUTION is (width, height)
_SHAPE = (_H, _W, 3)        # numpy uses (height, width, channels)


@pytest.fixture(autouse=True)
def fresh_motion_detector():
    """Replace the shared MOG2 model with a new instance before each test.

    The background subtractor is a module-level singleton — state accumulated
    in one test (warm-up frames, white frames) would otherwise bleed into the
    next and make test results depend on execution order.
    """
    motion_detector._bg_subtractor = cv2.createBackgroundSubtractorMOG2(
        detectShadows=False
    )
    motion_detector.reset_motion_state()


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


# --- Day/night brightness threshold tests (regression for #60) ---


def colored_frame(bgr_value):
    """Solid frame filled with a specific BGR color."""
    return np.full(_SHAPE, bgr_value, dtype=np.uint8)


def _warm_up_on(base_frame, n=30):
    """Feed n copies of base_frame to settle the MOG2 background model."""
    for _ in range(n):
        motion_detector.detect(base_frame)
    motion_detector.reset_motion_state()


def frame_with_blob(bg_bgr, blob_bgr, blob_size=200):
    """Frame filled with bg_bgr containing a blob_size×blob_size region of blob_bgr."""
    frame = np.full(_SHAPE, bg_bgr, dtype=np.uint8)
    frame[100:100 + blob_size, 100:100 + blob_size] = blob_bgr
    return frame


def test_ir_like_frame_uses_night_threshold(monkeypatch):
    """High-Blue / low-grayscale frame must select MOTION_THRESHOLD_NIGHT.

    Regression for #60: cv2.mean(frame)[0] returns the Blue channel mean.
    On an IR-illuminated frame Blue≈120 > BRIGHTNESS_THRESHOLD(60), so the
    old code selected DAY — causing false detections in the dark.
    After the fix, grayscale≈14 correctly selects NIGHT.

    With MOTION_THRESHOLD_DAY=1 and MOTION_THRESHOLD_NIGHT=100_000:
    - Correct code:   grayscale≈24 < 60 → NIGHT=100k → blob(40k) < 100k → False
    - Old buggy code: Blue≈126     > 60 → DAY=1      → blob(40k) > 1    → True
    """
    monkeypatch.setattr(config, "MOTION_THRESHOLD_DAY", 1)
    monkeypatch.setattr(config, "MOTION_THRESHOLD_NIGHT", 100_000)

    ir_bg = [120, 0, 0]  # Blue=120 > 60; grayscale ≈ 14 < 60
    _warm_up_on(colored_frame(ir_bg))

    motion, _ = motion_detector.detect(frame_with_blob(ir_bg, [255, 255, 255]))
    assert motion is False


def test_bright_non_blue_frame_uses_day_threshold(monkeypatch):
    """Low-Blue / high-grayscale frame must select MOTION_THRESHOLD_DAY.

    Regression for #60: cv2.mean(frame)[0] returns Blue≈0 for a green frame,
    selecting NIGHT — causing missed detections in bright non-blue light.
    After the fix, grayscale≈117 correctly selects DAY.

    With MOTION_THRESHOLD_DAY=1 and MOTION_THRESHOLD_NIGHT=100_000:
    - Correct code:   grayscale≈123 > 60 → DAY=1      → blob(40k) > 1    → True
    - Old buggy code: Blue≈11       < 60 → NIGHT=100k → blob(40k) < 100k → False
    """
    monkeypatch.setattr(config, "MOTION_THRESHOLD_DAY", 1)
    monkeypatch.setattr(config, "MOTION_THRESHOLD_NIGHT", 100_000)

    green_bg = [0, 200, 0]  # Blue=0 < 60; grayscale ≈ 117 > 60
    _warm_up_on(colored_frame(green_bg))

    motion_frame = frame_with_blob(green_bg, [255, 255, 255])
    for _ in range(config.MIN_CONSECUTIVE_FRAMES):
        motion, _ = motion_detector.detect(motion_frame)
    assert motion is True
