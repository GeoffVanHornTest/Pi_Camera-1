# main.py

"""Entry point for the PI Camera motion detection system.

Initialises all modules and runs the main loop. Press Ctrl+C to stop.
"""

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
    """Stop recording, reset filter state, and upload the clip in the background."""
    camera.stop_recording()
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

    threading.Thread(target=_upload_and_notify, args=(filepath,), daemon=True).start()


def main():
    """Run the camera loop — detect motion, record clips, and send alerts."""

    _validate_config()

    currently_recording = False
    filepath = None
    last_cleanup = 0
    motion_last_seen = 0.0
    recording_started = 0.0

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
            snapshot = storage.save_snapshot(frame)
            telegram_notifier.send_photo(snapshot, caption="Motion detected!")
            currently_recording = True
            recording_started = now
            motion_last_seen = now
            _arm_watchdog()
            print(f"Motion detected — recording to {filepath}")

        if currently_recording:
            time_recording = now - recording_started
            time_since_motion = now - motion_last_seen

            if _split_event.is_set():
                # Watchdog fired — MAX_RECORD_SEC elapsed on a background timer
                # so this fires even if get_frame() was slow (#23).
                print("Watchdog: MAX_RECORD_SEC reached — splitting clip.")
                clip_to_upload = filepath
                _finish_clip(clip_to_upload)
                filepath = storage.get_video_path()
                camera.start_recording(filepath)
                recording_started = now
                motion_last_seen = now
                currently_recording = True
                _arm_watchdog()

            elif (
                time_recording >= config.MIN_RECORD_SEC
                and time_since_motion >= config.POST_MOTION_BUFFER_SEC
            ):
                clip_to_upload = filepath
                filepath = None
                currently_recording = False
                _finish_clip(clip_to_upload)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopping PI Camera...")
        _cancel_watchdog()
        camera.close()
        print("Camera released. Goodbye.")