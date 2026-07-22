# API Reference

Auto-generated from docstrings in `02-scripts/`.

## config

::: config

## camera

`camera.py` acquires the Picamera2 hardware, H264 encoder, and CircularOutput at module import time, so mkdocstrings cannot auto-import it on non-Pi machines. Public API is documented here manually.

| Function | Description |
|---|---|
| `get_frame()` | Capture a single BGR frame from the live feed. Returns `numpy.ndarray`. |
| `start_recording(filepath)` | Tap the ring buffer into a `.h264` file. Pre-roll is flushed first. |
| `split_recording(new_filepath, on_complete=None)` | Switch to a new clip file without clearing the ring buffer. Old clip is converted to MP4 in a background thread; `on_complete(mp4_path)` is called on success. |
| `stop_recording(on_complete=None)` | Stop writing, convert to MP4 in background. `on_complete(mp4_path)` called on success. |
| `close()` | Shut down the encoder and release the hardware. |

## motion_detector

::: motion_detector

## storage

::: storage

## telegram_notifier

::: telegram_notifier

## dropbox_uploader

::: dropbox_uploader

## event_log

::: event_log

## main

::: main