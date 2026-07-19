# camera.py

import os
import subprocess
import threading
import time

import config
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import CircularOutput

_camera = Picamera2()
_camera.configure(
    _camera.create_video_configuration(
        main={"size": config.RESOLUTION, "format": "BGR888"},
        controls={"FrameRate": config.FPS},
    )
)
_camera.start()

# The encoder and circular buffer run continuously from startup.
# CircularOutput keeps the last PRE_ROLL_SEC of compressed video in memory
# so that every clip automatically includes footage from before the trigger.
# buffersize is in frames (not bytes), so PRE_ROLL_SEC * FPS gives the right count.
_encoder = H264Encoder(bitrate=config.VIDEO_BITRATE_BPS)
_circular = CircularOutput(buffersize=int(config.PRE_ROLL_SEC * config.FPS))
_camera.start_recording(_encoder, _circular)

# Writing the H264 stream to a named file rather than an ffmpeg pipe because
# CircularOutput dumps the ring buffer starting at whatever NAL unit was
# oldest in the buffer — there is no guarantee an SPS/PPS header is first.
# ffmpeg can probe a file to find SPS/PPS anywhere in the stream; it cannot
# do that on a pipe, causing silent corruption or an immediate ffmpeg exit
# that breaks the pipe and kills picamera2's internal output thread.
_h264_file = None
_recording_started = None


def get_frame():
    """Capture a single frame from the live camera feed.

    Returns:
        numpy.ndarray: A (height, width, 3) array in BGR format,
        ready for OpenCV processing.
    """
    return _camera.capture_array()


def start_recording(filepath):
    """Tap the ring buffer into a file and start saving footage.

    Writes to a temporary .h264 file; stop_recording() converts it to MP4.
    The last config.PRE_ROLL_SEC seconds already in the buffer are flushed
    to the file first, so the clip starts before the trigger point.

    Args:
        filepath: Full path to the output .mp4 file.
    """
    global _h264_file, _recording_started
    _recording_started = time.time()
    h264_path = filepath.replace(".mp4", ".h264")
    _h264_file = open(h264_path, "wb")
    _circular.fileoutput = _h264_file
    _circular.start()


def _log_clip_quality(mp4_path, expected_sec):
    """Log actual vs expected clip duration to surface frame-drop issues (#53)."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", mp4_path],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0:
            return
        actual_sec = float(r.stdout.strip())
        drop_pct = 100.0 * (1.0 - actual_sec / expected_sec)
        label = "drop" if drop_pct > 0 else "gain"
        print(
            f"[camera] clip duration: {actual_sec:.1f}s / {expected_sec:.1f}s expected"
            f" ({drop_pct:+.1f}% {label})"
        )
    except (subprocess.TimeoutExpired, ValueError, ZeroDivisionError):
        pass


def _convert_to_mp4(h264_path, on_complete=None, expected_sec=None):
    mp4_path = h264_path.replace(".h264", ".mp4")
    try:
        # nice -n 10 keeps ffmpeg from competing with the H264 encoder and
        # MOG2 detection threads during recording overlap (#53).
        result = subprocess.run(
            ["nice", "-n", "10", "ffmpeg", "-y", "-f", "h264", "-framerate", str(config.FPS),
             "-i", h264_path, "-c:v", "copy", mp4_path],
            timeout=30,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode == 0:
            os.remove(h264_path)
            if expected_sec is not None:
                _log_clip_quality(mp4_path, expected_sec)
            if on_complete:
                on_complete(mp4_path)
        else:
            print(f"WARNING: ffmpeg failed (rc={result.returncode}) — keeping {h264_path}")
    except subprocess.TimeoutExpired:
        print(f"WARNING: ffmpeg timed out — keeping {h264_path}")


def split_recording(new_filepath, on_complete=None):
    """Switch to a new clip file without clearing the ring buffer.

    Reassigns fileoutput directly so the deque survives the transition.
    The new clip starts with pre-roll from the existing buffer. The old
    clip is converted to MP4 in a background thread.
    """
    global _h264_file, _recording_started

    old_h264_file = _h264_file
    old_h264_path = old_h264_file.name if old_h264_file else None
    elapsed = time.time() - _recording_started if _recording_started else None
    _recording_started = time.time()

    new_h264_path = new_filepath.replace(".mp4", ".h264")
    new_h264_file = open(new_h264_path, "wb")

    # Switching fileoutput resets _firstframe=True and keeps recording=True.
    # The deque is not drained, so the new clip gets pre-roll from the buffer.
    _circular.fileoutput = new_h264_file
    _h264_file = new_h264_file

    if old_h264_file:
        old_h264_file.close()

    if old_h264_path and os.path.exists(old_h264_path):
        threading.Thread(
            target=_convert_to_mp4, args=(old_h264_path, on_complete, elapsed), daemon=True
        ).start()


def stop_recording(on_complete=None):
    """Stop writing to the current clip file and convert to MP4.

    Closes the .h264 file, then remuxes it to .mp4 in a background thread
    so the detection loop is not blocked during conversion. The .h264 is
    deleted on success; kept on failure as a recovery artifact.
    on_complete(mp4_path) is called from the background thread after a
    successful conversion — use it to trigger upload/notification.
    """
    global _h264_file, _recording_started
    _circular.stop()

    elapsed = time.time() - _recording_started if _recording_started else None
    _recording_started = None

    h264_path = None
    if _h264_file is not None:
        h264_path = _h264_file.name
        _h264_file.close()
        _h264_file = None
    _circular.fileoutput = None

    if h264_path and os.path.exists(h264_path):
        threading.Thread(
            target=_convert_to_mp4, args=(h264_path, on_complete, elapsed), daemon=True
        ).start()


def close():
    """Shut down the camera and release the hardware."""
    _camera.stop_recording()
    _camera.stop()
    _camera.close()
