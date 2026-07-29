"""Channel comparison — Blue channel vs true luminance per clip.

For each clip, samples the first 10 frames and reports:
  blue_mean      — cv2.mean(frame)[0]  (what the system currently uses)
  luminance_mean — 0.114*B + 0.587*G + 0.299*R  (ITU-R BT.601 luma)
  grey_mean      — cv2.cvtColor(frame, BGR2GRAY).mean()  (OpenCV grayscale)
  threshold_used — DAY or NIGHT based on current BRIGHTNESS_THRESHOLD vs blue_mean
  correct_thresh — DAY or NIGHT based on luminance_mean

This directly quantifies the #60 bug: if threshold_used != correct_thresh,
the system was using the wrong motion sensitivity for that clip.

Run from 02-scripts/:
    uv run python analyze_brightness_channels.py
"""

import csv
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

CLIPS_DIR = config.CLIPS_DIR
SAMPLE_FRAMES = 10
OUT_CSV = os.path.join(CLIPS_DIR, "brightness_channels.csv")


def analyze(filepath):
    cap = cv2.VideoCapture(filepath)
    if not cap.isOpened():
        return None

    blues, lumas, greys = [], [], []
    for _ in range(SAMPLE_FRAMES):
        ok, frame = cap.read()
        if not ok:
            break
        b, g, r = cv2.split(frame)
        blues.append(float(cv2.mean(frame)[0]))
        lumas.append(float(np.mean(0.114 * b + 0.587 * g + 0.299 * r)))
        greys.append(float(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).mean()))
    cap.release()

    if not blues:
        return None

    blue_mean = sum(blues) / len(blues)
    luma_mean = sum(lumas) / len(lumas)
    grey_mean = sum(greys) / len(greys)

    threshold_used = "DAY" if blue_mean > config.BRIGHTNESS_THRESHOLD else "NIGHT"
    correct_thresh = "DAY" if luma_mean > config.BRIGHTNESS_THRESHOLD else "NIGHT"
    mismatch = threshold_used != correct_thresh

    return {
        "clip": os.path.basename(filepath),
        "blue_mean": round(blue_mean, 1),
        "luma_mean": round(luma_mean, 1),
        "grey_mean": round(grey_mean, 1),
        "brightness_threshold": config.BRIGHTNESS_THRESHOLD,
        "threshold_used": threshold_used,
        "correct_thresh": correct_thresh,
        "mismatch": mismatch,
    }


def main():
    clips = sorted(
        f for f in os.listdir(CLIPS_DIR)
        if f.endswith(".mp4") and os.path.isfile(os.path.join(CLIPS_DIR, f))
    )

    if not clips:
        print(f"No MP4 clips found in {CLIPS_DIR}")
        return

    rows = []
    for clip in clips:
        path = os.path.join(CLIPS_DIR, clip)
        result = analyze(path)
        if result:
            rows.append(result)
            mismatch_flag = " *** MISMATCH" if result["mismatch"] else ""
            print(
                f"{clip}  blue={result['blue_mean']:6.1f}  "
                f"luma={result['luma_mean']:6.1f}  "
                f"grey={result['grey_mean']:6.1f}  "
                f"used={result['threshold_used']}  "
                f"correct={result['correct_thresh']}"
                f"{mismatch_flag}"
            )

    mismatches = sum(1 for r in rows if r["mismatch"])
    print(f"\n{len(rows)} clips analysed — {mismatches} threshold mismatches")
    print(f"BRIGHTNESS_THRESHOLD = {config.BRIGHTNESS_THRESHOLD}")

    with open(OUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"Results saved to {OUT_CSV}")


if __name__ == "__main__":
    main()