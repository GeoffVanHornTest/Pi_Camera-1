# motion_detector.py
import time
from collections import deque

import config
import cv2
import event_log
import numpy as np

_bg_subtractor = cv2.createBackgroundSubtractorMOG2(detectShadows=False)
_last_motion = 0.0

# Filter state — reset between motion events via reset_motion_state().
_consecutive_motion_frames = 0  # count of back-to-back frames that passed all blob checks
_centroid_history = deque(maxlen=config.CENTROID_HISTORY_LEN)  # (cx, cy) ring buffer

# Scene-change gate state — rolling brightness window + suppress timer.
_brightness_history: deque = deque(maxlen=config.SCENE_CHANGE_WINDOW_FRAMES)
_scene_suppress_until: float = 0.0
_last_gate_brightness: float = 0.0  # previous frame's background brightness for instant-step check


def reset_motion_state() -> None:
    """Reset per-event filter counters.

    Call when a recording session ends so the next motion event must earn
    its consecutive-frame count from scratch rather than inheriting leftover
    state from the previous clip.
    """
    global _consecutive_motion_frames
    _consecutive_motion_frames = 0
    _centroid_history.clear()
    _brightness_history.clear()
    # _scene_suppress_until intentionally NOT reset — the gate timer is a
    # property of the external scene, not of the per-clip detection state.
    # Zeroing it here would re-enable detection mid-transition if a clip
    # ends while the gate is still suppressing (#100).


def _is_scene_transition(gray: float) -> bool:
    """Return True if the rolling brightness window shows a significant jump.

    Appends gray to the history on every call. Once the window is full,
    returns True when the end-to-end delta exceeds SCENE_CHANGE_THRESHOLD.
    A delta this large indicates a global illumination change (AGC/AEC step,
    lights on/off) rather than a person moving through the frame.
    """
    _brightness_history.append(gray)
    if len(_brightness_history) < _brightness_history.maxlen:
        return False
    return abs(_brightness_history[-1] - _brightness_history[0]) > config.SCENE_CHANGE_THRESHOLD


def detect(frame: np.ndarray) -> tuple[bool, np.ndarray]:
    """Analyse a frame for motion — layered filter pipeline.

    The pipeline runs four stages in order. Each stage must pass before the
    next runs. Failure at any stage resets the consecutive-frame counter so
    flickering noise cannot accumulate credit across interruptions.

    Pipeline:
        0. Scene-change gate: if mean frame brightness jumps significantly
           over the rolling window, suppress detection for SCENE_CHANGE_SUPPRESS_SEC
           while MOG2 re-adapts to the new illumination level. MOG2 continues
           updating even while suppressed.
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
    global _consecutive_motion_frames, _scene_suppress_until, _last_gate_brightness

    gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    brightness = cv2.mean(gray_frame)[0]
    threshold = (
        config.MOTION_THRESHOLD_DAY
        if brightness > config.BRIGHTNESS_THRESHOLD
        else config.MOTION_THRESHOLD_NIGHT
    )

    # Always apply MOG2 so the model keeps adapting to the current scene,
    # even when the scene-change gate is suppressing motion detection below.
    fg_mask = _bg_subtractor.apply(frame)

    # Gate brightness from background pixels only — excludes any large/close
    # subject from shifting the brightness metric and arming the gate against
    # itself (#97). Falls back to full-frame mean if MOG2 has no background yet.
    bg_mask = cv2.bitwise_not(fg_mask)
    bg_count = cv2.countNonZero(bg_mask)
    gate_brightness = cv2.mean(gray_frame, mask=bg_mask)[0] if bg_count > 0 else brightness

    # --- Scene-change gate (Filter 0) ---
    # Two-stage check. Stage A catches instantaneous single-frame AGC/AEC steps
    # before the rolling window accumulates enough history (#104). Stage B catches
    # slower transitions using the 5-second rolling window (#96). Both arm
    # SCENE_CHANGE_SUPPRESS_SEC of suppression. The timer only ever extends
    # forward — it is never reset on a repeated fire within the same transition,
    # keeping actual suppression at SCENE_CHANGE_SUPPRESS_SEC not a multiple (#98).
    now = time.time()

    # Stage A — instant-step pre-filter
    prev_gate_brightness = _last_gate_brightness
    _last_gate_brightness = gate_brightness
    instant_delta = abs(gate_brightness - prev_gate_brightness)
    if prev_gate_brightness > 0.0 and instant_delta > config.INSTANT_STEP_THRESHOLD:
        if now >= _scene_suppress_until:
            event_log.log(
                "SCENE_CHANGE",
                f"instant step {instant_delta:.1f} gray units",
            )
        _scene_suppress_until = max(_scene_suppress_until, now + config.SCENE_CHANGE_SUPPRESS_SEC)
        _consecutive_motion_frames = 0
        _centroid_history.clear()
        return False, frame

    # Stage B — rolling-window gate
    if _is_scene_transition(gate_brightness):
        if now >= _scene_suppress_until:
            event_log.log(
                "SCENE_CHANGE",
                f"rolling gate — delta >{config.SCENE_CHANGE_THRESHOLD:.0f} over {config.SCENE_CHANGE_WINDOW_SEC}s",
            )
        _scene_suppress_until = max(_scene_suppress_until, now + config.SCENE_CHANGE_SUPPRESS_SEC)
        _consecutive_motion_frames = 0
        _centroid_history.clear()
        return False, frame

    if now < _scene_suppress_until:
        _consecutive_motion_frames = 0
        _centroid_history.clear()
        return False, frame

    contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

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


def new_event_allowed() -> bool:
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