# storage.py
# Handles all file system operations — generating timestamped filenames
# for video clips and snapshots, saving images to disk, and ensuring the
# clips folder exists before anything tries to write to it.

import os
import time
from datetime import datetime

import config
import cv2

os.makedirs(config.CLIPS_DIR, exist_ok=True)
# os.makedirs() creates the clips folder if it doesn't already exist.
# exist_ok=True prevents a crash if the folder is already there — it simply moves on.
# This runs once when the module is first imported, so the folder is always
# guaranteed to exist before any file-saving functions are called.


def get_video_path():
    """Generate a timestamped file path for a new video clip.

    Returns:
        str: Path in the form clips/motion_YYYY-MM-DD_HH-MM-SS.mp4.
    """

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    # gets current date and time and formats the the string ie:2026-06-20_21-30-00

    filename = f"motion_{timestamp}.mp4"
    # sets the name of the recording file

    return os.path.join(config.CLIPS_DIR, filename)


def get_snapshot_path():
    """Generate a timestamped file path for a new snapshot image.

    Returns:
        str: Path in the form clips/snapshot_YYYY-MM-DD_HH-MM-SS.jpg.
    """
    # Almost identical to get_video_path() — the only differences are the
    # prefix (snapshot_ instead of motion_) and the extension
    # (.jpg instead of .mp4).

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"snapshot_{timestamp}.jpg"
    return os.path.join(config.CLIPS_DIR, filename)


def save_snapshot(frame):
    """Save a single frame to disk as a JPEG image.

    Args:
        frame: A BGR numpy.ndarray from camera.get_frame().

    Returns:
        str: The path where the snapshot was saved.
    """
    path = get_snapshot_path()
    cv2.imwrite(path, frame)
    return path


def cleanup_old_clips(days=7):
    """Delete clips and snapshots older than the given number of days.

    Args:
        days: Files older than this many days are removed. Defaults to 7.
    """
    cutoff = time.time() - (days * 86400)
    for filename in os.listdir(config.CLIPS_DIR):
        path = os.path.join(config.CLIPS_DIR, filename)
        if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
            os.remove(path)
