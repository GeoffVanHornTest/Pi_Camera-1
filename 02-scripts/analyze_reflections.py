"""Diagnostic script — classify motion events as person vs. reflection.

For each clip in 00-clips/, replays frames through MOG2 and scores each
motion event against three reflection indicators:

  1. Brightness spike  — frame gets significantly brighter (light source)
  2. High centroid     — motion is in the upper portion of frame (wall, not floor)
  3. Low solidity      — irregular/diffuse contour shape (reflection, not body)

Outputs a verdict per clip: PERSON, REFLECTION, or AMBIGUOUS.
Use this to validate whether false triggers match the reflection pattern
before adding filter logic to motion_detector.py.

Run from 02-scripts/:
    python analyze_reflections.py
"""

import csv
import os
import sys
from datetime import datetime

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

# --- Tunable scoring parameters ---
BRIGHTNESS_SPIKE_PCT = 0.15  # brightness jump > 15% of previous = light event
CENTROID_UPPER_ZONE = 0.45  # centroid in top 45% of frame = wall zone
SOLIDITY_THRESHOLD = 0.45  # solidity < 0.45 = diffuse/irregular = reflection
MIN_CONTOUR_AREA = config.MOTION_THRESHOLD_DAY


def score_frame(frame, fg_mask, prev_brightness, frame_height):
    """Return (reflection_score, flags) for a motion frame.

    reflection_score: 0-3, one point per indicator triggered.
    flags: list of triggered indicator names.
    """
    score = 0
    flags = []

    brightness = float(cv2.mean(frame)[0])

    # 1. Brightness spike
    if prev_brightness > 0:
        delta_pct = (brightness - prev_brightness) / prev_brightness
        if delta_pct > BRIGHTNESS_SPIKE_PCT:
            score += 1
            flags.append(f"brightness+{delta_pct:.0%}")

    # 2. Motion region brightness direction — reflections make pixels brighter,
    #    a person moving through existing light stays similar or darker
    motion_pixels = frame[fg_mask > 0]
    background_pixels = frame[fg_mask == 0]
    if len(motion_pixels) > 50 and len(background_pixels) > 50:
        motion_mean = float(np.mean(motion_pixels))
        background_mean = float(np.mean(background_pixels))
        if motion_mean > background_mean * 1.25:
            score += 1
            flags.append(f"bright-region({motion_mean / background_mean:.2f}x)")

    # 3. Centroid position and solidity of largest contour
    contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    big = [c for c in contours if cv2.contourArea(c) > MIN_CONTOUR_AREA]
    if big:
        largest = max(big, key=cv2.contourArea)

        M = cv2.moments(largest)
        if M["m00"] > 0:
            cy = M["m01"] / M["m00"]
            if cy < frame_height * CENTROID_UPPER_ZONE:
                score += 1
                flags.append(f"high-centroid(y={cy / frame_height:.0%})")

        hull = cv2.convexHull(largest)
        hull_area = cv2.contourArea(hull)
        if hull_area > 0:
            solidity = cv2.contourArea(largest) / hull_area
            if solidity < SOLIDITY_THRESHOLD:
                score += 1
                flags.append(f"low-solidity({solidity:.2f})")

    return score, flags, brightness


def analyze(filepath):
    cap = cv2.VideoCapture(filepath)
    if not cap.isOpened():
        return None

    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = n_frames / fps

    bg = cv2.createBackgroundSubtractorMOG2(detectShadows=False)

    motion_frames = 0
    reflection_flags = []  # (frame_sec, score, flags)
    prev_brightness = 0.0

    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        fg_mask = bg.apply(frame)
        contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        motion = any(cv2.contourArea(c) > MIN_CONTOUR_AREA for c in contours)

        if motion:
            motion_frames += 1
            score, flags, brightness = score_frame(frame, fg_mask, prev_brightness, h)
            if score > 0:
                reflection_flags.append((frame_idx / fps, score, flags))
        else:
            _brightness = float(cv2.mean(frame)[0])

        prev_brightness = float(cv2.mean(frame)[0])
        frame_idx += 1

    cap.release()

    return duration, motion_frames, reflection_flags, n_frames


def verdict(motion_frames, reflection_flags):
    if motion_frames == 0:
        return "NO MOTION"
    if not reflection_flags:
        return "PERSON"
    refection_frame_count = len(reflection_flags)
    pct = refection_frame_count / motion_frames
    high_score = sum(1 for _, s, _ in reflection_flags if s >= 2)
    if pct > 0.5 and high_score > motion_frames * 0.3:
        return "REFLECTION"
    if pct > 0.25 or high_score > 0:
        return "AMBIGUOUS"
    return "PERSON"


def main():
    clips_dir = config.CLIPS_DIR
    clips = sorted(
        [f for f in os.listdir(clips_dir) if f.startswith("motion_") and f.endswith(".mp4")]
    )

    if not clips:
        print("No clips found in", clips_dir)
        return

    print(f"\n{'Clip':<42} {'Dur':>6}  {'Motion':>8}  {'Reflect%':>8}  {'Verdict'}")
    print("-" * 85)

    rows = []
    for clip in clips:
        path = os.path.join(clips_dir, clip)
        result = analyze(path)
        if result is None:
            print(f"{clip:<42}  (unreadable)")
            rows.append(
                {
                    "clip": clip,
                    "duration_sec": "unreadable",
                    "motion_frames": "",
                    "reflection_pct": "",
                    "verdict": "unreadable",
                    "top_flags": "",
                }
            )
            continue

        duration, motion_frames, reflection_flags, n_frames = result
        v = verdict(motion_frames, reflection_flags)

        if motion_frames > 0:
            r_pct = len(reflection_flags) / motion_frames * 100
        else:
            r_pct = 0

        flag_summary = ""
        if reflection_flags:
            # show the most common flag type across all flagged frames
            all_flags = [f for _, _, fs in reflection_flags for f in fs]
            types = {}
            for f in all_flags:
                key = f.split("(")[0]
                types[key] = types.get(key, 0) + 1
            flag_summary = ", ".join(
                f"{k}×{v}" for k, v in sorted(types.items(), key=lambda x: -x[1])
            )

        print(
            f"{clip:<42} {duration:>5.1f}s  {motion_frames:>6}fr"
            f"  {r_pct:>7.1f}%  {v:<12}  {flag_summary}"
        )
        rows.append(
            {
                "clip": clip,
                "duration_sec": round(duration, 1),
                "motion_frames": motion_frames,
                "reflection_pct": round(r_pct, 1),
                "verdict": v,
                "top_flags": flag_summary,
            }
        )

    print()
    print(
        "Scoring: 1pt each — brightness spike >15%, bright motion region"
        " >1.25x bg, centroid in top 45%, solidity <0.45"
    )
    print("REFLECTION = >50% motion frames scored + >30% scored ≥2 indicators")
    print("AMBIGUOUS  = >25% motion frames scored or any 2-indicator frames")
    print("PERSON     = <25% motion frames scored, no 2-indicator frames")

    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    csv_path = os.path.join(config.CLIPS_DIR, f"reflection_analysis_{ts}.csv")
    fieldnames = ["clip", "duration_sec", "motion_frames", "reflection_pct", "verdict", "top_flags"]
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nCSV saved: {csv_path}")


if __name__ == "__main__":
    main()
