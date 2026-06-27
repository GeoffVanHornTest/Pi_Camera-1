# main.py
# Entry point for the Pi Night Vision Motion Camera.
# Wires together all modules (config, camera, motion_detector, notifier, storage)
# to run the main capture-detect-record-notify loop.

import time
import logging
import config
import camera
import motion_detector
import notifier
import storage

# Set up clean, professional console logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)

def main():
    logging.info("Starting Pi Night Vision Motion Camera...")
    
    currently_recording = False
    recording_stop_time = None

    try:
        logging.info("Camera and detector initialized. Entering main loop...")
        
        while True:
            # Capture a single frame from the camera BGR888 feed
            frame = camera.get_frame()
            
            # Run motion detection on the captured frame
            motion, annotated_frame = motion_detector.detect(frame)
            
            now = time.time()
            
            if motion:
                if not currently_recording:
                    logging.info("Motion detected! Starting recording and sending alert.")
                    
                    # Generate a timestamped video file path and start recording
                    filepath = storage.get_video_path()
                    camera.start_recording(filepath)
                    currently_recording = True
                    
                    # Save a snapshot frame and send a Gmail notification asynchronously
                    try:
                        snapshot_path = storage.save_snapshot(frame)
                        logging.info(f"Snapshot saved to {snapshot_path}")
                        
                        # notifier.send_alert handles its own email rate limiting
                        notifier.send_alert(snapshot_path)
                    except Exception as e:
                        logging.error(f"Error handling snapshot or email alert: {e}")
                else:
                    logging.info("Motion detected while already recording. Extending recording time.")
                
                # Extend the recording window.
                # We record for MOTION_COOLDOWN_SEC to monitor for subsequent motion,
                # plus POST_MOTION_BUFFER_SEC after motion stops.
                recording_stop_time = now + config.MOTION_COOLDOWN_SEC + config.POST_MOTION_BUFFER_SEC

            # Check if recording is active and the recording window has expired
            if currently_recording and recording_stop_time is not None:
                if now >= recording_stop_time:
                    logging.info("No motion detected recently. Stopping recording.")
                    camera.stop_recording()
                    currently_recording = False
                    recording_stop_time = None
            
            # Brief sleep to be polite to the CPU.
            # Note: camera.get_frame() is naturally rate-limited by the camera's 30 FPS,
            # but a small sleep ensures we do not busy-wait in case of any driver delays.
            time.sleep(0.01)

    except KeyboardInterrupt:
        logging.info("Interrupt received (Ctrl+C). Shutting down...")
    except Exception as e:
        logging.error(f"Unexpected error in main loop: {e}")
    finally:
        # Graceful cleanup: stop any active recording and release the camera hardware
        if currently_recording:
            try:
                camera.stop_recording()
                logging.info("Active recording stopped.")
            except Exception as e:
                logging.error(f"Error stopping recording during cleanup: {e}")
        
        try:
            camera.close()
            logging.info("Camera resources released.")
        except Exception as e:
            logging.error(f"Error closing camera: {e}")
            
        logging.info("System shutdown complete.")

if __name__ == "__main__":
    main()
