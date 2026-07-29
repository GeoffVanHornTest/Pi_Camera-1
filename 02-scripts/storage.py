# storage.py
"""File system operations for the PI Camera system.

Handles generating timestamped filenames for video clips and snapshots,
saving images to disk, and cleaning up old files to prevent the SD card
from filling up. The clips directory is created on import if it does not
already exist.
"""

import os
import time
from datetime import datetime

import config
import cv2
import numpy as np

if os.path.isfile(config.CLIPS_DIR):
    raise RuntimeError(
        f"CLIPS_DIR {config.CLIPS_DIR!r} is a regular file, not a directory. "
        "Remove the file and ensure the directory exists."
    )
os.makedirs(config.CLIPS_DIR, exist_ok=True)


def get_video_path() -> str:
    """Generate a timestamped file path for a new video clip.

    Returns:
        str: Path in the form 00-clips/motion_YYYY-MM-DD_HH-MM-SS.mp4.
    """

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"motion_{timestamp}.mp4"
    return os.path.join(config.CLIPS_DIR, filename)


def get_snapshot_path() -> str:
    """Generate a timestamped file path for a new snapshot image.

    Returns:
        str: Path in the form 00-clips/snapshot_YYYY-MM-DD_HH-MM-SS.jpg.
    """
    # Almost identical to get_video_path() — the only differences are the
    # prefix (snapshot_ instead of motion_) and the extension
    # (.jpg instead of .mp4).

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"snapshot_{timestamp}.jpg"
    return os.path.join(config.CLIPS_DIR, filename)


def save_snapshot(frame: np.ndarray) -> str:
    """Save a single frame to disk as a JPEG image.

    Args:
        frame: A BGR numpy.ndarray from camera.get_frame().

    Returns:
        str: The path where the snapshot was saved.
    """
    path = get_snapshot_path()
    ok = cv2.imwrite(path, frame)
    if not ok:
        raise RuntimeError(f"cv2.imwrite failed — could not write snapshot to {path}")
    return path


_H264_ORPHAN_AGE_SEC = 300  # 5 min — long enough to never touch an in-flight conversion


def _validate_clips_dir() -> None:
    """Raise RuntimeError if CLIPS_DIR has been replaced or removed since startup.

    config.CLIPS_DIR is validated as a real (non-symlink) directory at load time,
    but the filesystem can change while the service is running. A symlink created
    at that path after startup would redirect cleanup's os.remove() calls to the
    symlink target. Re-checking before each destructive operation closes the
    post-load TOCTOU window (#147).
    """
    path = config.CLIPS_DIR
    if not os.path.isdir(path):
        raise RuntimeError(f"CLIPS_DIR {path!r} no longer exists — skipping")
    if os.path.realpath(path) != path:
        raise RuntimeError(
            f"CLIPS_DIR {path!r} has been replaced by a symlink since startup — skipping"
        )


def cleanup_old_clips(days: int = 7) -> None:
    """Delete clips and snapshots older than the given number of days.

    Only scans the top level of CLIPS_DIR — manually archived subdirectories
    (e.g. daytime-2026-07-14/) are skipped and are the operator's responsibility
    to manage. Orphaned .h264 files (evidence of a failed ffmpeg conversion) are
    removed only when older than _H264_ORPHAN_AGE_SEC so that an in-flight
    conversion is never unlinked mid-write (#66).

    Args:
        days: Files older than this many days are removed. Defaults to 7.
    """
    _validate_clips_dir()
    # Re-check for symlink immediately before listdir() to catch any race between
    # _validate_clips_dir() returning and os.listdir() executing. An attacker with
    # local write access could rename() a pre-staged symlink into place in that window.
    if os.path.islink(config.CLIPS_DIR):
        raise RuntimeError(
            f"CLIPS_DIR {config.CLIPS_DIR!r} was replaced by a symlink — aborting cleanup"
        )
    now = time.time()
    cutoff = now - (days * 86400)
    for filename in os.listdir(config.CLIPS_DIR):
        path = os.path.join(config.CLIPS_DIR, filename)
        if not os.path.isfile(path):
            continue
        try:
            if filename.endswith(".h264"):
                if now - os.path.getmtime(path) > _H264_ORPHAN_AGE_SEC:
                    os.remove(path)
            elif filename.endswith((".mp4", ".jpg")) and os.path.getmtime(path) < cutoff:
                os.remove(path)
            # Files with other extensions (notes, lock files, operator-staged files)
            # are left untouched — only storage.py's own output types are managed.
        except (FileNotFoundError, PermissionError):
            pass  # race with another thread, or read-only filesystem after power loss
