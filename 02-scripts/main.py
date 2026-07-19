# main.py

"""Entry point for the PI Camera motion detection system.

Initialises all modules and runs the main loop. Press Ctrl+C to stop.
"""

import signal
import sys
import threading
import time

import camera
import config
import dropbox_uploader
import motion_detector
import storage
import telegram_notifier

# --- Watchdog (issue #23) ---
# The main loop timing checks only run when get_frame() returns. If the camera
# stalls, MAX_RECORD_SEC can be breached by an entire frame period. The watchdog
# is a daemon Timer that sets _split_event after MAX_RECORD_SEC regardless of
# what get_frame() is doing. The main loop checks the event on every iteration.
_watchdog = None
_split_event = threading.Event()


def _arm_watchdog():
    """Start (or restart) the MAX_RECORD_SEC timer for the current clip."""
    global _watchdog
    _split_event.clear()
    if _watchdog:
        _watchdog.cancel()
    _watchdog = threading.Timer(config.MAX_RECORD_SEC, _split_event.set)
    _watchdog.daemon = True
    _watchdog.start()


def _cancel_watchdog():
    """Cancel the watchdog and clear the split event."""
    global _watchdog
    if _watchdog:
        _watchdog.cancel()
        _watchdog = None
    _split_event.clear()


def _validate_config():
    """Check required .env credentials are present before the main loop starts."""
    missing = [
        name
        for name, value in {
            "TELEGRAM_BOT_TOKEN": config.TELEGRAM_BOT_TOKEN,
            "TELEGRAM_CHAT_ID": config.TELEGRAM_CHAT_ID,
            "DROPBOX_APP_KEY": config.DROPBOX_APP_KEY,
            "DROPBOX_APP_SECRET": config.DROPBOX_APP_SECRET,
            "DROPBOX_REFRESH_TOKEN": config.DROPBOX_REFRESH_TOKEN,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(
            f"Missing required config: {', '.join(missing)}\n"
            "Add TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, DROPBOX_APP_KEY, "
            "DROPBOX_APP_SECRET, DROPBOX_REFRESH_TOKEN to .env"
        )


def _finish_clip(filepath):
    """Stop recording, reset filter state, and upload the clip once conversion completes."""
    motion_detector.reset_motion_state()
    _cancel_watchdog()
    print("Recording stopped — uploading clip in background...")

    def _upload_and_notify(path):
        url = dropbox_uploader.upload(path)
        if url:
            telegram_notifier.send_message(f"Clip ready: {url}")
            print(f"Clip uploaded: {url}")
        else:
            telegram_notifier.send_message("Clip recorded but Dropbox upload failed.")

    camera.stop_recording(on_complete=_upload_and_notify)


def main():
    """Run the camera loop — detect motion, record clips, and send alerts."""

    _validate_config()

    currently_recording = False
    filepath = None
    last_cleanup = 0
    motion_last_seen = 0.0

    print("PI Camera started. Press Ctrl+C to stop.")

    while True:
        if time.time() - last_cleanup > 86400:
            storage.cleanup_old_clips(days=7)
            last_cleanup = time.time()

        frame = camera.get_frame()
        motion, _ = motion_detector.detect(frame)
        now = time.time()

        if motion:
            motion_last_seen = now

        if motion and not currently_recording and motion_detector.new_event_allowed():
            filepath = storage.get_video_path()
            camera.start_recording(filepath)
            _arm_watchdog()
            snapshot = storage.save_snapshot(frame)
            threading.Thread(
                target=telegram_notifier.send_photo,
                args=(snapshot,),
                kwargs={"caption": "Motion detected!"},
                daemon=True,
            ).start()
            currently_recording = True
            motion_last_seen = now
            print(f"Motion detected — recording to {filepath}")

        if currently_recording:
            time_since_motion = now - motion_last_seen

            if _split_event.is_set():
                # Watchdog fired — MAX_RECORD_SEC elapsed on a background timer
                # so this fires even if get_frame() was slow (#23).
                print("Watchdog: MAX_RECORD_SEC reached — splitting clip.")
                filepath = storage.get_video_path()

                def _upload_and_notify_split(path):
                    url = dropbox_uploader.upload(path)
                    if url:
                        telegram_notifier.send_message(f"Clip ready: {url}")
                        print(f"Clip uploaded: {url}")
                    else:
                        telegram_notifier.send_message("Clip recorded but Dropbox upload failed.")

                camera.split_recording(filepath, on_complete=_upload_and_notify_split)
                motion_detector.reset_motion_state()
                motion_last_seen = now
                _arm_watchdog()

            elif time_since_motion >= config.POST_MOTION_BUFFER_SEC:
                clip_to_upload = filepath
                filepath = None
                currently_recording = False
                _finish_clip(clip_to_upload)


def _shutdown():
    """Shared cleanup path for SIGTERM and KeyboardInterrupt."""
    print("\nStopping PI Camera...")
    _cancel_watchdog()
    camera.close()
    print("Camera released. Goodbye.")
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: _shutdown())
    try:
        main()
    except KeyboardInterrupt:
        _shutdown()
