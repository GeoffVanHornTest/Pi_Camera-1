# camera.py

import config
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import CircularOutput, FfmpegOutput

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
# Buffer size = PRE_ROLL_SEC * H264Encoder default bitrate (~10 Mbps).
_encoder = H264Encoder()
_circular = CircularOutput(buffersize=int(config.PRE_ROLL_SEC * 10_000_000 / 8))
_camera.start_recording(_encoder, _circular)


def get_frame():
    """Capture a single frame from the live camera feed.

    Returns:
        numpy.ndarray: A (height, width, 3) array in BGR format,
        ready for OpenCV processing.
    """
    return _camera.capture_array()


def start_recording(filepath):
    """Tap the ring buffer into a file and start saving footage.

    The last config.PRE_ROLL_SEC seconds already in the buffer are flushed
    to the file first, so the clip starts before the trigger point.

    Args:
        filepath: Full path to the output .mp4 file.
    """
    _circular.fileoutput = FfmpegOutput(filepath)
    _circular.start()


def stop_recording():
    """Stop writing to the current clip file.

    The circular buffer continues capturing — the next start_recording()
    call will again include PRE_ROLL_SEC seconds of pre-motion footage.
    No camera restart needed between clips.
    """
    _circular.stop()
    _circular.fileoutput = None


def close():
    """Shut down the camera and release the hardware."""
    _camera.stop_recording()
    _camera.stop()
    _camera.close()