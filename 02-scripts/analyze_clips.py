"""Diagnostic script — analyze MP4 clips to find motion gap durations.

For each clip in 00-clips/, runs MOG2 at multiple threshold levels and reports:
- Total duration
- Longest gap with no motion detected
- Percentage of frames with motion detected

Run from the 02-scripts directory:
    python analyze_clips.py
"""

import os
import sys

import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

THRESHOLDS = [5000, 10000, 15000, 25000]


def analyze(filepath):
    cap = cv2.VideoCapture(filepath)
    if not cap.isOpened():
        return None

    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps

    bg = cv2.createBackgroundSubtractorMOG2(detectShadows=False)

    results = {t: {"motion_frames": 0, "max_gap_sec": 0.0} for t in THRESHOLDS}
    gap_start = {t: None for t in THRESHOLDS}

    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        mask = bg.apply(frame)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        max_area = max((cv2.contourArea(c) for c in contours), default=0)
        t_sec = frame_idx / fps

        for t in THRESHOLDS:
            if max_area > t:
                results[t]["motion_frames"] += 1
                if gap_start[t] is not None:
                    gap = t_sec - gap_start[t]
                    results[t]["max_gap_sec"] = max(results[t]["max_gap_sec"], gap)
                    gap_start[t] = None
            else:
                if gap_start[t] is None:
                    gap_start[t] = t_sec

        frame_idx += 1

    cap.release()

    # close any open gap at end of clip
    for t in THRESHOLDS:
        if gap_start[t] is not None:
            gap = duration - gap_start[t]
            results[t]["max_gap_sec"] = max(results[t]["max_gap_sec"], gap)

    return duration, total_frames, fps, results


def main():
    clips_dir = config.CLIPS_DIR
    clips = sorted([
        f for f in os.listdir(clips_dir)
        if f.startswith("motion_") and f.endswith(".mp4")
    ])

    if not clips:
        print("No clips found in", clips_dir)
        return

    header = f"{'Clip':<40} {'Dur':>6}  " + "  ".join(f"T={t//1000}k gap" for t in THRESHOLDS)
    print(header)
    print("-" * len(header))

    for clip in clips:
        path = os.path.join(clips_dir, clip)
        result = analyze(path)
        if result is None:
            print(f"{clip:<40}  (unreadable)")
            continue

        duration, total_frames, fps, res = result
        gaps = "  ".join(f"{res[t]['max_gap_sec']:>9.1f}s" for t in THRESHOLDS)
        print(f"{clip:<40} {duration:>5.1f}s  {gaps}")

    print()
    print("'gap' = longest continuous period with no motion above that threshold.")
    print(f"Current config: DAY={config.MOTION_THRESHOLD_DAY}, NIGHT={config.MOTION_THRESHOLD_NIGHT}")
    print(f"POST_MOTION_BUFFER_SEC={config.POST_MOTION_BUFFER_SEC}, MIN_RECORD_SEC={config.MIN_RECORD_SEC}")


if __name__ == "__main__":
    main()