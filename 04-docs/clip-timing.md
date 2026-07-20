# Clip Timing & Ring Buffer

Every clip the camera records goes through three timing phases: pre-roll (footage captured before the trigger), active recording (while motion is present), and finalisation (convert and upload). This page explains how each phase works and what config values control it.

---

## Pre-roll — the ring buffer

The camera records continuously into a circular (ring) buffer in memory. When a motion event is triggered, the buffer is flushed to the start of the clip file before live recording continues. This means every clip automatically includes footage from *before* the trigger point — the person entering the frame is always captured, even though recording started after detection.

```python
_encoder = H264Encoder(bitrate=config.VIDEO_BITRATE_BPS)
_circular = CircularOutput(buffersize=int(config.PRE_ROLL_SEC * config.FPS))
_camera.start_recording(_encoder, _circular)
```

| Config key | Default | Effect |
|---|---|---|
| `PRE_ROLL_SEC` | 8 | Target pre-roll duration in seconds |
| `VIDEO_BITRATE_BPS` | 2 500 000 | H264 encoder target bitrate — set explicitly to avoid picamera2's low default |
| `FPS` | 30 | Frames per second; `PRE_ROLL_SEC × FPS` = buffer size in frames |

### Effective pre-roll is slightly less than `PRE_ROLL_SEC`

`CircularOutput` discards frames at the start of a flush until it reaches the first keyframe (IDR frame). An H264 stream cannot be decoded starting from a non-keyframe, so this is intentional. The hardware encoder's default keyframe interval is 60 frames (2 seconds at 30 fps). In the worst case — trigger fires immediately after a keyframe — the buffer discards up to one full keyframe interval:

```
effective pre-roll = PRE_ROLL_SEC - keyframe_interval
                   = 8s - 2s = 6s  (worst case)
```

Observed pre-roll in field testing: **~6–8 seconds**, typically ~6s. If tighter pre-roll is required, set `iperiod=15` on `H264Encoder` (0.5s keyframe interval → max loss 0.5s) or increase `PRE_ROLL_SEC` to compensate.

### Why the buffer is written to a file, not piped directly to ffmpeg

The ring buffer may flush without an SPS/PPS header (H264 stream metadata) at the very start — those headers only appear at keyframe boundaries. ffmpeg reads a pipe sequentially and cannot seek backwards to find them; if they are not first, ffmpeg exits and the resulting MP4 is corrupt.

The solution: flush to a `.h264` file, then convert. ffmpeg probes a file and finds SPS/PPS regardless of offset. After conversion the `.h264` source is deleted.

---

## Clip tail — `POST_MOTION_BUFFER_SEC`

Once a motion event is allowed (`new_event_allowed()` passes the cooldown gate), `start_recording()` is called. The clip ends when motion has been continuously absent for `POST_MOTION_BUFFER_SEC`. Each new detected motion frame resets this countdown.

This acts as a trailing buffer — the clip continues a short time after the last movement so the subject is fully out of frame before recording stops.

| Config key | Default |
|---|---|
| `POST_MOTION_BUFFER_SEC` | 20s |

The minimum clip duration (no motion after the first detection) is `POST_MOTION_BUFFER_SEC` = 20s.

---

## Clip cap — `MAX_RECORD_SEC` and the watchdog

If motion is continuous, `POST_MOTION_BUFFER_SEC` never elapses and the clip grows without bound. `MAX_RECORD_SEC` is a hard cap enforced by a background watchdog thread — independent of the main frame loop:

```python
_watchdog = threading.Timer(config.MAX_RECORD_SEC, _split_event.set)
_watchdog.daemon = True
_watchdog.start()
```

When `_split_event` fires the main loop splits the clip: the current file is finalised and uploaded, and a new recording starts immediately with its own watchdog timer.

| Config key | Default |
|---|---|
| `MAX_RECORD_SEC` | 120s |

### Observed clip duration at watchdog split

With `PRE_ROLL_SEC = 8` and `MAX_RECORD_SEC = 120`, clips that run to the watchdog are **~128s** total: 8s pre-roll flushed at the start plus 120s of live recording. `_arm_watchdog()` is called immediately after `camera.start_recording()` so the timer is not delayed by the Telegram notification (which runs on a daemon thread).

---

## Cooldown between events — `MOTION_COOLDOWN_SEC`

After a clip ends, `new_event_allowed()` gates the next recording start. Only one new event is allowed per `MOTION_COOLDOWN_SEC` window, preventing a continuous subject from triggering back-to-back clips with no gap.

| Config key | Default |
|---|---|
| `MOTION_COOLDOWN_SEC` | 10s |

This is separate from `POST_MOTION_BUFFER_SEC` — motion can be detected continuously within an active clip without resetting the cooldown. The cooldown only applies to starting a *new* clip.

---

## Timing summary

```
                    ┌─ PRE_ROLL_SEC (8s nominal, ~6s effective) ─┐
                    │                                             │
─────────────── ring buffer ─────────────────┬───── active recording ──────────────────
                                        TRIGGER                  │
                                                                  │
                                            ├── POST_MOTION_BUFFER_SEC (20s) ──┤
                                                 (no motion for this long → stop)
                                                                             │
                    ├──────────────── MAX_RECORD_SEC (120s watchdog) ────────┤
                                                              (hard cap → split)
```

### Notification cooldown

Alert emails and Telegram messages have their own independent cooldown (`NOTIFICATION_COOLDOWN_SEC = 60s`) so a rapid sequence of clips does not flood the notification channel.