# Alternative Notification Plan — Telegram + Google Drive

**Status:** Planning only — no existing code changed.

## Release roadmap

| Version | Branch | Content |
|---------|--------|---------|
| v0.1.0 | `main` | Gmail SMTP — **released ✅** |
| v0.2.0 | `feature/telegram-drive` | Telegram + Google Drive backend |
| v0.3.0 | `feature/setup-gui` | Tkinter setup GUI + unified credential management |

---

**This file covers v0.2.0 (Phase 1) and v0.3.0 (Phase 2).**

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
2. `feature/telegram-drive` — implement Telegram + Drive backend, release as v0.2.0
3. `feature/setup-gui` — Tkinter GUI + `notifier_factory.py`, release as v0.3.0
4. `.env` becomes CI/headless fallback only once the GUI is the standard setup path