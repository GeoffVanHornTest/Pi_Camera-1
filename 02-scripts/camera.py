# camera.py

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
# Bitrate must be set explicitly so the buffer size calculation is correct;
# leaving H264Encoder() with no argument uses picamera2's ~1 Mbps default,
# which would make the buffer hold ~5× more data than intended.
_encoder = H264Encoder(bitrate=config.VIDEO_BITRATE_BPS)
_circular = CircularOutput(buffersize=int(config.PRE_ROLL_SEC * config.VIDEO_BITRATE_BPS / 8))
_camera.start_recording(_encoder, _circular)

# CircularOutput.fileoutput requires io.BufferedIOBase, not FfmpegOutput.
# We pipe the raw H264 stream into an ffmpeg subprocess for MP4 muxing.
_proc = None


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
    global _proc
    _proc = subprocess.Popen(
        [
            "ffmpeg", "-y",
            "-f", "h264",
            "-framerate", str(config.FPS),
            "-i", "pipe:0",
            "-c:v", "copy",
            filepath,
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # proc.stdin is io.BufferedWriter (subclass of io.BufferedIOBase) — satisfies picamera2
    _circular.fileoutput = _proc.stdin
    _circular.start()


def stop_recording():
    """Stop writing to the current clip file.

    The circular buffer continues capturing — the next start_recording()
    call will again include PRE_ROLL_SEC seconds of pre-motion footage.
    No camera restart needed between clips.
    """
    global _proc
    _circular.stop()
    if _proc is not None:
        _proc.stdin.close()  # send EOF so ffmpeg finalises the MP4 container
        try:
            _proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            print("WARNING: ffmpeg did not exit in 15s — killing process")
            _proc.kill()
            _proc.wait()
        _proc = None
    _circular.fileoutput = None


def close():
    """Shut down the camera and release the hardware."""
    _camera.stop_recording()
    _camera.stop()
    _camera.close()