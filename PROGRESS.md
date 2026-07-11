# Pi Night Vision Motion Camera — Progress Log

This document captures all decisions made and code written so far.
Use it to resume work on a new machine or after a long break.

---

## Session Log

### 2026-07-10 — Full audit, 13 issues resolved, hardware test attempted

Independent three-plan analysis of the repo:
- `PLAN2.md` written by a second Claude instance analysing the live code
- `PLAN3.md` written by a third Claude instance independently
- `04-docs/plan-compare.html` — visual side-by-side artifact comparing all three plans
- 13 GitHub issues created and closed (labels: correctness, quality, maintenance)

Issues addressed in this session:

| ID | Title | Fix |
|----|-------|-----|
| C-01 | `camera.close()` incomplete | Added `_camera.close()` after `_camera.stop()` |
| C-02 | Recording stops too early (cooldown in detect) | Separated `detect()` (raw signal) from `new_event_allowed()` (cooldown gate) |
| C-03 | FPS not wired up | Added `controls={"FrameRate": config.FPS}` to `create_video_configuration()` |
| C-04 | ffmpeg not guaranteed on Pi OS | Added install step to hardware checklist |
| M-01 | `CLIPS_DIR` CWD-relative | Anchored with `os.path.abspath(__file__)` in `config.py` |
| M-02 | Missing `.gitignore` entries | Added `00-clips/*`, `!00-clips/.gitkeep`, `clips/` |
| M-03 | `requirements.txt` lists `picamera2` | Replaced with comment explaining apt-only install |
| M-04 | Attachment filename includes full path | Fixed with `os.path.basename(snapshot_path)` |
| M-05 | No daily clip cleanup | Added `storage.cleanup_old_clips(days=7)` called from `main()` |
| L-01 | No CI workflow | Added `.github/workflows/ci.yml` |
| L-02 | No credential validation on startup | Added `_validate_config()` in `main.py` |
| L-03 | No systemd service unit | Added `pi-camera.service` |
| L-04 | ruff errors (27) | `ruff check --fix`, `ruff format`, bumped `line-length` to 100 |

End state: **29 tests passing**, ruff clean, CI green, GitHub Pages live.

Hardware test: `rpicam-hello --timeout 2000` returned "no cameras available".
Likely cause: CSI ribbon cable not fully seated.
**Next step: reseat ribbon cable at both ends (Pi CSI port + camera module), re-run `rpicam-hello`.**

---

## Project Summary

A motion-detection security camera using a Raspberry Pi 4 and an Arducam
5MP OV5647 camera module with IR LEDs for night vision. When motion is
detected the Pi records a video clip, saves a snapshot, and emails an alert
with the snapshot attached to a Gmail address.

---

## Key Decisions Made

| Decision | Choice | Reason |
|---|---|---|
| Notification method | Gmail via SMTP | Rogers Canada discontinued their email-to-SMS gateway. Gmail push notification via the Gmail app works just as well. |
| Gmail auth | App Password (not login password) | Google requires App Passwords for SMTP access when 2-Step Verification is on |
| OpenCV install | `opencv-python-headless` | Pi doesn't need the GUI display components — headless is lighter |
| Motion algorithm | MOG2 background subtraction | Adapts to gradual lighting changes, better than simple frame-diff for night scenes |
| Config format | `config.py` (not JSON) | Pure Python project — no parsing boilerplate, supports logic and comments |
| venv creation | `uv venv --system-site-packages` | `picamera2` is apt-installed into `/usr/lib/python3/dist-packages` and is invisible to an isolated venv; this flag lets the venv reach apt packages |
| `detect()` vs `new_event_allowed()` | Separate functions | `detect()` returns a raw per-frame boolean with no cooldown — this is what the recording loop needs. `new_event_allowed()` gates the *event* (start new clip + send email). Previously a combined detect+cooldown meant a person walking for 30 s would only produce a 10 s clip. |
| `CLIPS_DIR` path | Anchored to `__file__` | `"clips"` is CWD-relative; running pytest from the repo root created stray directories. `os.path.abspath(__file__)` makes it always resolve to `PI_Camera/00-clips/`. |
| `camera.close()` | Both `stop()` and `close()` | `stop()` alone pauses the camera but does not release `/dev/video0`; a subsequent launch fails with a device-busy error. |

