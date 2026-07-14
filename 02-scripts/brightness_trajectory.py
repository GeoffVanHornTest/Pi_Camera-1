"""Brightness trajectory analysis.

For each clip, tracks mean frame brightness per second and reports:
  initial_brightness  — mean brightness of first 2 seconds
  max_brightness      — peak brightness seen in clip
  max_spike_pct       — largest single-second brightness jump as % of previous
  spike_at_sec        — when the largest spike occurred
  sustained_variation — mean absolute change per second (high = active scene)
  brightness_class    — SPIKE (brief flash), SUSTAINED (gradual), FLAT (static)

Reflections typically show SPIKE at the start then flat.
A person shows SUSTAINED variation throughout.

Run from 02-scripts/:
    python brightness_trajectory.py
"""

import csv
import os
import sys
from datetime import datetime

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config


def analyze(filepath):
    cap = cv2.VideoCapture(filepath)
    if not cap.isOpened():
        return None

    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = n_frames / fps

    # collect mean brightness per second
    brightness_by_sec = {}
    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        sec = int(frame_idx / fps)
        b = float(cv2.mean(frame)[0])
        if sec not in brightness_by_sec:
            brightness_by_sec[sec] = []
        brightness_by_sec[sec].append(b)
        frame_idx += 1
    cap.release()

    if not brightness_by_sec:
        return None

    seconds = sorted(brightness_by_sec.keys())
    means = [float(np.mean(brightness_by_sec[s])) for s in seconds]

    initial = round(float(np.mean(means[:2])), 1) if len(means) >= 2 else round(means[0], 1)
    max_brightness = round(max(means), 1)

    # find largest brightness spike
    max_spike_pct = 0.0
    spike_at_sec = 0
    for i in range(1, len(means)):
        if means[i - 1] > 0:
            delta = (means[i] - means[i - 1]) / means[i - 1]
            if delta > max_spike_pct:
                max_spike_pct = delta
                spike_at_sec = seconds[i]

    sustained_variation = round(float(np.mean([
        abs(means[i] - means[i-1]) for i in range(1, len(means))
    ])), 2) if len(means) > 1 else 0

    # classify
    if max_spike_pct > 0.15 and spike_at_sec <= 3:
        brightness_class = "SPIKE_EARLY"
    elif max_spike_pct > 0.15:
        brightness_class = "SPIKE_LATE"
    elif sustained_variation > 3.0:
        brightness_class = "SUSTAINED"
    else:
        brightness_class = "FLAT"

    return {
        "duration_sec": round(duration, 1),
        "initial_brightness": initial,
        "max_brightness": max_brightness,
        "max_spike_pct": round(max_spike_pct * 100, 1),
        "spike_at_sec": spike_at_sec,
        "sustained_variation": sustained_variation,
        "brightness_class": brightness_class,
    }


def main():
    clips_dir = config.CLIPS_DIR
    clips = sorted([
        f for f in os.listdir(clips_dir)
        if f.startswith("motion_") and f.endswith(".mp4")
    ])

    if not clips:
        print("No clips found.")
        return

    print(f"\n{'Clip':<42} {'init':>5}  {'max':>5}  {'spike%':>7}  {'@sec':>4}  {'variation':>9}  class")
    print("-" * 90)

    rows = []
    for clip in clips:
        path = os.path.join(clips_dir, clip)
        result = analyze(path)
        if result is None:
            print(f"{clip:<42}  (unreadable)")
            rows.append({"clip": clip, **{k: "N/A" for k in
                ["duration_sec","initial_brightness","max_brightness",
                 "max_spike_pct","spike_at_sec","sustained_variation","brightness_class"]}})
            continue

        print(f"{clip:<42} {result['initial_brightness']:>5.1f}  {result['max_brightness']:>5.1f}  "
              f"{result['max_spike_pct']:>6.1f}%  {result['spike_at_sec']:>4}  "
              f"{result['sustained_variation']:>9.2f}  {result['brightness_class']}")
        rows.append({"clip": clip, **result})

    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out = os.path.join(clips_dir, f"brightness_trajectory_{ts}.csv")
    with open(out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["clip","duration_sec","initial_brightness",
                                                "max_brightness","max_spike_pct","spike_at_sec",
                                                "sustained_variation","brightness_class"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nCSV saved: {out}")


if __name__ == "__main__":
    main()