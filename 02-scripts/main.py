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
    """Stop recording, upload the clip, and send the Telegram link."""
    camera.stop_recording()
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
    motion_last_seen = 0.0  # timestamp of the most recent frame with detected motion
    recording_started = 0.0  # timestamp when the current clip began

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
            # start a new clip: motion present, not already recording, cooldown elapsed
            filepath = storage.get_video_path()
            camera.start_recording(filepath)
            snapshot = storage.save_snapshot(frame)
            telegram_notifier.send_photo(snapshot, caption="Motion detected!")
            currently_recording = True
            recording_started = now
            motion_last_seen = now
            print(f"Motion detected — recording to {filepath}")

        if currently_recording:
            time_recording = now - recording_started
            time_since_motion = now - motion_last_seen

            if time_recording >= config.MAX_RECORD_SEC:
                # hard cap reached — close this clip and immediately start a new one
                print("Max clip duration reached — splitting clip.")
                clip_to_upload = filepath
                _finish_clip(clip_to_upload)
                filepath = storage.get_video_path()
                camera.start_recording(filepath)
                recording_started = now
                motion_last_seen = now

            elif (time_recording >= config.MIN_RECORD_SEC
                  and time_since_motion >= config.POST_MOTION_BUFFER_SEC):
                # minimum duration met and motion has been absent long enough — stop
                clip_to_upload = filepath
                filepath = None
                currently_recording = False
                _finish_clip(clip_to_upload)


if __name__ == "__main__":
    # only run when this file is executed directly (not when imported by another module)
    try:
        main()
    except KeyboardInterrupt:
        # user pressed Ctrl+C — shut down cleanly instead of dying mid-frame
        print("\nStopping PI Camera...")
        camera.close()
        # release the camera hardware so it's not left in a locked state
        print("Camera released. Goodbye.")
