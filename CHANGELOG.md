# Changelog

All notable changes to PI Camera are documented here.

---

## [Unreleased]

### Fixed

- **Bot token leaked in exception logs (#75)** — `telegram_notifier._safe_err()` redacts `TELEGRAM_BOT_TOKEN` from exception strings before printing; connection errors (which include the full URL) no longer expose the token in stdout or systemd journal
- **Busy-loop CPU spike on camera error (#70)** — main loop `except` block now sleeps 1s per consecutive error and raises `RuntimeError` after 10, exiting cleanly so systemd can restart and re-initialise hardware
- **Notification cooldown not enforced (#71)** — `send_photo()` checks `_last_photo_sent` against `NOTIFICATION_COOLDOWN_SEC`; rapid re-triggers no longer flood the Telegram chat
- **`_finish_clip()` stale `filepath` parameter (#62)** — parameter removed; path is internal to `camera.stop_recording()` and was unused at the call site
- **Duplicate `_upload_and_notify` closures (#63)** — promoted to a module-level function; the two identical inline closures in the split and finish paths are replaced with a single definition
- **Stale config comments (#67, #72)** — `RESOLUTION`, `VIDEO_BITRATE_BPS`, and `NOTIFICATION_COOLDOWN_SEC` comments updated to reflect current values; `MOTION_COOLDOWN_SEC` and `POST_MOTION_BUFFER_SEC` cross-referenced to clarify their distinct roles
- **Phantom `dropbox` dependency in requirements.txt (#68)** — stale entry removed; `pyproject.toml` is the authoritative dependency list
- **Stale `clips/` entry in `.gitignore` (#73)** — replaced by `00-clips/` (correct directory name since v0.2.0)
- **`strftime` microsecond magic-number slice in `storage.py` (#64)** — `%f` and `[:23]` removed; second-precision timestamps are sufficient given `MOTION_COOLDOWN_SEC = 10`
- **`.env` path in README and docs (#61)** — corrected from `02-scripts/.env` to repo root `.env`; `.env.example` added at repo root with current Telegram + Dropbox keys only
- **`pyproject.toml` version and description stale (#58)** — version bumped to 0.4.2; description updated to reference Telegram + Dropbox
- **`clip-timing.md` stale content** — `MIN_RECORD_SEC` section removed (constant deleted in #43), `PRE_ROLL_SEC` updated 5→8, watchdog narrative corrected (~140s bug note replaced with accurate ~128s), ASCII timing diagram updated

### Fixed (cont.)

- **Day/night detection used Blue channel instead of grayscale (#60)** — `cv2.mean(frame)[0]` returned the Blue channel mean on a BGR frame, not luminance. IR illuminators inflate the Blue channel 5–7× above true brightness, so the system was classifying IR night clips as daytime and applying the wrong threshold. Fixed to `cv2.mean(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))[0]`. Field analysis showed 13/19 overnight clips (68%) had the wrong day/night threshold as a result.
- **`MOTION_THRESHOLD_NIGHT` uncalibrated — real motion suppressed (#19)** — threshold was set to 25 000 px² without field data. Overnight dataset analysis (19 clips, midnight–9:45am) showed 50s+ detection gaps on confirmed motion events at T=25 000. Recalibrated to 7 500 to match `MOTION_THRESHOLD_DAY`; field-verified on the same dataset.
- **Stale `MIN_RECORD_SEC` reference in `analyze_clips.py`** — constant was removed in #43; script crashed at the summary print. Fixed to `MAX_RECORD_SEC`.
- **Dropbox-API-Arg built with f-string (#76)** — replaced with `json.dumps()`; filenames containing `"` or `\` no longer produce invalid JSON in the upload header
- **Test frame shape mismatch (#77)** — `test_motion_detector.py` now derives frame dimensions from `config.RESOLUTION` (720p) instead of a hardcoded 1080p constant; tests match the production resolution
- **Cooldown slot consumed when snapshot raises (#78)** — `_currently_recording = True` is now set before `save_snapshot()` so a snapshot failure does not silently consume the `new_event_allowed()` cooldown slot while leaving no clip
- **`on_complete` identity not verified in test (#79)** — `test_finish_clip_calls_stop_recording` now asserts `on_complete is main._upload_and_notify` (identity) instead of `callable(on_complete)` (any callable)
- **Active recording lost on shutdown (#80)** — added module-level `_currently_recording` flag; `_shutdown()` calls `_finish_clip()` before `camera.close()` when a clip is in progress. Follow-up fix: ffmpeg conversion threads changed from `daemon=True` to `daemon=False` so Python's interpreter shutdown waits for `on_complete()` to fire — previously `sys.exit(0)` killed the daemon thread before `_upload_and_notify` could run, silently dropping the upload and Telegram notification on every graceful shutdown with an active clip
- **`list.pop(0)` in centroid history (#81)** — replaced with `collections.deque(maxlen=CENTROID_HISTORY_LEN)`; O(1) rotation, no manual length guard
- **TOCTOU race in `cleanup_old_clips()` (#82)** — `os.remove()` now wrapped in `try/except FileNotFoundError`; a concurrent removal between the `isfile()` check and the `remove()` call no longer raises
- **Invalid package name in `pyproject.toml` (#83)** — `[build-system]` / `hatchling` / `packages = ["02-scripts"]` block removed; replaced with `[tool.uv] package = false` (application project, not a library)
- **Dropbox token refetched on every upload (#84)** — `_get_access_token()` now caches the token with a 4-hour TTL and a 60s safety margin; subsequent uploads within the window reuse the cached token without a network round-trip
- **Shared MOG2 state between tests (#85)** — `test_motion_detector.py` gains an autouse fixture `fresh_motion_detector` that replaces `_bg_subtractor` with a fresh MOG2 instance before each test; ordering-dependent failures eliminated
- **`_log_clip_quality` labels 0% as 'gain' (#86)** — ternary corrected to `"drop" if drop_pct > 0 else ("gain" if drop_pct < 0 else "ok")`
- **Dropbox 150MB limit not enforced (#87)** — `upload()` checks `os.path.getsize()` before calling the API; files over `_UPLOAD_MAX_BYTES` return `None` immediately with a clear log message
- **griffe warnings under `mkdocs --strict` (#89)** — type annotations added to all public functions in `telegram_notifier.py`, `dropbox_uploader.py`, `motion_detector.py`, and `storage.py`; `mkdocs build --strict` now exits clean
- **RuntimeError from consecutive-error backoff skips `_shutdown()` (#90)** — the `__main__` guard now catches all exceptions (not just `KeyboardInterrupt`), routing fatal errors through `_shutdown()` for clip finalisation and `camera.close()`; `_MAX_CONSECUTIVE_ERRORS` hoisted to module level for testability
- **Dropbox exceptions expose credentials (#91)** — `_safe_err()` added to `dropbox_uploader.py`; redacts `DROPBOX_APP_KEY`, `DROPBOX_APP_SECRET`, `DROPBOX_REFRESH_TOKEN`, and the cached access token from exception strings, consistent with the pattern established for Telegram in #75
- **Stale "Alert emails" phrase in `clip-timing.md`** — corrected to "Telegram alerts"; Gmail was removed in v0.4.0

### Added

- **Persistent event log (#93)** — `event_log.py` appends one timestamped line per event to `05-logs/pi_camera.log`. Covers `STARTUP`, `SHUTDOWN`, `MOTION`, `SPLIT`, `STOP`, `ERROR`, `FATAL`, `SNAPSHOT_FAIL`, `TELEGRAM_OK/FAIL/SKIP`, `UPLOAD_OK/FAIL/SKIP`. Rotating handler: 1 MB per file, 5 backups (~5 MB max). Credentials redacted via each module's existing `_safe_err()` before any string reaches the log. Useful for post-hoc troubleshooting when no one is present to watch the terminal.
- **`analyze_brightness_channels.py`** — diagnostic script that samples the first 10 frames of each clip and compares Blue-channel mean, ITU-R BT.601 luminance, and OpenCV grayscale. Reports whether each clip had the correct day/night threshold applied (used to quantify #60 impact).
- **Event log tests** — `test_event_log.py`: 9 tests covering file creation, format, multi-line append, event type padding, and `config.LOG_FILE` location.
- **Watchdog split test (#65)** — `test_watchdog_split_calls_split_recording` verifies `camera.split_recording` is called with `on_complete=main._upload_and_notify` when `_split_event` fires
- **`_upload_and_notify` tests (#74)** — two new tests verify the Dropbox link is sent on success and the fallback message is sent on upload failure
- **Token-redaction tests (#75)** — three new tests: `_safe_err` replaces the token, `_safe_err` survives an empty token, and `send_photo` exception does not print the token to stdout
- **Shutdown / recording-continuity tests (#78, #79, #80)** — `test_shutdown_calls_finish_clip_when_recording`, `test_shutdown_skips_finish_clip_when_not_recording`, `test_recording_continues_when_snapshot_raises`
- **Token-cache tests (#84)** — `test_get_access_token_caches_token`, `test_get_access_token_refreshes_when_expired`, `test_upload_returns_none_for_oversized_file`, `test_upload_api_arg_header_is_valid_json`
- **TOCTOU test (#82)** — `test_cleanup_does_not_raise_if_file_deleted_concurrently`
- **`verify_shutdown.py` (#80)** — hardware integration test; starts recording directly, calls `_finish_clip()`, waits for the MP4, and validates it with `ffprobe`. Hardware-verified: 6.2s MP4, 1945 KB
- **Thread map** — swimlane sequence diagram added to MkDocs docs (`thread-map.html`) showing all four concurrent threads and their interactions across a full recording lifecycle
- **Consecutive-error tests (#90)** — `test_main_raises_after_max_consecutive_errors` and `test_consecutive_error_counter_resets_on_success` cover the escalation path and counter-reset behaviour
- **Dropbox credential-redaction tests (#91)** — `test_safe_err_redacts_app_key`, `test_safe_err_redacts_cached_token`, `test_upload_exception_does_not_log_credentials`

---

## [0.4.2] - 2026-07-19

### Fixed

- **Dead variable `recording_started` (#56)** — left over from the #43 `MIN_RECORD_SEC` cleanup; assigned three times but never read, causing ruff F841 and a broken CI pipeline on trunk

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