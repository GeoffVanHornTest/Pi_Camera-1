# Pi Night Vision Motion Camera — Progress Log

This document captures current project state, key decisions, and setup instructions.
Use it to resume work on a new machine or after a long break.

---

## Current state (2026-07-29, v0.4.3 released)

**Branch:** `main` — v0.4.3 released with motion detection reliability overhaul. Seven areas of work:
1. **Brightness measurement fix (#60)** — day/night threshold selection now uses true grayscale luminance instead of the Blue channel, which IR/red illuminators inflate 5–7×. 13/19 overnight clips had the wrong threshold applied under the old code.
2. **Scene-change gate — two-filter architecture (#96, #97, #98, #100, #104, #105, closes #19)** — Stage A instant-step pre-filter catches single-frame AGC jumps ≥ 8.0 gray units; Stage B rolling-window gate catches sustained drifts ≥ 15.0 units over 5 s. Gate brightness computed from background pixels only so a bright foreground subject cannot arm the gate against itself. Suppress timer extends through the transition and expires `SCENE_CHANGE_SUPPRESS_SEC` after the scene stabilises. Root-caused from 10 false positives in 40 minutes (2026-07-22, 07:48–08:28); field-verified 2026-07-26: 17 HUMAN, 3 LIGHTING, 4 other in 24 clips.
3. **Persistent event log (#93)** — rotating file handler in `05-logs/pi_camera.log` records STARTUP, SHUTDOWN, MOTION, SPLIT, STOP, TELEGRAM, UPLOAD, SCENE_CHANGE, DISK_FULL, SNAPSHOT_FAIL, and FATAL events for post-hoc troubleshooting.
4. **Config override layer (#99, #102, #110, #119, #121–#125, #128, #131–#133, #138–#139)** — `config_overrides.json` allows runtime parameter changes without editing `config.py`. Credential keys blocked. Type coercion, zero/negative guard, non-dict protection, OverflowError guard, math.isfinite() guard for float constants (NaN/±Infinity rejection), and allowlist path guard for CLIPS_DIR/LOG_FILE: only `~/`, `/media/`, `/mnt/` roots accepted; hidden directory components (`.ssh`, `.gnupg`, `.aws`) blocked; symlink check applied to raw input path before `realpath()` (previously dead code); CLIPS_DIR requires existing directory; LOG_FILE requires non-directory path with existing parent dir (was isdir() on both — blocked all valid LOG_FILE overrides and accepted directories, causing IsADirectoryError); `_home` computed with `realpath(expanduser('~'))` for consistent comparison on symlinked-/home systems; `_BASE_DIR` computed with `realpath` so symlinked project deployments are correctly blocked.
5. **Operational reliability fixes** — low-disk guard before recording and in watchdog split path (#107, #127); send_photo resize + backoff + thumbnail-path fix (#106, #113); Telegram API error redaction in event log (#101); SIGTERM shutdown deadline 300 s + `TimeoutStopSec=330` in service file to outlast legitimate work (#108, #111, #112, #126, #129); SIGTERM race fixed (#112); `_shutdown()` reentrancy guard (#130); `_finish_clip()` double-call race closed — flags cleared before call (#131); recording flags reset if `start_recording()` raises (#134); `_arm_watchdog()` cancel-before-clear order corrected (#135); `After=network-online.target` + burst limit added to service file (#136, #137); `_split_event` cleared before `split_recording()` so an exception doesn't cause infinite retry (#141); `cleanup_old_clips()` now catches `PermissionError` so a read-only filesystem doesn't kill the service (#143); cleanup extension filter restricts deletion to `.mp4` and `.jpg` only (#144); **root cause of all SIGTERM bytecode races eliminated** — signal handler now sets a flag only; `_shutdown()` called from the outer `__main__` handler after `main()` returns at a safe iteration boundary, never between bytecodes (#146); **three HIGH-severity bugs fixed (#148–#150)** — consecutive_errors reset moved to end of try block to accumulate on persistent failures; camera.close() wrapped in try/finally in _shutdown(); split_recording() failure now re-arms watchdog in finally block; **seven MEDIUM-severity bugs fixed (#151–#157)** — os.makedirs() guard for CLIPS_DIR-is-file case; LOG_FILE parent-dir realpath validation for post-load TOCTOU; cleanup() pre-listdir symlink check; timer cancel callback yield; _shutdown_called guard atomicity with Lock; test isolation via monkeypatch; test assertion match.
6. **Test hardening (#94, #95, #102, #107, #110, #115, #117, #121–#137, #138–#145)** — session-scoped conftest isolation; regression tests for day/night fix, override layer, disk guard, background-pixel gate, Stage A filter, path containment, NaN/Infinity coercion, shutdown deadline value, watchdog disk-full path, allowlist path guard (positive and negative), TOCTOU existence guard, shutdown reentrancy, double-_finish_clip race, start_recording failure recovery, symlink input rejection, LOG_FILE acceptance/rejection, RLock reentrance, stale split_event, PermissionError in cleanup, and extension filter. Three test isolation bugs fixed: side_effect leak, watchdog timer leak, fragile precondition assertion.
7. **Documentation and code quality** — suppress-window behaviour clarified as "SUPPRESS_SEC after scene stabilises" (#98); ruff CI green (#109); CHANGELOG and PROGRESS updated (#116).

PR #158 merged to `main`. All 57 issues resolved (manually closed — GitHub auto-close requires PRing to the default branch).

**Notification backend:** Telegram + Dropbox. Gmail (`notifier.py`) removed in v0.4.0 housekeeping.

**Tests:** 143 passing, 2 xfailed (known limitations #114, #120). Covers `config`, `storage`,
`motion_detector`, `telegram_notifier`, `dropbox_uploader`, `main`, `event_log`.
`camera.py` excluded (hardware-dependent). New: test_consecutive_errors_accumulates_on_recording_failure, test_split_recording_failure_rearms_watchdog, test_shutdown_calls_camera_close_on_finish_clip_failure.

**Recording config:** 1280×720 @ 30fps, 2.5 Mbps, PRE_ROLL_SEC=8 (effective ~7–8s after keyframe
alignment). Reduced from 1080p/4Mbps to address frame-drop under concurrent load (#53).

**Systemd service:** `pi-camera.service` is **disabled** during calibration.
The deployed `/etc/systemd/system/pi-camera.service` uses `ExecStart=/bin/true` and
`Restart` commented out to prevent the service competing with manual test sessions.
Re-enable after algorithm is finalised (see Pi Hardware Setup Checklist).

**Open issues (post-PR):**

| # | Type | Title |
|---|------|-------|
| 120 | bug | MOG2 absorption of stationary subject causes false scene-change suppression — xfail test added, fix deferred to post-PR calibration |
| 114 | bug | Scene-change gate can suppress real subject via AGC gain response — xfail test added, fix deferred to post-PR calibration |
| 88 | refactor | camera.py acquires hardware at import time — should be deferred to initialize() |
| 20 | enhancement | AI snapshot validation (day/night detection component closed by #60) |
| 21 | enhancement | OpenCV HOG person detector as optional validator |
| 22 | investigation | False-trigger diagnostic suite (suite built — calibration pending) |
| 29 | enhancement | Web GUI — Flask + Tailscale (v0.5.0) |

**Issues resolved on this branch** (all manually closed):

#19, #60, #93, #94, #95, #96, #97, #98, #99, #100, #101, #102, #103, #104, #105, #106, #107, #108, #109, #110, #111, #112, #113, #115, #116, #117, #118, #119, #121, #122, #123, #124, #125, #126, #127, #128, #129, #130, #131, #132, #133, #134, #135, #136, #137, #138, #139, #140, #141, #142, #143, #144, #145, #146, #147, #148, #149, #150, #151, #152, #153, #154, #155, #156, #157

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
| v0.4.3 | 2026-07-29 | Reliability hardening — 10 bugs fixed (#148–#157): SIGTERM race elimination, consecutive-error accumulation, shutdown reentrancy, split-watchdog re-arm, path TOCTOU validation, test infrastructure |

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
├── 03-tests/                # pytest unit tests (128 passing, 2 xfailed)
├── 04-docs/                 # MkDocs source → GitHub Pages
├── .github/workflows/ci.yml # Lint + test on push/PR
├── 00-clips/                # Recorded clips and snapshots (gitignored)
├── 05-logs/                 # Persistent event log output — pi_camera.log (gitignored)
├── 01-reqs/requirements.txt # pip fallback (pyproject.toml is authoritative)
├── pi-camera.service        # systemd unit (production values — see note in file)
├── pyproject.toml           # Project metadata and dependencies
└── mkdocs.yml               # MkDocs config
```