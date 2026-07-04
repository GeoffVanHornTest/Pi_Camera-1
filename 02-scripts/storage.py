# storage.py
# Handles all file system operations — generating timestamped filenames
# for video clips and snapshots, saving images to disk, and ensuring the
# clips folder exists before anything tries to write to it.

import os       # built-in: used to build file paths and create directories
import cv2      # OpenCV: used to encode and write image frames to disk as JPEG
from datetime import datetime  # built-in: used to generate timestamps for filenames
import config   # our settings file — provides CLIPS_DIR so the path isn't hardcoded here


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
    #sets the name of the recording file
    
    return os.path.join(config.CLIPS_DIR, filename)

def get_snapshot_path():
    """Generate a timestamped file path for a new snapshot image.

    Returns:
        str: Path in the form clips/snapshot_YYYY-MM-DD_HH-MM-SS.jpg.
    """
    #Almost identical to get_video_path() — the only differences are the 
    # prefix (snapshot_ instead of motion_) and the extension 
    # (.jpg instead of .mp4).

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"snapshot_{timestamp}.jpg"
    return os.path.join(config.CLIPS_DIR, filename)

def save_snapshot(frame): #frame is a NumPy array
    """Save a single frame to disk as a JPEG image.

    Args:
        frame: A BGR numpy.ndarray from camera.get_frame().

    Returns:
        str: The path where the snapshot was saved.
    """

    path = get_snapshot_path()
    cv2.imwrite(path, frame)
    #cv2.imwrite() encodes that array as a JPEG and writes it to 
    # disk at the given path
    return path
