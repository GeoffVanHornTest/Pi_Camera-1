# motion_detector.py
import time

import config
import cv2

_bg_subtractor = cv2.createBackgroundSubtractorMOG2(detectShadows=False)
_last_motion = 0

# Two module-level variables, same pattern as _camera in camera.py.

# _bg_subtractor — MOG2 stands for "Mixture of Gaussians 2". It works by
# watching many frames over time and building a statistical model of
# what the "background" looks like. When a new frame comes in,
# anything that doesn't match that model gets painted white in a mask
# — that's your moving object. detectShadows=False tells it
# not to bother classifying shadows separately, which saves
# CPU and keeps the mask simpler.

# _last_motion — stores the timestamp of the last time motion was detected.
# Set to 0 so the very first motion event always triggers immediately
# (same trick we used with _last_sent in notifier.py).


def detect(frame):
    """Analyse a frame for motion — raw per-frame signal, no cooldown.

    Compares the frame against a background model using MOG2. Returns
    True on every frame where real motion is present, regardless of how
    recently a motion event was triggered. Use new_event_allowed() to
    gate whether a new clip or notification should start.

    Args:
        frame: A BGR numpy.ndarray from camera.get_frame().

    Returns:
        tuple: (motion_detected, frame) where motion_detected is a bool
        and frame is the original frame unchanged.
    """
    fg_mask = _bg_subtractor.apply(frame)
    # apply() compares this frame against the background model and returns
    # a mask where white pixels = something moved, black pixels = background

    contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    # find the outlines of white blobs in the mask — each blob is a candidate
    # moving object. RETR_EXTERNAL ignores holes inside blobs, CHAIN_APPROX_SIMPLE
    # stores only corner points rather than every pixel on the edge.

    brightness = cv2.mean(frame)[0]
    threshold = (
        config.MOTION_THRESHOLD_DAY
        if brightness > config.BRIGHTNESS_THRESHOLD
        else config.MOTION_THRESHOLD_NIGHT
    )
    motion_detected = any(cv2.contourArea(c) > threshold for c in contours)
    return motion_detected, frame


def new_event_allowed():
    """Return True if enough time has passed to treat this as a new motion event.

    Separate from detect() so the recording loop can key off the raw motion
    signal while only new clips and alerts are cooldown-gated.

    Returns:
        bool: True if MOTION_COOLDOWN_SEC has elapsed since the last event.
    """
    global _last_motion
    now = time.time()
    if now - _last_motion > config.MOTION_COOLDOWN_SEC:
        _last_motion = now
        return True
    return False
