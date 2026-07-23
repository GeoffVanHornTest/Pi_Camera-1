# Pi Night Vision Motion Camera — Progress Log

This document captures current project state, key decisions, and setup instructions.
Use it to resume work on a new machine or after a long break.

---

## Current state (2026-07-22)

**Branch:** `feature/night-detection` — motion detection reliability overhaul driven by overnight and morning field data. Four areas of work:
1. **Brightness measurement fix (#60)** — day/night threshold selection now uses true grayscale luminance instead of the Blue channel, which IR/red illuminators inflate 5–7×. 13/19 overnight clips had the wrong threshold applied under the old code.
2. **Sunrise/AGC false-trigger gate (#96, closes #19)** — a rolling 5-second brightness window detects discrete camera AGC steps (~10+ gray units) and suppresses MOG2 detection for 10 s while the background model re-adapts. Root-caused from 10 false positives in a 40-minute morning window (2026-07-22, 07:48–08:28).
3. **Persistent event log (#93)** — rotating file handler in `05-logs/pi_camera.log` records STARTUP, MOTION, SPLIT, STOP, TELEGRAM, UPLOAD, SCENE_CHANGE, and FATAL events for post-hoc troubleshooting.
4. **Test hardening (#94 #95)** — session-scoped conftest isolation prevents test runs polluting the production log; two regression tests lock in the grayscale fix against reversion.

10 commits ahead of `dev`. CI extended to cover `dev` branch. PR pending post-overnight-run hardware verification.

**Notification backend:** Telegram + Dropbox. Gmail (`notifier.py`) removed in v0.4.0 housekeeping.

**Tests:** 96 passing. Covers `config`, `storage`, `motion_detector`, `telegram_notifier`,
`dropbox_uploader`, `main`, `event_log`. `camera.py` excluded (hardware-dependent).

**Recording config:** 1280×720 @ 30fps, 2.5 Mbps, PRE_ROLL_SEC=8 (effective ~7–8s after keyframe
alignment). Reduced from 1080p/4Mbps to address frame-drop under concurrent load (#53).

**Systemd service:** `pi-camera.service` is **disabled** during calibration.
The deployed `/etc/systemd/system/pi-camera.service` uses `ExecStart=/bin/true` and
`Restart` commented out to prevent the service competing with manual test sessions.
Re-enable after algorithm is finalised (see Pi Hardware Setup Checklist).

**Open issues (priority order):**

| # | Type | Title |
|---|------|-------|
| 88 | refactor | camera.py acquires hardware at import time — should be deferred to initialize() |
| 20 | enhancement | Improve day/night detection + AI snapshot validation |
| 21 | enhancement | OpenCV HOG person detector as optional validator |
| 22 | investigation | False-trigger diagnostic suite (suite built — calibration pending) |
| 29 | enhancement | Web GUI — Flask + Tailscale (v0.5.0) |

**Issues closed on this branch (auto-close on PR merge):** #60, #93, #96, #19

**Data collected (issue #28):**

| # | Position | Lighting | Status |
|---|----------|----------|--------|
| 1 | Original | Day | Done — 238 clips, 2026-07-14 |
| 2 | New (repositioned) | Day | Done — 18 clips, 2026-07-15 |
| 3 | New | Night | Done — 1 clip (startup trigger only), 2026-07-16 |
| 4 | New | Overnight (midnight–9:45am) | Done — 19 clips, 2026-07-21; used to diagnose #60 and calibrate #19 |
| 5 | New | Morning (06:23–08:28) | Done — 15 clips, 2026-07-22; 5 true positives (people), 10 false positives (sunrise AGC); used to diagnose and fix #96 |
| 5 | Original | Night | Planned — facing open window, car lights expected |
| 6 | TBD | Day (supervised) | Planned — operator present, labelled in real time |

---

## Release history

| Version | Date | Summary |
|---------|------|---------|
| v0.1.0 | 2026-07-11 | Initial release — Gmail, MOG2, MkDocs, CI |
| v0.2.0 | 2026-07-17 | Telegram + Dropbox, recording overhaul, 8-script diagnostic suite |
| v0.3.0 | 2026-07-18 | Layered motion filter pipeline (blob coherence + consecutive-frame gate) |
| v0.4.0 | 2026-07-18 | Ring buffer pre-roll, watchdog thread, file-based H264 pipeline |

See `CHANGELOG.md` for full details.

---

## Key Decisions Made

| Decision | Choice | Reason |
|---|---|---|
| Notification method | Telegram Bot API | Gmail App Passwords inaccessible; instant push photo + text to phone |
| Video storage | Dropbox (refresh token OAuth) | Google Drive rejected service account uploads with 403 |
| Upload threading | `threading.Thread(daemon=True)` | Synchronous upload (30–120s) blocked the main loop entirely |
| Recording stop condition | `motion_last_seen` timestamp | Blind `time.sleep()` stopped recording on any single no-motion frame |
| Pre-roll | CircularOutput ring buffer | Captures footage from before the trigger point |
| H264 recording | `.h264` file → `ffmpeg -c:v copy` | Pipe approach caused SPS/PPS header issues and BrokenPipeError cascade |
| Clip cap enforcement | `threading.Timer` watchdog | Frame-loop timing checks don't fire if `get_frame()` stalls |
| Motion algorithm | MOG2 background subtraction | Adapts to gradual lighting changes; better than frame-diff for night |
| False-positive filtering | Blob coherence + consecutive-frame gate | Reduces scattered/flickering foreground noise without HOG overhead |
| Config format | `config.py` (not JSON/YAML) | Pure Python — supports logic, comments, no parsing boilerplate |
| venv creation | `uv venv --system-site-packages` | `picamera2` is apt-installed and invisible to an isolated venv |
| `CLIPS_DIR` path | Anchored to `__file__` | CWD-relative path created stray directories when running pytest |
| OpenCV install | `opencv-python-headless` | Pi doesn't need GUI display components |

---

## Dependencies

`pyproject.toml` is the source of truth, managed with `uv`.

**Runtime** (installed via uv):
```
opencv-python-headless
python-dotenv
requests
dropbox
```

**System packages** (apt only — cannot be pip-installed):
```bash
sudo apt install python3-picamera2 ffmpeg
```

The venv must be created with `--system-site-packages` to reach apt-installed picamera2:
```bash
uv venv --system-site-packages
uv sync --dev
```

---

## `.env` File

Create `.env`. **Never commit this file** — it is in `.gitignore`.

```
TELEGRAM_BOT_TOKEN=your_bot_token_from_BotFather
TELEGRAM_CHAT_ID=your_numeric_chat_id
DROPBOX_APP_KEY=your_app_key
DROPBOX_APP_SECRET=your_app_secret
DROPBOX_REFRESH_TOKEN=your_refresh_token
```

**Telegram setup:**
1. Message @BotFather → `/newbot` → copy the token
2. Message your bot, then: `curl "https://api.telegram.org/bot<TOKEN>/getUpdates"` — find `"chat": {"id": ...}`

**Dropbox setup:**
1. Create app at dropbox.com/developers → Scoped access, Full Dropbox
2. Copy App Key and App Secret
3. Authorize: `https://www.dropbox.com/oauth2/authorize?client_id=<APP_KEY>&response_type=code&token_access_type=offline`
4. Exchange the code for a refresh token (run immediately — code expires in minutes):
```bash
curl -X POST https://api.dropbox.com/oauth2/token \
  -d code=<AUTH_CODE> \
  -d grant_type=authorization_code \
  -d client_id=<APP_KEY> \
  -d client_secret=<APP_SECRET>
```
Copy `refresh_token` from the response.

---

## Pi Hardware Setup Checklist

- [x] Enable camera: `camera_auto_detect=1` in `/boot/firmware/config.txt`
- [x] Verify ribbon cable seated at both ends (Pi CSI port and camera module)
- [x] Test camera is detected: `rpicam-hello --timeout 2000`
- [x] Update system: `sudo apt update && sudo apt upgrade`
- [x] Install picamera2 via apt: `sudo apt install python3-picamera2`
- [x] Install ffmpeg: `sudo apt install ffmpeg`
- [x] Create venv with system-site-packages: `uv venv --system-site-packages`
- [x] Install Python deps: `uv sync --dev`
- [x] Fill in `.env` with Telegram and Dropbox credentials
- [x] Supervised end-to-end test: clip recorded, Telegram snapshot received, Dropbox link received
- [ ] Re-enable systemd service after calibration complete:
  ```bash
  sudo nano /etc/systemd/system/pi-camera.service
  # restore ExecStart and Restart=always, remove ExecStart=/bin/true
  sudo systemctl daemon-reload
  sudo systemctl enable --now pi-camera
  ```

---

## Project Structure

```
PI_Camera/
├── 02-scripts/
│   ├── main.py              # Entry point — detection loop, watchdog, clip lifecycle
│   ├── config.py            # All settings and constants
│   ├── camera.py            # Camera init, ring buffer, H264 recording
│   ├── motion_detector.py   # MOG2 + layered filter pipeline
│   ├── storage.py           # Timestamped filenames, cleanup
│   ├── telegram_notifier.py # Telegram Bot API — send_photo(), send_message()
│   ├── dropbox_uploader.py  # Dropbox OAuth + upload, returns shareable URL
│   ├── event_log.py         # Persistent event log — motion, Telegram, Dropbox, scene-change outcomes
│   ├── verify_timing.py     # Post-run validation: pre-roll and MP4 validity
│   ├── run_test.sh          # Stop-after-N-clips field test helper
│   └── analyze_*.py         # 9-script false trigger diagnostic suite
├── 03-tests/                # pytest unit tests (96 passing)
├── 04-docs/                 # MkDocs source → GitHub Pages
├── .github/workflows/ci.yml # Lint + test on push/PR
├── 00-clips/                # Recorded clips and snapshots (gitignored)
├── 05-logs/                 # Persistent event log output — pi_camera.log (gitignored)
├── 01-reqs/requirements.txt # pip fallback (pyproject.toml is authoritative)
├── pi-camera.service        # systemd unit (production values — see note in file)
├── pyproject.toml           # Project metadata and dependencies
└── mkdocs.yml               # MkDocs config
```