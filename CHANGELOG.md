# Changelog

All notable changes to PI Camera are documented here.

---

## [0.4.1] - 2026-07-19

### Fixed

- **Dropbox upload race (#54)** — upload now fires via `on_complete` callback after ffmpeg signals success; previously `stop_recording()` returned immediately and the upload thread ran before the MP4 existed
- **Consecutive-clip pre-roll loss (#55)** — `split_recording()` switches `CircularOutput.fileoutput` directly without calling `stop()`, preserving the ring buffer for the next clip; `stop()` drains the deque and would have cleared it
- **Watchdog arms before Telegram send (#35)** — `_arm_watchdog()` moved before `send_photo()` so network latency no longer counts against the MAX_RECORD_SEC budget
- **ffmpeg blocking the detection loop (#34/#42)** — `stop_recording()` now spawns a background thread for ffmpeg conversion; main loop is never blocked
- **Frame drops under load (#53)** — moved to 720p / 2.5 Mbps; field-verified <1% duration error (was ~18% at 1080p / 4 Mbps). ffmpeg runs at `nice -n 10` to yield to the encoder during watchdog splits
- **SIGTERM not handled (#36)** — `signal.SIGTERM` now calls shared `_shutdown()` alongside `KeyboardInterrupt`; `camera.close()` runs on `systemctl stop` / `kill`, preventing hardware lock and crash-restart loops
- **`cv2.imwrite` silent failure (#37)** — `save_snapshot()` now raises `RuntimeError` if `imwrite` returns `False`
- **Telegram API errors silent (#39)** — `send_photo()` and `send_message()` check `response.json()["ok"]` and log a warning on failure
- **`combine_analysis.py` crash on empty join (#40)** — early exit with a clear message when no clips matched both datasets
- **`MIN_RECORD_SEC` dead code (#43)** — constant removed from `config.py`; elif condition in `main.py` simplified to check only `POST_MOTION_BUFFER_SEC`

### Changed

- `RESOLUTION`: 1920×1080 → 1280×720
- `VIDEO_BITRATE_BPS`: 4 000 000 → 2 500 000
- `PRE_ROLL_SEC`: 5 → 8 (more buffer headroom now that frame drops are resolved)
- After each clip conversion, `ffprobe` logs actual vs expected duration so frame-drop regressions are visible in the terminal

---

## [0.4.0] - 2026-07-18

### Added

- **Pre-record ring buffer** — `CircularOutput` runs continuously; every clip automatically includes `PRE_ROLL_SEC = 5s` of footage from before the trigger point (issue #27)
  - Effective pre-roll ~3–5s due to H264 keyframe alignment (2s default iperiod); documented in issue #31
- **Watchdog thread** — `threading.Timer` fires after `MAX_RECORD_SEC` independent of `get_frame()` latency, enforcing the clip cap even if the camera stalls (issue #23)
- `verify_timing.py` — post-run validation script; checks pre-roll, clip duration, and watchdog split behaviour across a recorded dataset
- `run_test.sh` — stop-after-N-clips test helper for controlled field sessions
- MkDocs pages: **Motion Detection & Filtering** and **Clip Timing & Ring Buffer**

### Fixed

- `CircularOutput.fileoutput` rejected `FfmpegOutput` with `RuntimeError: Must pass io.BufferedIOBase` — every trigger silently failed (issue #30); fixed by writing to a `.h264` file handle instead
- CircularOutput flushed without guaranteed SPS/PPS header at stream start — ffmpeg pipe exited immediately, corrupting the MP4 and crashing picamera2's encoder thread, stopping all subsequent detection (issue #33); fixed by writing to a named `.h264` file and converting with `subprocess.run()` after close
- `H264Encoder` default bitrate (~1 Mbps) mismatched assumed 10 Mbps, producing 50s of buffer instead of 5s (issue #31); explicit `VIDEO_BITRATE_BPS = 4_000_000` added to config
- `CircularOutput(buffersize=...)` unit is frames, not bytes — bytes-based calculation produced 2.5 million frames (~23 hours of buffer); corrected to `PRE_ROLL_SEC * FPS = 150` frames (issue #31)
- `stop_recording()` `_proc.wait()` had no timeout — blocked main loop indefinitely during watchdog clip split, preventing second clip from starting (issue #32); resolved by switching to `subprocess.run(..., timeout=30)`

### Changed

- Camera output pipeline: CircularOutput → `.h264` file → `ffmpeg -c:v copy` → `.mp4` (replaces pipe-to-ffmpeg approach)
- `VIDEO_BITRATE_BPS` added to `config.py`; passed to `H264Encoder(bitrate=...)` to avoid picamera2's low default

---

## [0.3.0] - 2026-07-18

### Added

- **Layered motion filter pipeline** — two new filters sit between MOG2 and the recording trigger, dramatically reducing false positives (issues #25, #26)
  - **Blob coherence gate** (`MIN_BLOB_COHERENCE = 0.30`): largest blob must account for ≥ 30% of total foreground pixels — a person scores 0.7–0.95; scattered foliage scores 0.05–0.20
  - **Consecutive-frame gate** (`MIN_CONSECUTIVE_FRAMES = 3`): 3 unbroken frames must pass all blob checks before `detect()` returns `True` — single-frame flickers and brief glints cannot trigger a clip
  - **Centroid history** (`CENTROID_HISTORY_LEN = 10`): centroid of the largest blob tracked over time; infrastructure for a future translation-vs-oscillation discriminator (not yet a hard gate)
  - `reset_motion_state()` added — resets consecutive-frame counter and centroid history between events so the next trigger must earn its count from scratch

### Changed

- `detect()` now returns `(bool, frame)` tuple; callers updated accordingly

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