# Changelog

All notable changes to PI Camera are documented here.

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