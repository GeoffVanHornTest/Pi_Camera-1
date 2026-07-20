# motion_detector.py
import time
from collections import deque

import config
import cv2

_bg_subtractor = cv2.createBackgroundSubtractorMOG2(detectShadows=False)
_last_motion = 0

# Filter state — reset between motion events via reset_motion_state().
_consecutive_motion_frames = 0  # count of back-to-back frames that passed all blob checks
_centroid_history = deque(maxlen=config.CENTROID_HISTORY_LEN)  # (cx, cy) ring buffer


def reset_motion_state():
    """Reset per-event filter counters.

    Call when a recording session ends so the next motion event must earn
    its consecutive-frame count from scratch rather than inheriting leftover
    state from the previous clip.
    """
    global _consecutive_motion_frames
    _consecutive_motion_frames = 0
    _centroid_history.clear()


def detect(frame):
    """Analyse a frame for motion — layered filter pipeline.

    The pipeline runs four stages in order. Each stage must pass before the
    next runs. Failure at any stage resets the consecutive-frame counter so
    flickering noise cannot accumulate credit across interruptions.

    Pipeline:
        1. MOG2 foreground mask + large-blob gate (blob area > threshold).
        2. Blob coherence: largest blob must account for MIN_BLOB_COHERENCE
           fraction of all foreground pixels. Person = one big shape;
           leaves = many scattered specks.
        3. Consecutive-frame gate: MIN_CONSECUTIVE_FRAMES back-to-back passes
           required before returning True. Eliminates single-frame flickers.
        4. Centroid history update. Not yet a hard gate — tracked for the
           translation-vs-oscillation discriminator in the next calibration step.

    Args:
        frame: A BGR numpy.ndarray from camera.get_frame().

    Returns:
        tuple: (motion_detected, frame) where motion_detected is a bool
        and frame is the original frame unchanged.
    """
    global _consecutive_motion_frames

    fg_mask = _bg_subtractor.apply(frame)
    contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    brightness = cv2.mean(frame)[0]
    threshold = (
        config.MOTION_THRESHOLD_DAY
        if brightness > config.BRIGHTNESS_THRESHOLD
        else config.MOTION_THRESHOLD_NIGHT
    )

    # --- Filter 1: large-blob gate ---
    # At least one contour must exceed the area threshold. Anything smaller
    # (insects, sensor noise, compression artifacts) is ignored here.
    if not any(cv2.contourArea(c) > threshold for c in contours):
        _consecutive_motion_frames = 0
        _centroid_history.clear()
        return False, frame

    # --- Filter 2: blob coherence ---
    # A person produces one dominant blob; windblown foliage scatters into
    # many small disconnected specks. Coherence = largest blob area / total
    # foreground pixels. Low coherence means the movement is fragmented.
    total_fg = cv2.countNonZero(fg_mask)
    if total_fg > 0:
        largest_area = max(cv2.contourArea(c) for c in contours)
        coherence = largest_area / total_fg
        if coherence < config.MIN_BLOB_COHERENCE:
            _consecutive_motion_frames = 0
            _centroid_history.clear()
            return False, frame

    # --- Centroid tracking (infrastructure — not yet a hard gate) ---
    # Track the centroid of the largest blob over time. Steady translation
    # indicates a person moving across the frame; oscillation around a fixed
    # point indicates foliage or reflections. The history is kept for the
    # translation-vs-oscillation discriminator in the next calibration step.
    largest_blob = max(contours, key=cv2.contourArea)
    M = cv2.moments(largest_blob)
    if M["m00"] > 0:
        cx = int(M["m10"] / M["m00"])
        cy = int(M["m01"] / M["m00"])
        _centroid_history.append((cx, cy))

    # --- Filter 3: consecutive-frame gate ---
    # Require MIN_CONSECUTIVE_FRAMES successive frames to all pass Filters 1
    # and 2 before returning True. A single bright flash or brief leaf flutter
    # cannot accumulate across gaps — Filter 1/2 failure resets the counter.
    _consecutive_motion_frames += 1
    if _consecutive_motion_frames < config.MIN_CONSECUTIVE_FRAMES:
        return False, frame

    return True, frame


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