---

## Project Structure

```
PI_Camera/
├── 02-scripts/
│   ├── main.py              # Entry point — wires all modules together
│   ├── config.py            # All settings and constants
│   ├── camera.py            # Camera setup, frame capture, video recording
│   ├── motion_detector.py   # Motion detection (detect + new_event_allowed)
│   ├── notifier.py          # Sends Gmail alert with snapshot attached
│   └── storage.py           # Timestamped filenames, clip/disk management
├── 03-tests/                # pytest unit tests (29 passing)
│   ├── test_config.py
│   ├── test_motion_detector.py
│   ├── test_notifier.py
│   └── test_storage.py
├── 04-docs/                 # mkdocs site
│   ├── index.md
│   └── plan-compare.html    # Visual three-plan comparison (served via GitHub Pages)
├── .github/
│   └── workflows/
│       └── ci.yml           # GitHub Actions — lint + test on push/PR
├── 01-reqs/
│   └── requirements.txt     # Third-party deps (pip fallback reference; picamera2 excluded)
├── 00-clips/                # Where recorded video and snapshots are saved
│   └── .gitkeep             # Keeps the folder in git without committing clips
├── PLAN2.md                 # Second-opinion analysis from independent Claude instance
├── PLAN3.md                 # Third independent analysis
├── pi-camera.service        # systemd unit — auto-start and supervise main.py
├── pyproject.toml           # Project metadata and dependencies (uv-managed)
├── uv.lock                  # Locked dependency versions
├── mkdocs.yml               # mkdocs site config
├── .env                     # Secrets — fill in before running (never commit)
└── .gitignore               # Excludes .env and clips/ from version control
```

---

## Dependencies

The project uses `pyproject.toml` as the source of truth, managed with `uv`.

**Runtime** (installed via uv):
```
opencv-python-headless
python-dotenv
```

**picamera2** — installed via apt, not pip:
```bash
sudo apt install python3-picamera2
```
pip/uv cannot install picamera2 correctly on Pi OS — always use apt.
The venv must be created with `--system-site-packages` to reach it:
```bash
uv venv --system-site-packages
uv sync --extra dev
```

**ffmpeg** — required by `FfmpegOutput` in picamera2:
```bash
sudo apt install ffmpeg
```

**Dev** (linting, testing, docs):
```
pytest>=7.0
ruff>=0.4
mkdocs>=1.5
mkdocs-material>=9.0
mkdocstrings[python]>=0.24
```

---

## `.env` File

Create `02-scripts/.env` and fill in your real values.
**Never commit this file** — it is already listed in `.gitignore`.

```
GMAIL_SENDER=your_address@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
GMAIL_RECIPIENT=your_address@gmail.com
```

Generate a Gmail App Password at:
Google Account → Security → 2-Step Verification → App Passwords

---

## Completed Files

### `config.py`

```python
import os
from dotenv import load_dotenv

load_dotenv()

GMAIL_SENDER = os.getenv("GMAIL_SENDER")
GMAIL_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
GMAIL_RECIPIENT = os.getenv("GMAIL_RECIPIENT")

RESOLUTION = (1920, 1080)
FPS = 30

MOTION_THRESHOLD = 500
MOTION_COOLDOWN_SEC = 10

POST_MOTION_BUFFER_SEC = 5
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIPS_DIR = os.path.join(_BASE_DIR, "00-clips")

NOTIFICATION_COOLDOWN_SEC = 60
```

Key change: `CLIPS_DIR` is now anchored to the project root via `__file__` so it resolves
to `PI_Camera/00-clips/` regardless of which directory the script is launched from.

---

### `storage.py`

```python
import os
import time
import cv2
from datetime import datetime
import config

os.makedirs(config.CLIPS_DIR, exist_ok=True)


def get_video_path():
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return os.path.join(config.CLIPS_DIR, f"motion_{timestamp}.mp4")


def get_snapshot_path():
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return os.path.join(config.CLIPS_DIR, f"snapshot_{timestamp}.jpg")


def save_snapshot(frame):
    path = get_snapshot_path()
    cv2.imwrite(path, frame)
    return path


def cleanup_old_clips(days=7):
    """Delete clips older than `days` days to prevent the SD card filling up."""
    cutoff = time.time() - (days * 86400)
    for filename in os.listdir(config.CLIPS_DIR):
        path = os.path.join(config.CLIPS_DIR, filename)
        if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
            os.remove(path)
```

