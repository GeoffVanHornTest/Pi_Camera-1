# Changelog

All notable changes to PI Camera are documented here.

---

## [0.2.0] - 2026-07-17

### Added

- **Telegram + Dropbox notification backend** — replaces Gmail SMTP
  - `telegram_notifier.py`: `send_photo()` sends snapshot inline on motion start; `send_message()` sends Dropbox share link when clip upload completes
  - `dropbox_uploader.py`: OAuth refresh token flow; `upload()` returns a shareable URL
  - 9 new tests (`test_telegram_notifier.py`, `test_dropbox_uploader.py`) — total now 38
- **Recording logic overhaul** (fixes R-01 through R-05, issues #14–#18)
  - `motion_last_seen` timestamp replaces blind `time.sleep(POST_MOTION_BUFFER_SEC)` — recording no longer stops on a single no-motion frame
  - `MAX_RECORD_SEC = 120` hard cap with immediate clip split and new recording start
  - `MIN_RECORD_SEC = 15` minimum — clips shorter than this are not saved
  - `MOTION_COOLDOWN_SEC = 10` cooldown gate via `new_event_allowed()` prevents rapid re-triggering
  - Dropbox upload runs in a daemon thread — main detection loop never blocked
  - `camera.start()` called after `stop_recording()` so `get_frame()` does not block indefinitely (issue #16)
- **Day/night threshold auto-switching** — mean frame brightness selects `MOTION_THRESHOLD_DAY` or `MOTION_THRESHOLD_NIGHT` at runtime
- **8-script false trigger diagnostic analysis suite** (issue #22)
  - `analyze_clips.py`, `analyze_reflections.py`, `combine_analysis.py`, `heatmap_analysis.py`, `brightness_trajectory.py`, `duration_stats.py`, `interval_analysis.py`, `cross_analysis.py`
  - Scores clips 0–9 across 8 signals; assigns PERSON / LIKELY_PERSON / LIKELY_FALSE / FALSE_TRIGGER verdicts
- **Phase 3 algorithm plan** documented in `alt_plan.md` — 5-dataset collection strategy, layered filter pipeline design, calibration workflow (issue #28)
- `pi-camera.service` systemd unit — auto-start and crash recovery (`Restart=always`)
  - Currently **disabled** during camera calibration phase; `ExecStart` commented out

### Fixed

- Telegram `ReadTimeout` no longer crashes the recording loop — both `send_photo()` and `send_message()` now catch all network exceptions and log a warning (issue #24)
- `combine_analysis.py` no longer crashes on clips where `duration_sec = "unreadable"` — all numeric fields wrapped in `try/except`

### Changed

- `MOTION_THRESHOLD_DAY` tuned: 500 → 5000 → 10000 → 7500 (current) based on IR noise floor diagnostic and clip gap analysis
- `POST_MOTION_BUFFER_SEC` raised from 5 → 20 (clip data showed 16s stillness gaps for a desk-work subject)
- Google Drive replaced by Dropbox (Drive rejected service account uploads on personal accounts with a 403)
- `notifier.py` (Gmail SMTP) retained as dead code on this branch — not called from `main.py`

### Known issues / open

- Clip timing violations — `MIN_RECORD_SEC` and `MAX_RECORD_SEC` bounds can be breached because timing checks only run when `get_frame()` returns (#23)
- Recording starts after trigger — first few seconds of motion event are lost; pre-record ring buffer needed (#27)
- False trigger rate high in daytime: 238 false clips in 90-minute empty-room window; scoring system misclassified 235/238 as PERSON/LIKELY_PERSON (#22, #25, #26)
- `MOTION_THRESHOLD_NIGHT = 25000` uncalibrated — IR noise floor diagnostic not yet run (#19)

---

## [0.1.0] - 2026-07-11

### Added

- Motion detection using OpenCV MOG2 background subtraction
- Video recording to timestamped `.mp4` clips via picamera2 + ffmpeg
- Snapshot capture on motion start
- Gmail alert with snapshot attached via SMTP App Password
- Daily clip cleanup (`storage.cleanup_old_clips`) to prevent SD card filling up
- Startup credential validation — clear error if `.env` is incomplete
- Google-style docstrings on all modules
- MkDocs site with Material theme and auto-generated API reference (GitHub Pages)
- pytest unit test suite — 29 tests covering config, storage, motion_detector, notifier
- GitHub Actions CI — lint (ruff) and test on every push and PR
- systemd service unit (`pi-camera.service`) for auto-start and crash recovery
- `uv`-managed dependencies with `pyproject.toml`

### Fixed

- `camera.close()` now calls both `stop()` and `close()` so `/dev/video0` is fully released
- FPS wired up via `controls={"FrameRate": config.FPS}` in camera configuration
- `CLIPS_DIR` anchored to project root using `os.path.abspath(__file__)` — no longer CWD-relative
- `detect()` separated from cooldown logic — recording duration now matches actual motion duration
- Email attachment filename now uses `os.path.basename()` instead of the full filesystem path
- `picamera2` removed from `requirements.txt` — must be installed via `apt`, not pip