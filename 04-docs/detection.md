# Motion Detection & Filtering

The detector runs every frame through a pipeline that has five stages. MOG2 and the brightness measurement always run — they are not gated. Filter 0 (scene-change gate) runs first and can short-circuit the frame before blob analysis. Filters 1–3 evaluate the blob characteristics of frames that survive Filter 0. Failure at any stage resets the consecutive-frame counter so short-lived noise cannot accumulate credit across interruptions.

---

## Background subtraction — MOG2

Every frame is passed through OpenCV's MOG2 (Mixture of Gaussians) background subtractor, which builds a statistical model of the scene over time and returns a foreground mask of pixels that have changed significantly.

```python
_bg_subtractor = cv2.createBackgroundSubtractorMOG2(detectShadows=False)
fg_mask = _bg_subtractor.apply(frame)
```

Shadow detection is disabled — on an IR night-vision camera the shadow response is unreliable and adds noise. The foreground mask is then passed to `cv2.findContours()` to identify discrete moving regions (blobs).

---

## Day / night threshold switching

The area threshold applied to blobs is not fixed — it switches based on scene brightness:

```python
brightness = cv2.mean(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))[0]
threshold = MOTION_THRESHOLD_DAY if brightness > BRIGHTNESS_THRESHOLD else MOTION_THRESHOLD_NIGHT
```

Brightness is derived from a grayscale conversion of the BGR frame. Using a raw BGR channel (e.g. `cv2.mean(frame)[0]`, which returns the Blue channel) gives misleading results on IR night-vision cameras: the IR illuminator inflates the Blue channel 5–7× above true luminance, causing night-mode clips to be classified as daytime.

| Config key | Default | Purpose |
|---|---|---|
| `BRIGHTNESS_THRESHOLD` | 60 | Mean grayscale pixel value (0–255) that separates day from night mode |
| `MOTION_THRESHOLD_DAY` | 7 500 px² | Minimum contour area in good light |
| `MOTION_THRESHOLD_NIGHT` | 7 500 px² | Minimum contour area in IR/dark mode |

Both thresholds are currently equal, calibrated from an overnight field dataset (midnight–9:45am, 19 clips). The separate constants are retained so they can be tuned independently as more night data is collected.

---

## Filter 0 — scene-change gate

MOG2 cannot distinguish a global illumination change from real motion — both produce frame-wide foreground. Confirmed false-trigger mechanism (2026-07-22, 07:48–08:28): camera AGC/AEC stepped discretely during sunrise, raising mean frame brightness by ~10+ gray units in a single frame. MOG2 classified this as 919 601 px² of foreground on a 921 600 px² frame — nearly the entire image — triggering 10 consecutive false clips over 40 minutes.

Filter 0 addresses this by tracking mean frame brightness over a rolling window and suppressing detection whenever a significant step is detected:

```python
def _is_scene_transition(gray: float) -> bool:
    _brightness_history.append(gray)
    if len(_brightness_history) < _brightness_history.maxlen:
        return False
    return abs(_brightness_history[-1] - _brightness_history[0]) > config.SCENE_CHANGE_THRESHOLD
```

When `_is_scene_transition()` returns `True`, or while the suppression timer is active, `detect()` returns `False` immediately. MOG2 **continues updating** during suppression — the background model re-adapts to the new brightness level so that legitimate motion after the transition is caught promptly.

A `SCENE_CHANGE` entry is written to the event log the first time the gate fires for each transition.

| Config key | Default | Purpose |
|---|---|---|
| `SCENE_CHANGE_WINDOW_SEC` | 5 | Rolling brightness window length in seconds. Edit this constant — `SCENE_CHANGE_WINDOW_FRAMES` is derived from it. |
| `SCENE_CHANGE_WINDOW_FRAMES` | 150 | Derived: `SCENE_CHANGE_WINDOW_SEC × FPS`. Do not edit directly. |
| `SCENE_CHANGE_THRESHOLD` | 5.0 | Gray-unit end-to-end delta across the window that arms the gate. Calibrated: catches AGC steps (~10+ units); ignores sunrise drift (~0.03 units/5 s) and sensor noise (~1–2 units peak-to-peak). |
| `SCENE_CHANGE_SUPPRESS_SEC` | 10 | Seconds to hold detection suppressed after the gate fires. Gives MOG2 ~300 frames to re-adapt. |

All four constants are GUI-tunable via `config_overrides.json` (restart required; no hardware re-init).

---

## Filter 1 — large-blob gate

At least one contour in the foreground mask must exceed the active area threshold. Anything smaller — insects, sensor noise, compression artifacts — is discarded here.

Failure resets `_consecutive_motion_frames` to zero and clears centroid history. A single-frame spike cannot survive into Filter 3.

---

## Filter 2 — blob coherence

A person moving through the frame appears as one large, contiguous blob. Windblown foliage, reflections, or moving water scatter into many small disconnected specks with roughly equal areas.

Coherence is defined as:

```
coherence = largest_blob_area / total_foreground_pixels
```

If coherence falls below `MIN_BLOB_COHERENCE` (default 0.30), the frame is rejected. The threshold means: "the single largest blob must account for at least 30% of all moving pixels." A person walking past typically scores 0.7–0.95; scattered leaf movement typically scores 0.05–0.20.

Failure also resets the consecutive-frame counter.

---

## Filter 3 — consecutive-frame gate

Even after passing Filters 1 and 2, a single frame is not enough to trigger a recording. The detector requires `MIN_CONSECUTIVE_FRAMES` (default 3) back-to-back frames to all pass both blob filters before returning `True`.

At 30 fps, three consecutive frames is ~0.1 seconds. A person walking through the frame easily sustains this. A brief camera glitch, a single insect crossing the lens, or an isolated windblown leaf rarely does.

The counter is incremented only on a successful pass. Any failure at Filter 1 or Filter 2 resets it to zero — the streak must be unbroken.

---

## Centroid history — infrastructure for translation tracking

For every frame that passes Filters 1 and 2, the centroid of the largest blob is computed and appended to a rolling history of length `CENTROID_HISTORY_LEN` (default 10):

```python
cx = int(M["m10"] / M["m00"])
cy = int(M["m01"] / M["m00"])
_centroid_history.append((cx, cy))
```

A person crossing the frame produces a centroid that moves steadily in one direction (translation). Windblown foliage or reflections produce a centroid that oscillates around a fixed point.

This history is **not yet a hard gate** — it is tracked in preparation for a translation-vs-oscillation discriminator planned for a future calibration step. It does not affect whether the current frame triggers a recording.

---

## Event cooldown — `new_event_allowed()`

`detect()` returns raw per-frame motion state. A separate gate controls how often a new *recording event* can start:

```python
def new_event_allowed():
    if now - _last_motion > MOTION_COOLDOWN_SEC:
        _last_motion = now
        return True
    return False
```

`MOTION_COOLDOWN_SEC` (default 10s) must elapse after the previous event before a new clip and alert can be triggered. This is independent of clip recording — motion can be continuously detected within an active clip without resetting the cooldown.

---

## Filter state reset between events

At the end of every recording session `reset_motion_state()` is called:

```python
def reset_motion_state() -> None:
    global _consecutive_motion_frames, _scene_suppress_until
    _consecutive_motion_frames = 0
    _centroid_history.clear()
    _brightness_history.clear()
    _scene_suppress_until = 0.0
```

This ensures the next event must earn its consecutive-frame count from scratch rather than inheriting leftover state from a previous clip. The scene-change suppression timer and brightness history are also cleared so a transition that occurred during recording does not carry a suppression window into the next event.