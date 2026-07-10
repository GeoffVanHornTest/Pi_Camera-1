# main.py


"""Entry point for the PI Camera motion detection system.

Initialises all modules and runs the main loop. Press Ctrl+C to stop.
"""

import time

import camera
import config
import motion_detector
import notifier
import storage


def main():
    """Run the camera loop — detect motion, record clips, and send alerts."""

    currently_recording = False
    # tracks whether a video clip is actively being recorded

    print("PI Camera started. Press Ctrl+C to stop.")

    while True:
        # runs forever until the user hits Ctrl+C — the camera is always watching

        frame = camera.get_frame()
        # grab the latest frame from the live feed — this is a NumPy array in BGR format

        motion, _ = motion_detector.detect(frame)
        # analyse the frame for motion — returns (bool, frame). We discard the frame with _
        # because we already have it, and we don't need the annotated version in main

        if motion and not currently_recording:
            # only start a new clip if motion was detected AND we're not already recording
            # the second condition prevents stacking recordings on top of each other
            filepath = storage.get_video_path()
            camera.start_recording(filepath)
            snapshot = storage.save_snapshot(frame)
            notifier.send_alert(snapshot)
            currently_recording = True
            print(f"Motion detected — recording to {filepath}")

        if not motion and currently_recording:
            time.sleep(config.POST_MOTION_BUFFER_SEC)
            # keep recording for a few seconds after motion stops — without this the clip
            # would cut off the moment the subject leaves frame
            camera.stop_recording()
            currently_recording = False
            print("Motion stopped — recording saved.")

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
