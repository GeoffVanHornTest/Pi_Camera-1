# Alternative Notification Plan — Telegram + Google Drive

**Status:** Planning only — no existing code changed.

## Release roadmap

| Version | Branch | Content | Status |
|---------|--------|---------|--------|
| v0.1.0 | `main` | Gmail SMTP | **released ✅** |
| v0.2.0 | `feature/telegram-drive` | Telegram + Dropbox, recording overhaul, 8-script analysis suite | **released ✅** |
| v0.3.0 | `feature/detection-filtering` | Blob coherence + consecutive-frame filter pipeline | in development |
| v0.4.0 | `feature/timing-fixes` | Watchdog thread (#23), pre-record ring buffer (#27) | in development |
| v0.5.0 | `feature/gui` | Flask web UI — live view, settings, scheduler, Dropbox FIFO | planned |

---

**This file covers v0.2.0 (Phase 1) and v0.3.0 (Phase 2).**

---

## Why Telegram and not Signal

Signal was considered as an alternative. The comparison:

| | Telegram | Signal |
|---|---|---|
| Bot / automation API | Official, purpose-built | None — requires `signal-cli` (community tool) |
| Implementation | `requests.post` — no extra packages | Java runtime + phone number registration |
| Encryption | Server-client (Telegram can read messages) | End-to-end by default |
| Reliability | Stable official API | signal-cli can break when Signal updates servers |
| Privacy | Closed-source server | Open-source protocol, stronger reputation |
| Clip delivery | `sendVideo` up to 50 MB inline | Works via signal-cli but not seamless |

**Decision: Telegram.** The content being sent is "Motion detected" + a driveway photo.
The privacy risk of Telegram seeing that is low. Signal's E2E advantage is most meaningful
for sensitive personal data (medical, financial, legal) — not home security alerts.
The reliability and simplicity of the official Telegram Bot API are the right tradeoff here.

Signal would be the correct choice for a deployment in a sensitive environment
(law firm, medical practice, etc.) where the complexity of signal-cli is justified.

---

## Overview

Instead of sending an email with an attached snapshot via SMTP, this plan:

1. Sends the snapshot **inline** to a Telegram chat the moment motion is detected
2. Uploads the finished video clip to **Google Drive** once recording stops
3. Sends a second Telegram message with the **shareable Drive link**

This moves clip storage off the SD card, gives instant phone push notifications via
Telegram, and eliminates the MIME email construction entirely.

---

## How the two APIs work

### Telegram Bot API

- Create a bot via [@BotFather](https://t.me/BotFather) on Telegram (takes ~2 minutes)
- BotFather gives you a **bot token**: `7123456789:AAFxxxxxxxxxxxxxxxxxxxxxxx`
- Start a chat with your new bot, then call `GET /getUpdates` to discover your **chat ID**
- From then on, the Pi posts to `https://api.telegram.org/bot{TOKEN}/{method}` — no
  persistent connection, no SDK required, just `requests.post`

Relevant API methods:
| Method | Used for |
|--------|----------|
| `sendPhoto` | Inline snapshot on motion start |
| `sendMessage` | Drive link after clip upload, or error alerts |

### Google Drive API

- Create a **Google Cloud Project** (free), enable the Drive API
- Create a **Service Account** and download its JSON key file
- Share a Drive folder with the service account's email address (e.g. `pi-camera@project.iam.gserviceaccount.com`)
- The Pi uploads files using `google-api-python-client` authenticating with the key file
- After upload, call `files().create(body=..., fields='id,webViewLink')` and use the
  returned `webViewLink` as the link in the Telegram message

No OAuth browser flow — service account auth works headlessly on the Pi.

---

## New notification flow

```
Motion detected
    │
    ├─ save_snapshot(frame)          [existing]
    ├─ telegram_notifier.send_photo(snapshot_path, caption="Motion detected!")
    └─ camera.start_recording(filepath)

Motion stops
    │
    ├─ camera.stop_recording()       [existing]
    ├─ drive_uploader.upload(filepath) → returns shareable_url
    └─ telegram_notifier.send_message(f"Clip ready: {shareable_url}")
```

The snapshot goes immediately (no Drive upload needed — Telegram accepts JPEG directly).
The clip link comes a few seconds later once the upload completes.

---

## New files to create

### `02-scripts/telegram_notifier.py`

Responsibilities:
- `send_photo(image_path, caption)` — POST to `sendPhoto` with the JPEG as a multipart upload
- `send_message(text)` — POST to `sendMessage` with plain text
- Reads `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` from `config`
- No cooldown needed here — Telegram rate-limits at the API level (30 msg/sec to different chats, 1 msg/sec to the same chat); one alert per motion event is well within that

```python
# telegram_notifier.py
import requests
import config

_BASE_URL = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}"


def send_photo(image_path, caption="Motion detected!"):
    with open(image_path, "rb") as f:
        requests.post(
            f"{_BASE_URL}/sendPhoto",
            data={"chat_id": config.TELEGRAM_CHAT_ID, "caption": caption},
            files={"photo": f},
            timeout=15,
        )


def send_message(text):
    requests.post(
        f"{_BASE_URL}/sendMessage",
        data={"chat_id": config.TELEGRAM_CHAT_ID, "text": text},
        timeout=15,
    )
```

### `02-scripts/drive_uploader.py`

Responsibilities:
- `upload(filepath)` — uploads the file to the configured Drive folder, makes it
  readable by anyone with the link, returns the `webViewLink`
- Reads `DRIVE_FOLDER_ID` and `DRIVE_SERVICE_ACCOUNT_JSON` from `config`
- Returns `None` on failure (caller logs and continues)

```python
# drive_uploader.py
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import config

_SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def _service():
    creds = service_account.Credentials.from_service_account_file(
        config.DRIVE_SERVICE_ACCOUNT_JSON, scopes=_SCOPES
    )
    return build("drive", "v3", credentials=creds)


def upload(filepath):
    """Upload a file to the configured Drive folder and return its shareable link."""
    try:
        svc = _service()
        file_metadata = {
            "name": os.path.basename(filepath),
            "parents": [config.DRIVE_FOLDER_ID],
        }
        media = MediaFileUpload(filepath, resumable=True)
        uploaded = svc.files().create(
            body=file_metadata, media_body=media, fields="id,webViewLink"
        ).execute()

        # make the file readable by anyone with the link
        svc.permissions().create(
            fileId=uploaded["id"],
            body={"type": "anyone", "role": "reader"},
        ).execute()

        return uploaded.get("webViewLink")
    except Exception as e:
        print(f"Drive upload failed: {e}")
        return None
```

---

## Changes to existing files

### `config.py` — add new env vars

```python
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")

DRIVE_FOLDER_ID            = os.getenv("DRIVE_FOLDER_ID")
DRIVE_SERVICE_ACCOUNT_JSON = os.getenv(
    "DRIVE_SERVICE_ACCOUNT_JSON",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "service_account.json"),
)
```

### `.env` — add new secrets

```
TELEGRAM_BOT_TOKEN=7123456789:AAFxxxxxxxxxxxxxxxxxxxxxxx
TELEGRAM_CHAT_ID=123456789
DRIVE_FOLDER_ID=1aBcDeFgHiJkLmNoPqRsTuVwXyZ
# DRIVE_SERVICE_ACCOUNT_JSON defaults to 02-scripts/service_account.json
```

### `.gitignore` — add service account key

```
02-scripts/service_account.json
```

### `_validate_config()` in `main.py` — add new required fields

```python
"TELEGRAM_BOT_TOKEN": config.TELEGRAM_BOT_TOKEN,
"TELEGRAM_CHAT_ID":   config.TELEGRAM_CHAT_ID,
"DRIVE_FOLDER_ID":    config.DRIVE_FOLDER_ID,
```

### `main.py` — updated recording block

```python
if motion and not currently_recording and motion_detector.new_event_allowed():
    filepath = storage.get_video_path()
    camera.start_recording(filepath)
    snapshot = storage.save_snapshot(frame)
    telegram_notifier.send_photo(snapshot, caption="Motion detected!")
    currently_recording = True
    print(f"Motion detected — recording to {filepath}")

if not motion and currently_recording:
    time.sleep(config.POST_MOTION_BUFFER_SEC)
    camera.stop_recording()
    currently_recording = False
    print("Motion stopped — uploading clip...")
    url = drive_uploader.upload(filepath)
    if url:
        telegram_notifier.send_message(f"Clip ready: {url}")
        print(f"Clip uploaded: {url}")
    else:
        telegram_notifier.send_message("Clip recorded but upload failed — check SD card.")
```

Note: `notifier.py` (Gmail SMTP) can be left in place or removed. It is not called from
this new flow. Keeping it means Gmail fallback is available if needed.

### `pyproject.toml` — add new dependencies

```toml
dependencies = [
    "opencv-python-headless",
    "python-dotenv",
    "requests",
    "google-api-python-client",
    "google-auth-httplib2",
    "google-auth",
]
```

---

## New tests to write

### `03-tests/test_telegram_notifier.py`

- Mock `requests.post` — verify `sendPhoto` is called with the right URL and chat ID
- Verify `sendMessage` is called with the right text
- Verify a missing/unreadable image path raises (or handles) `FileNotFoundError`

### `03-tests/test_drive_uploader.py`

- Mock `googleapiclient.discovery.build` — verify `files().create()` is called with
  the right folder ID and filename
- Verify `upload()` returns `None` (not an exception) on failure
- Verify `permissions().create()` is called with `role: reader` after a successful upload

---

## One-time setup steps (user does these once)

### Telegram

1. Message [@BotFather](https://t.me/BotFather): `/newbot` → follow prompts → copy token
2. Start a chat with your new bot
3. Visit `https://api.telegram.org/bot{YOUR_TOKEN}/getUpdates` in a browser
4. Find `"chat": {"id": 123456789}` — that number is your `TELEGRAM_CHAT_ID`

### Google Drive

1. Go to [console.cloud.google.com](https://console.cloud.google.com), create a project
2. Enable the **Google Drive API** (APIs & Services → Library)
3. Create a **Service Account** (APIs & Services → Credentials → Create Credentials)
4. Download the JSON key → save as `02-scripts/service_account.json`
5. In Google Drive, create a folder for clips (e.g. "PI_Camera Clips")
6. Share that folder with the service account email (found in the JSON key under `"client_email"`)
7. Copy the folder ID from the Drive URL: `https://drive.google.com/drive/folders/{THIS_PART}`
8. Add it to `.env` as `DRIVE_FOLDER_ID`

---

## What this does NOT change

- `motion_detector.py` — unchanged
- `camera.py` — unchanged
- `storage.py` — `cleanup_old_clips()` becomes optional (clips on Drive, not SD card)
  but can stay in place as a safety net for the local `00-clips/` copy
- All 29 existing tests — unchanged
- CI workflow — unchanged (new tests are additive)

---

## Decision point before starting

The local clip file in `00-clips/` still exists after uploading to Drive.
Two options:

| Option | Behaviour |
|--------|-----------|
| Keep local copy | `00-clips/` fills up; `cleanup_old_clips()` handles it |
| Delete after upload | Disk stays clean; Drive is the only copy |

Recommended: **keep local copy** initially (safer during testing), then switch to
delete-after-upload once Drive uploads are confirmed reliable.

---

## Phase 2 — Setup GUI and unified credential management

Once both notification backends are working and tested independently, the goal is a
**setup GUI** that lets the user choose their preferred method and enter credentials
through a form — no hand-editing of config files or `.env` required.

This also solves a security problem: the current `.env` approach stores credentials
inside the project directory, adjacent to a public git repo. The GUI will write
credentials to `~/.config/pi-camera/settings.json` — outside the repo entirely,
never at risk of being committed.

### Tech choice: Tkinter

Tkinter ships with Python on Pi OS and requires no additional packages. It is the
right choice here — this is a local utility, not a web app, and adding a full web
framework (Flask, etc.) would be overkill for a single setup screen.

### GUI layout

**Screen 1 — Notification method**
```
┌─────────────────────────────────────────┐
│  PI Camera Setup                        │
│                                         │
│  Notification method:                   │
│   ○ Gmail (email with snapshot)         │
│   ● Telegram + Google Drive             │
│                                         │
│              [ Next → ]                 │
└─────────────────────────────────────────┘
```

**Screen 2a — Gmail credentials** (if Gmail selected)
```
┌─────────────────────────────────────────┐
│  Gmail Settings                         │
│                                         │
│  Sender address:  [________________]    │
│  App Password:    [________________]    │
│  Recipient:       [________________]    │
│                                         │
│       [ ← Back ]  [ Save & Test ]       │
└─────────────────────────────────────────┘
```

**Screen 2b — Telegram + Drive credentials** (if Telegram selected)
```
┌─────────────────────────────────────────┐
│  Telegram + Google Drive Settings       │
│                                         │
│  Bot Token:       [________________]    │
│  Chat ID:         [________________]    │
│  Drive Folder ID: [________________]    │
│  Service acct:    [Browse…]             │
│                                         │
│       [ ← Back ]  [ Save & Test ]       │
└─────────────────────────────────────────┘
```

**"Save & Test" behaviour**
- Sends a test notification using the entered credentials before saving anything
- Gmail: sends a plain test email
- Telegram: sends a `sendMessage` with "PI Camera setup complete"
- If the test succeeds: writes `~/.config/pi-camera/settings.json`, shows confirmation
- If the test fails: shows the error inline, does not write any credentials to disk

### `~/.config/pi-camera/settings.json` format

```json
{
  "notification_method": "telegram",
  "telegram": {
    "bot_token": "...",
    "chat_id": "..."
  },
  "drive": {
    "folder_id": "...",
    "service_account_path": "/home/pi/.config/pi-camera/service_account.json"
  }
}
```

For Gmail:
```json
{
  "notification_method": "gmail",
  "gmail": {
    "sender": "...",
    "app_password": "...",
    "recipient": "..."
  }
}
```

The service account JSON key is copied into `~/.config/pi-camera/` by the GUI so it
also lives outside the repo.

### Changes to `config.py`

`config.py` currently reads from `.env`. Once the GUI exists, it reads from
`~/.config/pi-camera/settings.json` instead. The `.env` approach can remain as a
fallback for headless/CI use, checked only if the config file is absent.

```python
import json, os

_CONFIG_PATH = os.path.expanduser("~/.config/pi-camera/settings.json")

if os.path.exists(_CONFIG_PATH):
    with open(_CONFIG_PATH) as f:
        _cfg = json.load(f)
else:
    # fallback to .env for CI / headless use
    from dotenv import load_dotenv
    load_dotenv()
    _cfg = {}
```

### New files to create for the GUI phase

| File | Purpose |
|------|---------|
| `02-scripts/setup_gui.py` | Tkinter setup wizard |
| `02-scripts/notifier_factory.py` | Returns the right notifier module based on `settings.json` |
| `03-tests/test_notifier_factory.py` | Verifies correct module is selected for each method |

### Implementation order

1. ~~Get Gmail path working end-to-end on real hardware~~ — done, released as v0.1.0
2. `feature/telegram-drive` — implement Telegram + Dropbox backend, release as v0.2.0
3. `feature/setup-gui` — Tkinter GUI + `notifier_factory.py`, release as v0.3.0
4. `.env` becomes CI/headless fallback only once the GUI is the standard setup path

---

## Motion detection tuning (in progress on feature/telegram-drive)

### Day/night threshold auto-switching
Uses mean frame brightness to select threshold at runtime:
- `MOTION_THRESHOLD_DAY = 10000` — daylight mode
- `MOTION_THRESHOLD_NIGHT = 25000` — IR/dark mode
- `BRIGHTNESS_THRESHOLD = 60` — mean pixel value below this = night mode

Better IR detection (E-01, future): check if R≈G≈B (channels converge in IR) rather
than relying on brightness alone. Handles edge case where a bright grey room triggers
night mode incorrectly.

### Diagnostic snapshot validator (E-02, future — offline only)
Optional troubleshooting tool, gated by `ENABLE_SNAPSHOT_VALIDATION = False` in config.
When enabled, runs OpenCV HOG person detector on each snapshot and logs results to CSV:
timestamp, contour_area, brightness, person_detected, threshold_used.

- **No API key or internet required** — runs entirely on-device using OpenCV's built-in
  pre-trained HOG + SVM pedestrian detector
- Runs in the background upload thread, does not block the main loop
- Purpose is calibration data collection only — not a real-time filter
- GUI (v0.3.0) will expose the toggle for easy enable/disable

---

## Phase 3 — Noise suppression and body identification algorithm (v0.4.0)

### Motivation

The 8-script diagnostic suite (added 2026-07-14) confirmed that the current MOG2
pixel-count trigger produces significant false positives from:
- Wall reflections (light sweeping across surfaces)
- Small objects moving in the frame (plants, outdoor objects through window)
- MOG2 background drift under gradual lighting changes (morning light rise)

238 confirmed false-trigger clips were recorded in a single 90-minute daytime session
after camera repositioning. The scoring system misclassified 235 of 238 as PERSON or
LIKELY_PERSON. A more robust detection algorithm is needed before the system is
reliable enough to act on without manual review.

### Data collection plan

Five ground-truth datasets, collected before algorithm development begins:

| # | Position | Time of day | Status | Purpose |
|---|----------|------------|--------|---------|
| 1 | Original | Day | Done — 238 clips (2026-07-14) | Empty-room day baseline, original position |
| 2 | New (repositioned) | Day | Done — 18 clips (2026-07-15) | Empty-room day baseline, new position |
| 3 | New | Night | Planned | Empty-room night baseline, new position |
| 4 | Original (approx) | Night | Planned | Empty-room night baseline, original position |
| 5 | TBD | Day (supervised) | Planned | Labelled person clips — short session, operator present |

Dataset 5 is a dedicated supervised run: the operator is physically present and can
label clips in real time as valid or false. This gives a clean positive class for
algorithm training without ambiguity.

### Pre-algorithm review step

Before writing any code, review the heatmap PNGs from datasets 1 and 2 to manually
identify and annotate noise zones:
- Which frame regions correspond to wall reflections
- Which correspond to the outdoor object visible through the window
- Where confirmed person motion appears (from the 2026-07-15 11:01 staircase clip)

This annotation is the ground truth that calibrates the algorithm. It cannot be
derived automatically.

### Algorithm approach (proposed)

A layered filter pipeline in `motion_detector.py`, each layer independently rejectable
via config flags so they can be toggled during calibration:

**Layer 1 — Temporal filter (issue #26)**
Require motion in N consecutive frames before triggering. Rejects single-frame
flicker from reflections and IR artefacts.
```python
MOTION_CONSECUTIVE_FRAMES = 3  # ~200ms at 15fps
```

**Layer 2 — Spatial filter (issue #25)**
Require the largest connected blob to exceed a minimum area. Rejects spatially
dispersed noise (many tiny specks) that passes the pixel-count threshold.
```python
MIN_BLOB_AREA = TBD  # calibrate from dataset 1 vs dataset 5
```

**Layer 3 — Region-of-interest mask (new)**
Allow motion detection only within a configured polygon mask. Zones identified
during heatmap review (window, known reflection surfaces) can be excluded entirely.
Mask defined in config as a list of (x, y) vertices, applied to the MOG2 foreground
mask before any counting.
```python
ROI_MASK_VERTICES = []  # empty = full frame; populated after heatmap review
```

**Layer 4 — MOG2 learning rate (issue #22 fix F4)**
Increase `learningRate` from default (~0.002) to `0.02` so the background model
adapts faster to gradual lighting changes. Addresses Type B false triggers (MOG2
drift under morning light rise).
```python
MOGS_LEARNING_RATE = 0.02
```

### Calibration workflow

1. Collect all 5 datasets
2. Review heatmaps — annotate noise zones, define ROI mask vertices
3. Run Layer 1 + Layer 2 against datasets 1–4 (confirmed empty) — tune thresholds
   until false trigger rate drops below a target (e.g. <5 clips per hour)
4. Validate against dataset 5 (confirmed persons) — verify no true positives are lost
5. Adjust thresholds at the boundary until both conditions hold
6. Commit calibrated values to `config.py`, document in `CHANGELOG.md`

### What this does NOT do

This is a signal-filtering approach, not a classifier. It does not attempt to
identify whether the moving object is a human — it only rejects motion patterns
that are statistically unlikely to be human. A true person classifier (HOG, YOLO,
etc.) is a possible future enhancement but requires significantly more compute and
a labelled training set. E-02 (HOG snapshot validator) in the existing plan is the
stepping stone toward that.

---

## Phase 4 — Web GUI (v0.5.0, feature/gui)

Branch from `feature/timing-fixes` once that is validated on hardware.

### Architecture

**Flask** running as a service on the Pi + **Tailscale** for external access.

- Flask serves an MJPEG stream (live camera view) and a REST API for settings and controls
- Tailscale gives the Pi a stable private IP (`100.x.x.x`) accessible from any device
  where Tailscale is installed — no port forwarding, no public URL, no router config
- Free for personal use (1 user, 100 devices)
- Basic password auth gates the whole UI (`GUI_PASSWORD` in `.env`)
- **Cloudflare Tunnel** is the alternative if a public URL is needed (e.g. to share
  access with others); requires `CLOUDFLARE_TUNNEL_TOKEN` in `.env`
- All API keys remain in `.env` / `config.py` — never in the UI code

### Implementation phases

**Phase 4a — Core (local + Tailscale)**
- Live MJPEG camera stream in browser
- Settings panel — edit all `config.py` values via form, saves to `.env`
- ARM / DISARM toggle — pauses motion detection without stopping the camera
- System status bar — Pi CPU temp, SD card space, current mode (day/night), uptime
- Force relearn button — resets MOG2 background model when camera is moved

**Phase 4b — Scheduler + storage management**
- Daily schedule — set arm/disarm times per day of week (no recording when home)
- **Local clip storage** (user-settable via GUI):
  - `CLIPS_DIR` — storage location (default `00-clips/`, can be redirected to USB drive etc.)
  - `LOCAL_MAX_STORAGE_MB` — size cap; FIFO deletes oldest clips before each new recording
    starts, keeping usage below the cap; replaces the existing time-based `cleanup_old_clips(days=7)`
- **Dropbox storage** (user-settable via GUI):
  - `DROPBOX_MAX_STORAGE_MB` — size cap; FIFO deletes oldest Dropbox clips before upload
    (`1800` MB default — leaves headroom under the 2 GB free cap)
  - Dashboard shows used/total space and lists clips oldest-first
- Both FIFO policies run independently — local and Dropbox can be sized differently

**Phase 4c — Clip review and sensitivity tuning**
- Clip gallery — thumbnails of local clips with playback; mark as person / false / delete
  - Clip list respects `CLIPS_DIR` — works whether clips are on SD card or USB drive
- Sensitivity sliders — live-adjust `MIN_BLOB_COHERENCE`, `MIN_CONSECUTIVE_FRAMES`,
  `MOTION_THRESHOLD_DAY/NIGHT` and see the effect on the live stream
- Zone editor — draw exclusion rectangles on the live view (e.g. the window with trees)
- Motion overlay — highlight detected blobs on the live stream in real time

**Phase 4d — External access (optional)**
- Cloudflare Tunnel toggle — enable/disable from UI, token in `.env`
- Event log — scrollable timeline of motion events with Telegram notification status
- System health alerts — Telegram message if SD card > 80% full or Pi temp > 80°C

### Additional feature ideas

| Feature | Value |
|---------|-------|
| Snapshot gallery | Faster to scan than opening clips — grid of motion-start JPEGs |
| Clip review labels | Mark clips person/false — builds a labelled dataset for future ML |
| Download clips from UI | Stream clip directly from Pi without going to Dropbox |
| Multi-day schedule | Different arm/disarm times per weekday vs weekend |
| Live heatmap tab | Running heatmap of where triggers accumulate, rendered in browser |

### New config keys

```python
# GUI
GUI_PORT                = 8080
GUI_PASSWORD            = os.getenv("GUI_PASSWORD")

# External access (choose one)
TAILSCALE_ENABLED       = True   # default — no extra config needed beyond OS install
CLOUDFLARE_TUNNEL_TOKEN = os.getenv("CLOUDFLARE_TUNNEL_TOKEN")  # alternative

# Local clip storage — location and size cap both user-settable via GUI
CLIPS_DIR               = os.getenv("CLIPS_DIR", os.path.join(_BASE_DIR, "00-clips"))
LOCAL_MAX_STORAGE_MB    = int(os.getenv("LOCAL_MAX_STORAGE_MB", "10000"))  # 10 GB default

# Dropbox FIFO — user-settable via GUI
DROPBOX_MAX_STORAGE_MB  = int(os.getenv("DROPBOX_MAX_STORAGE_MB", "1800"))

# Scheduler
SCHEDULE_ENABLED        = False
SCHEDULE_ARM_TIME       = os.getenv("SCHEDULE_ARM_TIME",    "09:00")
SCHEDULE_DISARM_TIME    = os.getenv("SCHEDULE_DISARM_TIME", "18:00")
```

### New files

| File | Purpose |
|------|---------|
| `02-scripts/gui_server.py` | Flask app — routes, MJPEG stream, REST API |
| `02-scripts/scheduler.py` | Arm/disarm timer logic |
| `02-scripts/storage_manager.py` | Local FIFO cleanup — size-based, replaces time-based `cleanup_old_clips` |
| `02-scripts/dropbox_manager.py` | Dropbox storage audit + FIFO cleanup |
| `05-gui/templates/index.html` | Main dashboard |
| `05-gui/static/` | CSS / JS |
| `03-tests/test_scheduler.py` | Scheduler unit tests |
| `03-tests/test_dropbox_manager.py` | FIFO logic unit tests |