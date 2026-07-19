# Motion Detection & Filtering

The detector runs every frame in a four-stage pipeline. Each stage must pass before the next runs. Failure at any stage resets the consecutive-frame counter so short-lived noise cannot accumulate credit across interruptions.

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
brightness = cv2.mean(frame)[0]
threshold = MOTION_THRESHOLD_DAY if brightness > BRIGHTNESS_THRESHOLD else MOTION_THRESHOLD_NIGHT
```

| Config key | Default | Purpose |
|---|---|---|
| `BRIGHTNESS_THRESHOLD` | 60 | Mean pixel value (0–255) that separates day from night mode |
| `MOTION_THRESHOLD_DAY` | 7 500 px² | Minimum contour area in good light |
| `MOTION_THRESHOLD_NIGHT` | 25 000 px² | Minimum contour area in IR/dark mode |

The night threshold is significantly higher because IR LED flicker and increased sensor gain at low light produce a noisier foreground mask. Raising the threshold stops the detector treating that noise as motion.

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
def reset_motion_state():
    _consecutive_motion_frames = 0
    _centroid_history.clear()
```

This ensures the next event must earn its consecutive-frame count from scratch rather than inheriting leftover state from a previous clip. Without this, a long recording could exit with `_consecutive_motion_frames` already at 3, making the next trigger instant even if the new motion is marginal.