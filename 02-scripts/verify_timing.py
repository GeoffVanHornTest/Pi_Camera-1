"""verify_timing.py — Post-run validation of feature/timing-fixes behavior.

Verifies two hardware-dependent behaviors without needing the camera:

  Test 1 — FfmpegOutput compatibility
      Confirm each clip is a readable, valid MP4 with a plausible frame count.
      If FfmpegOutput doesn't work as CircularOutput.fileoutput, clips will be
      unreadable or have 0 frames.

  Test 2 — CircularOutput pre-roll (buffer survival)
      For each clip:
        - trigger_time  = timestamp parsed from filename (when start_recording() fired)
        - stop_time     = file mtime (when ffmpeg finalised the clip)
        - expected_no_preroll = stop_time - trigger_time
        - actual_duration     = frame_count / fps from cv2
        - preroll_detected    = actual_duration - expected_no_preroll

      If CircularOutput.stop() keeps the buffer alive:
        preroll_detected ≈ PRE_ROLL_SEC  for every clip including post-gap clips

      If CircularOutput.stop() clears the buffer:
        preroll_detected ≈ 0             for clips that follow a previous clip
        (first clip of the session may still show pre-roll)

  Consecutive-clip check
      Explicitly compares pre-roll on the first vs later clips. A drop from
      PRE_ROLL_SEC → 0 on clip 2+ is the signature of a buffer-reset bug.

Usage:
    uv run python verify_timing.py [clips_dir]

    clips_dir defaults to config.CLIPS_DIR.
    Point at an archived folder to verify a specific session:
        uv run python verify_timing.py ../00-clips/evening-2026-07-17
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import cv2

PREROLL_PASS_THRESHOLD = max(1.0, config.PRE_ROLL_SEC - 2)  # allow 2s tolerance


def video_duration(filepath):
    """Return clip duration in seconds, or None if unreadable."""
    cap = cv2.VideoCapture(filepath)
    if not cap.isOpened():
        return None
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    cap.release()
    return (frames / fps) if frames > 0 else None


def parse_trigger_time(filepath):
    """Parse the trigger datetime from a motion_YYYY-MM-DD_HH-MM-SS.mp4 filename."""
    name = os.path.basename(filepath).replace("motion_", "").replace(".mp4", "")
    try:
        return datetime.strptime(name, "%Y-%m-%d_%H-%M-%S")
    except ValueError:
        return None


def verify_clip(filepath):
    r = {
        "clip": os.path.basename(filepath),
        "mp4_valid": False,
        "actual_sec": None,
        "expected_no_preroll_sec": None,
        "preroll_detected_sec": None,
        "preroll_pass": None,
        "note": "",
    }

    # Test 1: can cv2 read the file?
    actual = video_duration(filepath)
    if actual is None:
        r["note"] = "unreadable — possible FfmpegOutput incompatibility"
        return r
    r["mp4_valid"] = True
    r["actual_sec"] = round(actual, 1)

    # Test 2: pre-roll check
    trigger = parse_trigger_time(filepath)
    if trigger is None:
        r["note"] = "filename format not recognised — skipping pre-roll check"
        return r

    mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
    expected = (mtime - trigger).total_seconds()

    if expected <= 0:
        r["note"] = "mtime <= trigger time — clock skew? skipping pre-roll check"
        return r

    r["expected_no_preroll_sec"] = round(expected, 1)
    preroll = actual - expected
    r["preroll_detected_sec"] = round(preroll, 1)

    if preroll < 0:
        r["preroll_pass"] = False
        r["note"] = "actual shorter than expected — recording may have stopped early"
    elif preroll >= PREROLL_PASS_THRESHOLD:
        r["preroll_pass"] = True
    else:
        r["preroll_pass"] = False
        r["note"] = f"only {preroll:.1f}s pre-roll, expected ≥{PREROLL_PASS_THRESHOLD:.0f}s"

    return r


def main():
    clips_dir = sys.argv[1] if len(sys.argv) > 1 else config.CLIPS_DIR

    clips = sorted(
        os.path.join(clips_dir, f)
        for f in os.listdir(clips_dir)
        if f.startswith("motion_") and f.endswith(".mp4")
    )

    if not clips:
        print(f"No motion_*.mp4 files found in {clips_dir}")
        sys.exit(1)

    print(f"verify_timing.py — {len(clips)} clip(s) in {clips_dir}")
    print(
        f"PRE_ROLL_SEC={config.PRE_ROLL_SEC}s  "
        f"MIN_RECORD_SEC={config.MIN_RECORD_SEC}s  "
        f"pass threshold≥{PREROLL_PASS_THRESHOLD:.0f}s"
    )
    print()

    results = [verify_clip(c) for c in clips]

    for r in results:
        t1 = "✓" if r["mp4_valid"] else "✗"
        if r["preroll_pass"] is True:
            t2 = f"✓ {r['preroll_detected_sec']}s"
        elif r["preroll_pass"] is False:
            t2 = f"✗ {r['preroll_detected_sec']}s"
        else:
            t2 = "— (skipped)"

        actual_str = f"{r['actual_sec']}s" if r["actual_sec"] is not None else "unreadable"
        expected_str = (
            f"{r['expected_no_preroll_sec']}s"
            if r["expected_no_preroll_sec"] is not None
            else "n/a"
        )
        note = f"  [{r['note']}]" if r["note"] else ""
        print(
            f"  {t1} {r['clip']}"
            f"  actual={actual_str}"
            f"  no-preroll-expected={expected_str}"
            f"  preroll={t2}{note}"
        )

    # Consecutive-clip check: does pre-roll hold after the first clip?
    preroll_results = [r for r in results if r["preroll_pass"] is not None]
    if len(preroll_results) >= 2:
        first_ok = preroll_results[0]["preroll_pass"]
        later_ok = all(r["preroll_pass"] for r in preroll_results[1:])
        print()
        if first_ok and not later_ok:
            print(
                "  ⚠ Consecutive-clip check FAILED: first clip has pre-roll, later clips do not.\n"
                "    CircularOutput.stop() is likely clearing the buffer.\n"
                "    Fix: swap fileoutput between clips without calling stop()/start()."
            )
        elif first_ok and later_ok:
            print("  ✓ Consecutive-clip check PASSED: pre-roll maintained across all clips.")
        elif not first_ok:
            print(
                "  ✗ Pre-roll absent on first clip — buffer may not be filling before trigger,\n"
                "    or FfmpegOutput flush from CircularOutput is not working."
            )

    # Summary
    print()
    valid = [r for r in results if r["mp4_valid"]]
    passed_preroll = [r for r in preroll_results if r["preroll_pass"]]
    avg_preroll = (
        sum(r["preroll_detected_sec"] for r in preroll_results) / len(preroll_results)
        if preroll_results
        else None
    )

    print("=" * 65)
    print(f"Test 1  FfmpegOutput (MP4 validity):  {len(valid)}/{len(results)} readable")
    if preroll_results:
        print(
            f"Test 2  CircularOutput pre-roll:       "
            f"{len(passed_preroll)}/{len(preroll_results)} ≥ {PREROLL_PASS_THRESHOLD:.0f}s"
            f"  (avg {avg_preroll:.1f}s)"
        )
        if avg_preroll is not None and avg_preroll < 0:
            expected_with_preroll = config.PRE_ROLL_SEC + avg_preroll
            print(
                f"\n  Note: negative avg is the expected baseline when pre-roll is inactive.\n"
                f"  Cause: ~1-2s gap between filename timestamp and actual recording start\n"
                f"  (snapshot save + Telegram HTTP in main.py shifts the baseline negative).\n"
                f"  With PRE_ROLL_SEC={config.PRE_ROLL_SEC}s active, expect avg ≈"
                f" {expected_with_preroll:.1f}s."
            )
    else:
        print("Test 2  CircularOutput pre-roll:       could not determine")
    print("=" * 65)


if __name__ == "__main__":
    main()
