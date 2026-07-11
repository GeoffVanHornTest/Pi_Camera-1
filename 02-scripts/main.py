# main.py


"""Entry point for the PI Camera motion detection system.

Initialises all modules and runs the main loop. Press Ctrl+C to stop.
"""

import os
import time

import camera
import config
import drive_uploader
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
            "DRIVE_FOLDER_ID": config.DRIVE_FOLDER_ID,
        }.items()
        if not value
    ]
    if not os.path.exists(config.DRIVE_SERVICE_ACCOUNT_JSON):
        missing.append("service_account.json (not found at expected path)")
    if missing:
        raise RuntimeError(
            f"Missing required config: {', '.join(missing)}\n"
            "Add TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, DRIVE_FOLDER_ID to 02-scripts/.env\n"
            "and place service_account.json in 02-scripts/."
        )


def main():
    """Run the camera loop — detect motion, record clips, and send alerts."""

    _validate_config()
    # fail fast if .env credentials are missing — better than crashing on first motion event

    currently_recording = False
    # tracks whether a video clip is actively being recorded

    filepath = None
    # path of the current clip — held here so the stop block can upload it

    last_cleanup = 0
    # timestamp of the last disk cleanup — starts at 0 so cleanup runs on first boot

    print("PI Camera started. Press Ctrl+C to stop.")

    while True:
        if time.time() - last_cleanup > 86400:
            # run cleanup once every 24 hours to prevent the clips folder filling the disk
            storage.cleanup_old_clips(days=7)
            last_cleanup = time.time()

        frame = camera.get_frame()
        motion, _ = motion_detector.detect(frame)

        if motion and not currently_recording and motion_detector.new_event_allowed():
            # start a new clip only when: motion is present, not already recording,
            # and enough time has passed since the last event (cooldown gate).
            filepath = storage.get_video_path()
            camera.start_recording(filepath)
            snapshot = storage.save_snapshot(frame)
            telegram_notifier.send_photo(snapshot, caption="Motion detected!")
            currently_recording = True
            print(f"Motion detected — recording to {filepath}")

        if not motion and currently_recording:
            time.sleep(config.POST_MOTION_BUFFER_SEC)
            # keep recording for a few seconds after motion stops
            camera.stop_recording()
            currently_recording = False
            print("Motion stopped — uploading clip...")
            url = drive_uploader.upload(filepath)
            if url:
                telegram_notifier.send_message(f"Clip ready: {url}")
                print(f"Clip uploaded: {url}")
            else:
                telegram_notifier.send_message("Clip recorded but Drive upload failed.")
            filepath = None


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
