"""verify_shutdown.py — Hardware integration test for the shutdown mid-clip fix (#80).

Verifies that calling _finish_clip() (as _shutdown() now does when a clip is in
progress) produces a valid, playable MP4 — i.e. the .h264 file is cleanly closed
and the ffmpeg conversion completes successfully.

No motion event is required. The script starts recording directly, waits a few
seconds for footage to accumulate, triggers the shutdown path, then checks the
output file.

Usage:
    uv run python verify_shutdown.py [record_sec]

    record_sec: how long to record before triggering shutdown (default: 5)
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import camera
import config
import main
import storage

POLL_INTERVAL = 0.5
CONVERSION_TIMEOUT = 30


def wait_for_mp4(mp4_path, timeout=CONVERSION_TIMEOUT):
    """Poll until the .mp4 exists and is non-zero, or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(mp4_path) and os.path.getsize(mp4_path) > 0:
            return True
        time.sleep(POLL_INTERVAL)
    return False


def check_mp4_playable(mp4_path):
    """Return (duration_sec, error_str). duration is None on failure."""
    try:
        import subprocess
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", mp4_path],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0:
            return None, f"ffprobe returned rc={r.returncode}"
        duration = float(r.stdout.strip())
        return duration, None
    except subprocess.TimeoutExpired:
        return None, "ffprobe timed out"
    except ValueError:
        return None, f"ffprobe output not a number: {r.stdout.strip()!r}"


def main_verify():
    record_sec = int(sys.argv[1]) if len(sys.argv) > 1 else 5

    print("verify_shutdown.py — testing _finish_clip() on an active recording")
    print(f"  record_sec={record_sec}  clips_dir={config.CLIPS_DIR}")
    print()

    # Step 1: start recording directly (no motion event)
    mp4_path = storage.get_video_path()
    print(f"[1] Starting recording → {mp4_path}")
    camera.start_recording(mp4_path)
    main._currently_recording = True

    # Step 2: let footage accumulate
    print(f"[2] Recording for {record_sec}s...")
    time.sleep(record_sec)

    # Step 3: trigger the shutdown path
    print("[3] Calling _finish_clip() (as _shutdown() would)...")
    main._finish_clip()
    main._currently_recording = False

    # Step 4: wait for ffmpeg conversion
    print(f"[4] Waiting up to {CONVERSION_TIMEOUT}s for MP4 conversion...")
    appeared = wait_for_mp4(mp4_path)

    print()
    print("=" * 60)
    if not appeared:
        print(f"  FAIL  MP4 did not appear within {CONVERSION_TIMEOUT}s")
        print(f"        Check for a leftover .h264 in {config.CLIPS_DIR}")
        print("=" * 60)
        sys.exit(1)

    size_kb = os.path.getsize(mp4_path) / 1024
    duration, err = check_mp4_playable(mp4_path)

    if err:
        print(f"  FAIL  MP4 exists ({size_kb:.0f} KB) but ffprobe failed: {err}")
        print("=" * 60)
        sys.exit(1)

    # Expect at least record_sec worth of content (pre-roll adds more on top)
    if duration < record_sec * 0.8:
        print(
            f"  WARN  MP4 duration {duration:.1f}s is shorter than expected "
            f"(recorded {record_sec}s — possible frame loss)"
        )
    else:
        print(f"  PASS  MP4 is valid: {duration:.1f}s duration, {size_kb:.0f} KB")
        print(f"        (includes ~{duration - record_sec:.1f}s pre-roll from ring buffer)")

    print(f"  File: {mp4_path}")
    print("=" * 60)


if __name__ == "__main__":
    main_verify()