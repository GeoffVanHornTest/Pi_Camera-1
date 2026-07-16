"""Clip duration statistics and time-of-day population analysis.

Parses clip filenames for timestamps and file sizes — no video processing needed.

Metrics:
  duration_class  — SHORT (<25s, likely false trigger hitting buffer),
                    MEDIUM (25-60s), LONG (60-180s), MAXED (>180s, hit MAX_RECORD_SEC)
  time_of_day     — NIGHT (0-6h), MORNING (6-10h), DAY (10-18h), EVENING (18-24h)
  file_size_mb    — proxy for video complexity (static scene = smaller file per second)
  mb_per_sec      — file size / duration; low = static scene, high = active scene

Run from 02-scripts/:
    python duration_stats.py
"""

import csv
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
import cv2


def get_duration(path):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return None
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    return round(n / fps, 1) if n > 0 else None


def classify_duration(sec):
    if sec < 25:
        return "SHORT"
    elif sec < 60:
        return "MEDIUM"
    elif sec <= 180:
        return "LONG"
    else:
        return "MAXED"


def classify_time(hour):
    if hour < 6:
        return "NIGHT"
    elif hour < 10:
        return "MORNING"
    elif hour < 18:
        return "DAY"
    else:
        return "EVENING"


def parse_timestamp(clip):
    # motion_YYYY-MM-DD_HH-MM-SS.mp4
    try:
        ts = clip.replace("motion_", "").replace(".mp4", "")
        return datetime.strptime(ts, "%Y-%m-%d_%H-%M-%S")
    except ValueError:
        return None


def main():
    clips_dir = config.CLIPS_DIR
    clips = sorted([
        f for f in os.listdir(clips_dir)
        if f.startswith("motion_") and f.endswith(".mp4")
    ])

    if not clips:
        print("No clips found.")
        return

    print(
        f"\n{'Clip':<42} {'Dur':>6}  {'Class':<8}  {'MB':>5}  {'MB/s':>5}"
        f"  {'Hour':>4}  time_of_day"
    )
    print("-" * 90)

    rows = []
    duration_classes = {}
    time_classes = {}

    for clip in clips:
        path = os.path.join(clips_dir, clip)
        duration = get_duration(path)
        ts = parse_timestamp(clip)
        size_bytes = os.path.getsize(path)
        size_mb = round(size_bytes / 1_000_000, 1)

        if duration is None:
            print(f"{clip:<42}  (unreadable)")
            rows.append({"clip": clip, "duration_sec": "N/A", "duration_class": "UNREADABLE",
                         "file_size_mb": size_mb, "mb_per_sec": "N/A",
                         "hour": "N/A", "time_of_day": "N/A"})
            continue

        dur_class = classify_duration(duration)
        hour = ts.hour if ts else -1
        time_class = classify_time(hour) if hour >= 0 else "UNKNOWN"
        mb_per_sec = round(size_mb / duration, 2) if duration > 0 else 0

        duration_classes[dur_class] = duration_classes.get(dur_class, 0) + 1
        time_classes[time_class] = time_classes.get(time_class, 0) + 1

        print(f"{clip:<42} {duration:>5.1f}s  {dur_class:<8}  {size_mb:>5.1f}  {mb_per_sec:>5.2f}  "
              f"{hour:>4}h  {time_class}")

        rows.append({
            "clip": clip,
            "duration_sec": duration,
            "duration_class": dur_class,
            "file_size_mb": size_mb,
            "mb_per_sec": mb_per_sec,
            "hour": hour,
            "time_of_day": time_class,
        })

    print(f"\nDuration distribution: {duration_classes}")
    print(f"Time of day distribution: {time_classes}")

    ts_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out = os.path.join(clips_dir, f"duration_stats_{ts_str}.csv")
    with open(out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["clip","duration_sec","duration_class",
                                                "file_size_mb","mb_per_sec","hour","time_of_day"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nCSV saved: {out}")


if __name__ == "__main__":
    main()