# camera.py

import os
import subprocess

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
    global _h264_file
    h264_path = filepath.replace(".mp4", ".h264")
    _h264_file = open(h264_path, "wb")
    _circular.fileoutput = _h264_file
    _circular.start()


def stop_recording():
    """Stop writing to the current clip file and convert to MP4.

    Closes the .h264 file, remuxes it to .mp4 with ffmpeg (-c:v copy so no
    re-encode), then deletes the .h264 source. The circular buffer continues
    capturing — the next start_recording() call will again include
    PRE_ROLL_SEC seconds of pre-motion footage.
    """
    global _h264_file
    _circular.stop()

    h264_path = None
    if _h264_file is not None:
        h264_path = _h264_file.name
        _h264_file.close()
        _h264_file = None
    _circular.fileoutput = None

    if h264_path and os.path.exists(h264_path):
        mp4_path = h264_path.replace(".h264", ".mp4")
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "h264",
                    "-framerate",
                    str(config.FPS),
                    "-i",
                    h264_path,
                    "-c:v",
                    "copy",
                    mp4_path,
                ],
                timeout=30,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired:
            print("WARNING: ffmpeg conversion timed out after 30s")
        finally:
            try:
                os.remove(h264_path)
            except FileNotFoundError:
                pass


def close():
    """Shut down the camera and release the hardware."""
    _camera.stop_recording()
    _camera.stop()
    _camera.close()