---

### `notifier.py`

```python
import os
import smtplib
import time
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import config

_last_sent = 0


def send_alert(snapshot_path):
    global _last_sent
    now = time.time()
    if now - _last_sent < config.NOTIFICATION_COOLDOWN_SEC:
        return

    msg = MIMEMultipart()
    msg["From"] = config.GMAIL_SENDER
    msg["To"] = config.GMAIL_RECIPIENT
    msg["Subject"] = "Motion Detected!"
    msg.attach(MIMEText("Motion was detected. See the attached snapshot.", "plain"))

    with open(snapshot_path, "rb") as f:
        attachment = MIMEBase("application", "octet-stream")
        attachment.set_payload(f.read())

    encoders.encode_base64(attachment)
    attachment.add_header(
        "Content-Disposition", f"attachment; filename={os.path.basename(snapshot_path)}"
    )
    msg.attach(attachment)

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.ehlo()
        server.starttls()
        server.login(config.GMAIL_SENDER, config.GMAIL_PASSWORD)
        server.sendmail(config.GMAIL_SENDER, config.GMAIL_RECIPIENT, msg.as_string())

    _last_sent = time.time()
```

Key change: `os.path.basename(snapshot_path)` so the recipient sees the filename, not the full path.

---

### `camera.py`

```python
import config
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import FfmpegOutput

_camera = Picamera2()
_camera.configure(
    _camera.create_video_configuration(
        main={"size": config.RESOLUTION, "format": "BGR888"},
        controls={"FrameRate": config.FPS},
    )
)
_camera.start()


def get_frame():
    return _camera.capture_array()


def start_recording(filepath):
    _camera.start_recording(H264Encoder(), FfmpegOutput(filepath))


def stop_recording():
    _camera.stop_recording()


def close():
    _camera.stop()
    _camera.close()  # releases /dev/video0; next launch fails if this is skipped
```

Key changes: `controls={"FrameRate": config.FPS}` now wires up the configured FPS.
`close()` calls both `stop()` and `close()` so the device node is fully released.

---

### `motion_detector.py`

```python
import cv2
import time
import config

_bg_subtractor = cv2.createBackgroundSubtractorMOG2(detectShadows=False)
_last_motion = 0


def detect(frame):
    """Analyse a frame for motion — raw per-frame signal, no cooldown."""
    fg_mask = _bg_subtractor.apply(frame)
    contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    motion_detected = any(
        cv2.contourArea(c) > config.MOTION_THRESHOLD for c in contours
    )
    return motion_detected, frame


def new_event_allowed():
    """Return True if enough time has passed to treat this as a new motion event."""
    global _last_motion
    now = time.time()
    if now - _last_motion > config.MOTION_COOLDOWN_SEC:
        _last_motion = now
        return True
    return False
```

Key change: `detect()` is now a pure per-frame signal. `new_event_allowed()` gates only
the *start* of a new recording event. Previously the cooldown was inside `detect()`,
which caused a 30-second movement to produce only a 10-second clip.

---

### `main.py`

```python
"""Entry point for the PI Camera motion detection system."""

import time
import camera
import config
import motion_detector
import notifier
import storage


def _validate_config():
    missing = [
        name
        for name, value in {
            "GMAIL_SENDER": config.GMAIL_SENDER,
            "GMAIL_APP_PASSWORD": config.GMAIL_PASSWORD,
            "GMAIL_RECIPIENT": config.GMAIL_RECIPIENT,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(
            f"Missing required .env values: {', '.join(missing)}\n"
            "Create 02-scripts/.env with GMAIL_SENDER, GMAIL_APP_PASSWORD, GMAIL_RECIPIENT."
        )


def main():
    _validate_config()
    currently_recording = False
    last_cleanup = 0
    print("PI Camera started. Press Ctrl+C to stop.")

    while True:
        if time.time() - last_cleanup > 86400:
            storage.cleanup_old_clips(days=7)
            last_cleanup = time.time()

        frame = camera.get_frame()
        motion, _ = motion_detector.detect(frame)

        if motion and not currently_recording and motion_detector.new_event_allowed():
            filepath = storage.get_video_path()
            camera.start_recording(filepath)
            snapshot = storage.save_snapshot(frame)
            notifier.send_alert(snapshot)
            currently_recording = True
            print(f"Motion detected — recording to {filepath}")

        if not motion and currently_recording:
            time.sleep(config.POST_MOTION_BUFFER_SEC)
            camera.stop_recording()
            currently_recording = False
            print("Motion stopped — recording saved.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopping PI Camera...")
        camera.close()
        print("Camera released. Goodbye.")
```

