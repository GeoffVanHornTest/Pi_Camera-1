# PLAN3 — Independent Analysis (Claude Code, July 2026)

Written from a clean read of every module in `02-scripts/`, the test suite in
`03-tests/`, and `pyproject.toml`. Neither `PLAN.md` nor `PLAN2.md` was consulted
before writing this. Comparisons appear at the end.

---

## Verdict: sound architecture, two logic bugs, one missing system dependency

The module decomposition is clean and the unit tests prove the non-hardware logic
works correctly. But there are two bugs that will cause the camera to behave
incorrectly on first real hardware run, and one missing system dependency that will
cause a silent crash before any of that is reached.

---

## Blocker — will crash before recording anything

### 1. `ffmpeg` is not in the setup checklist

`camera.py` calls `FfmpegOutput(filepath)` to wrap H264-encoded video into an `.mp4`
container. `FfmpegOutput` shells out to the `ffmpeg` binary. If `ffmpeg` is not
installed on the Pi, `start_recording()` will raise an exception the first time
motion is detected — but the import of `camera` will succeed, so there will be
no warning until that moment.

`ffmpeg` is not a default Raspberry Pi OS install and is not mentioned anywhere
in `PLAN.md`, `PROGRESS.md`, or `PLAN2.md`.

**Fix:** add to the hardware setup checklist:
```bash
sudo apt install ffmpeg
```
And verify it's present before the first full test:
```bash
ffmpeg -version
```

---

## Critical — will run but record incorrectly

### 2. The cooldown in `detect()` also suppresses the recording-continue signal

This is the most consequential logic bug in the project.

`motion_detector.detect()` gates its own return value behind
`MOTION_COOLDOWN_SEC` (10 seconds):

```python
if motion_detected and (now - _last_motion) > config.MOTION_COOLDOWN_SEC:
    _last_motion = now
    return True, frame
return False, frame   # hit even while motion is actively ongoing
```

`main.py` uses the same return value to decide whether to keep recording:

```python
if not motion and currently_recording:
    time.sleep(config.POST_MOTION_BUFFER_SEC)  # 5 seconds
    camera.stop_recording()
```

Walk through a 30-second motion event:
- Frame 1: `detect()` returns `True` → recording starts
- Frame 2 (milliseconds later): person still in frame, but cooldown hasn't
  elapsed → `detect()` returns `False` → `main.py` sees "no motion while
  recording" → waits 5 seconds → stops recording
- The person has been in frame for maybe 6 seconds total. The rest is lost.

Every clip will be approximately `POST_MOTION_BUFFER_SEC` (5s) long regardless
of how long the actual event lasts. For a security camera this is not a minor
glitch — it means the system systematically fails to capture what it was built
to capture.

**Root cause:** one boolean is doing two different jobs. "Should a new event
trigger a notification?" should be cooldown-gated. "Is there currently motion
in frame?" should be raw, every frame.

**Proposed fix:** separate these concerns. Have `detect()` return the raw
per-frame signal. Move the event cooldown into a separate function or into
`main.py` itself:

```python
# motion_detector.py — simplified, no cooldown
def detect(frame):
    fg_mask = _bg_subtractor.apply(frame)
    contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    motion = any(cv2.contourArea(c) > config.MOTION_THRESHOLD for c in contours)
    return motion, frame

def new_event_allowed():
    """Return True if enough time has passed to treat this as a new motion event."""
    global _last_motion
    now = time.time()
    if now - _last_motion > config.MOTION_COOLDOWN_SEC:
        _last_motion = now
        return True
    return False
```

`main.py` then uses `detect()` to drive recording (raw signal) and
`new_event_allowed()` only when deciding whether to start a new clip and send
an alert. The notifier's own `NOTIFICATION_COOLDOWN_SEC` (60s) already prevents
email spam independently.

---

## Medium — will run, with silent problems

### 3. `camera.close()` does not fully release the hardware

`camera.py`'s `close()` calls `_camera.stop()`. The correct Picamera2 shutdown
sequence is `stop()` followed by `close()`. Without `close()`, the camera device
file (`/dev/video0`) may remain held after the script exits. On a Pi this often
manifests as "camera already in use" on the next launch, requiring a reboot or
`pkill libcamera` to recover.

**Fix:**
```python
def close():
    _camera.stop()
    _camera.close()   # release the device file
```

### 4. `CLIPS_DIR` resolves relative to wherever you run the script from

`config.py` sets `CLIPS_DIR = "clips"` and `storage.py` calls
`os.makedirs(config.CLIPS_DIR, exist_ok=True)` at import time. This creates
`clips/` relative to the current working directory — which is already visible
in the repo: there is a stray top-level `clips/` directory that was created
by earlier test runs from the repo root, even though the intent was `00-clips/`.

