"""Persistent event log for the PI Camera system.

Appends a timestamped line for every motion detection, Telegram send,
Dropbox upload, and any failure of these. Survives restarts — each run
appends to the same rotating log so history accumulates over time.

Log location: config.LOG_FILE  (default: 05-logs/pi_camera.log)
Rotation:     1 MB per file, 5 backups kept  (~5 MB total on disk)

Format:
    2026-07-21 03:47:01 | MOTION         | Recording started → 00-clips/...
    2026-07-21 03:47:01 | TELEGRAM_OK    | Photo sent: 00-clips/snapshot_...
    2026-07-21 04:08:35 | STOP           | Recording stopped
    2026-07-21 04:09:05 | UPLOAD_OK      | https://www.dropbox.com/s/...
"""

import logging
import os
from logging.handlers import RotatingFileHandler

import config

_logger = logging.getLogger("pi_camera.events")
_logger.setLevel(logging.DEBUG)
_logger.propagate = False  # never bubble up to the root logger


def _init(log_file: str) -> None:
    """Initialise (or re-initialise) the rotating file handler.

    Safe to call multiple times — existing handlers are closed and replaced.
    Useful in tests to redirect the log to a temporary path.
    """
    for h in _logger.handlers[:]:
        _logger.removeHandler(h)
        h.close()
    os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)
    handler = RotatingFileHandler(
        log_file,
        maxBytes=1 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    )
    _logger.addHandler(handler)


_init(config.LOG_FILE)


def log(event_type: str, detail: str = "") -> None:
    """Append one timestamped event line to the log file.

    Args:
        event_type: Short uppercase label, e.g. "MOTION", "UPLOAD_FAIL".
        detail:     Optional context string appended after a separator.
    """
    line = f"{event_type:<14}" + (f" | {detail}" if detail else "")
    _logger.info(line)