Key changes: `_validate_config()` gives a clear error on startup if `.env` is incomplete.
Daily `cleanup_old_clips()` call prevents the SD card filling up over time.
Loop now calls `motion_detector.new_event_allowed()` to gate new event starts.

---

## Testing

Unit tests live in `03-tests/` — **29 tests, all passing**.

Coverage: `config.py`, `storage.py`, `motion_detector.py`, `notifier.py`.
`camera.py` and `main.py` are not unit-tested (depend on live `picamera2` hardware).

Run the suite:
```bash
cd /home/pi/Desktop/PI_Camera
uv run pytest -v
```

Notable test additions this session:
- `test_detect_returns_true_on_consecutive_motion_frames` — verifies `detect()` returns
  True on back-to-back motion frames with no cooldown
- `test_new_event_allowed_blocks_rapid_retriggering` — verifies cooldown gate blocks second call
- `test_new_event_allowed_fires_after_cooldown` — verifies gate reopens after cooldown expires

---

## CI/CD

`.github/workflows/ci.yml` runs on every push and PR to `main`:

```yaml
name: CI
on:
  push:
    branches: ["main"]
  pull_request:
    branches: ["main"]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install uv
        uses: astral-sh/setup-uv@v3
      - name: Install dependencies
        run: uv sync --extra dev
      - name: Lint with ruff
        run: uv run ruff check .
      - name: Run tests
        run: uv run pytest -v
```

Note: the CI environment does not have `picamera2`; all tests mock out hardware calls.

---

## Systemd Service

`pi-camera.service` enables auto-start on boot and automatic restart on crash:

```ini
[Unit]
Description=PI Camera motion detection
After=network.target

[Service]
ExecStart=/home/pi/Desktop/PI_Camera/.venv/bin/python /home/pi/Desktop/PI_Camera/02-scripts/main.py
WorkingDirectory=/home/pi/Desktop/PI_Camera/02-scripts
Restart=always
RestartSec=5
User=pi

[Install]
WantedBy=multi-user.target
```

To install:
```bash
sudo cp /home/pi/Desktop/PI_Camera/pi-camera.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable pi-camera
sudo systemctl start pi-camera
sudo systemctl status pi-camera
```

---

## Documentation

MkDocs site with Material theme and mkdocstrings auto-generated API docs.

```bash
uv run mkdocs serve          # preview locally at http://127.0.0.1:8000
uv run mkdocs gh-deploy      # deploy to GitHub Pages
```

Live site: https://GeoffVanHornTest.github.io/Pi_Camera-1/

The `04-docs/plan-compare.html` page is linked from `index.md` and shows the
side-by-side comparison of the three independent analysis plans.

---

## Pi Hardware Setup Checklist

- [x] Enable camera: `camera_auto_detect=1` in `/boot/firmware/config.txt`
- [ ] **Verify ribbon cable seated at both ends** (Pi CSI port and camera module) — do this first if `rpicam-hello` fails
- [ ] Test camera is detected: `rpicam-hello --timeout 2000`
- [x] Update system: `sudo apt update && sudo apt upgrade`
- [x] Install picamera2 via apt: `sudo apt install python3-picamera2`
- [ ] Install ffmpeg: `sudo apt install ffmpeg`
- [x] Create venv with system-site-packages: `uv venv --system-site-packages`
- [x] Install Python deps: `uv sync --extra dev`
- [x] Fill in `02-scripts/.env` with Gmail credentials
- [ ] Supervised end-to-end test: run `main.py`, walk in front of camera, verify clip in `00-clips/` and email received
- [ ] Install and enable systemd service (see Systemd Service section above)