The code and the docs disagree: `PROGRESS.md` references `00-clips/`, the
numbered-folder convention used throughout the project, but no code ever
writes there.

**Fix:** anchor the path to the project root in `config.py`:
```python
BASE_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIPS_DIR = os.path.join(BASE_DIR, "00-clips")
```
Then add to `.gitignore`:
```
00-clips/*
!00-clips/.gitkeep
```

### 5. Email attachment filename includes the directory path

`notifier.py` sets the MIME attachment filename to the full `snapshot_path`
(e.g. `clips/snapshot_2026-07-09_22-30-00.jpg`). The Gmail client will show
the attachment named `clips/snapshot_2026-07-09_22-30-00.jpg` — the leading
`clips/` is cosmetic noise.

**Fix:** one line in `notifier.py`:
```python
filename=os.path.basename(snapshot_path)
```

### 6. `config.FPS` is defined but has no effect

`FPS = 30` is defined in `config.py` but `camera.py` never passes it to
`create_video_configuration()`. The camera will use picamera2's default
framerate, which may or may not be 30fps. This isn't a crash — but it's
dead config that implies control that isn't there.

**Fix:** either wire it up or remove it:
```python
_camera.configure(
    _camera.create_video_configuration(
        main={"size": config.RESOLUTION, "format": "BGR888"},
        controls={"FrameRate": config.FPS},
    )
)
```

---

## Low — hygiene and future-proofing

- **No CI workflow** — `.github/workflows/` doesn't exist. Given the 27
  passing tests, a CI workflow (same pattern as the tutorial's `ci.yml`,
  skipping camera tests) would catch regressions automatically.

- **`ruff` has findings** — `uv run ruff check 02-scripts 03-tests` will
  surface unsorted imports and a few other style issues. Run
  `uv run ruff check --fix .` to clear the auto-fixable ones.

- **No disk space management** — running unattended long-term, the clips
  folder will grow without bound. A cron job or a `cleanup_old_clips(days)`
  function in `storage.py` is worth adding before deploying permanently.

- **No startup credential validation** — if `.env` is missing or the Gmail
  credentials are wrong, nothing fails until the first motion event triggers
  `send_alert()`. A one-time validation at startup (attempt a login, log the
  result) would surface credential problems immediately rather than silently.

- **No process supervision** — no systemd unit to start `main.py` on boot or
  restart it after a crash. Fine for development, necessary for permanent
  deployment.

---

## What the unit tests do and don't cover

| Module | Covered | Not covered |
|---|---|---|
| `config.py` | Types, positive values, cooldown relationship | .env load failure |
| `storage.py` | Path format, file creation | Path-anchoring (CWD issue) |
| `motion_detector.py` | Return type, static-frame no-trigger, cooldown | The recording-continue bug (needs integration test) |
| `notifier.py` | Cooldown, _last_sent update | SMTP auth failure |
| `camera.py` | Nothing — requires real hardware | Everything |

The recording-continue bug (#2 above) is particularly hard to catch in unit
tests because it only manifests in the interaction between `detect()` and
`main.py`'s recording loop — neither module's individual unit tests can see it.
An integration test that feeds many frames through both would catch it.

---

## Priority order for fixes

1. **Verify ffmpeg installed** (`sudo apt install ffmpeg`) — 2 minutes, prevents a
   silent crash on the first real motion event
2. **Fix the cooldown/recording bug** — this is the core product correctness issue
3. **Fix `camera.close()`** — prevents hardware lock on restart
4. **Anchor `CLIPS_DIR` to project root** and fix `.gitignore`
5. **Add CI workflow** — same pattern as the tutorial
6. **Fix attachment filename** and wire up `config.FPS`
7. **Add credential validation at startup** before first deployment

---

## Comparison with PLAN.md and PLAN2.md

**PLAN.md** is a forward-looking design doc — it describes what should be
built and in what order. It does not analyse what was actually built. It
doesn't identify any bugs because it predates the implementation. Still
useful as a reference for intent.

**PLAN2.md** and this plan largely agree on the critical issues (venv
isolation, cooldown bug, CLIPS_DIR, .gitignore). PLAN2 identified the
`picamera2` venv isolation issue — I did not list that above because
PLAN2 already covers it thoroughly and the fix is clear (`uv venv
--system-site-packages`). My additions beyond PLAN2:

- `ffmpeg` missing from setup checklist (new — not in either previous plan)
- `camera.close()` incomplete shutdown (new)
- Startup credential validation (new)
- The unit test coverage gap that makes the cooldown bug hard to catch (new)
- Specific remark that `config.FPS` gives the illusion of control without
  actually having any effect
