"""Spatial motion heatmap analysis.

For each clip, accumulates MOG2 foreground masks into a heatmap showing WHERE
in the frame motion occurred. Saves a PNG heatmap per clip and a summary CSV.

Key metrics:
  wall_zone_pct   — % of motion in the top 40% of the frame (wall/ceiling area)
  person_zone_pct — % of motion in the bottom 60% (where a standing person would be)
  peak_y_pct      — vertical position of peak motion (0=top, 1=bottom)
  motion_spread   — std dev of motion y-positions (high = spread across whole frame)

Run from 02-scripts/:
    python heatmap_analysis.py
"""

import csv
import os
import sys
from datetime import datetime

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

WALL_ZONE_CUTOFF = 0.40  # top 40% = wall/ceiling zone


def analyze(filepath):
    cap = cv2.VideoCapture(filepath)
    if not cap.isOpened():
        return None

    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    _fps = cap.get(cv2.CAP_PROP_FPS) or 30
    _n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    bg = cv2.createBackgroundSubtractorMOG2(detectShadows=False)
    heatmap = np.zeros((h, w), dtype=np.float32)

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        mask = bg.apply(frame)
        heatmap += (mask > 0).astype(np.float32)

    cap.release()

    total_motion = heatmap.sum()
    if total_motion == 0:
        return None

    wall_cutoff_px = int(h * WALL_ZONE_CUTOFF)
    wall_motion = heatmap[:wall_cutoff_px, :].sum()
    person_motion = heatmap[wall_cutoff_px:, :].sum()

    # peak motion location
    peak_pos = np.unravel_index(np.argmax(heatmap), heatmap.shape)
    peak_y_pct = round(peak_pos[0] / h, 3)
    peak_x_pct = round(peak_pos[1] / w, 3)

    # y-spread of motion
    ys, _ = np.where(heatmap > heatmap.max() * 0.1)
    motion_spread = round(float(np.std(ys)) / h, 3) if len(ys) > 0 else 0

    wall_zone_pct = round(wall_motion / total_motion * 100, 1)
    person_zone_pct = round(person_motion / total_motion * 100, 1)

    # save normalised heatmap PNG
    norm = cv2.normalize(heatmap, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    coloured = cv2.applyColorMap(norm, cv2.COLORMAP_JET)
    # draw zone boundary
    cv2.line(coloured, (0, wall_cutoff_px), (w, wall_cutoff_px), (255, 255, 255), 2)
    png_name = os.path.splitext(os.path.basename(filepath))[0] + "_heatmap.png"
    png_path = os.path.join(config.CLIPS_DIR, png_name)
    cv2.imwrite(png_path, coloured)

    return {
        "wall_zone_pct": wall_zone_pct,
        "person_zone_pct": person_zone_pct,
        "peak_y_pct": peak_y_pct,
        "peak_x_pct": peak_x_pct,
        "motion_spread": motion_spread,
        "heatmap_png": png_name,
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

    print(f"\n{'Clip':<42} {'wall%':>6}  {'person%':>7}  {'peak_y':>6}  {'spread':>6}  zone")
    print("-" * 80)

    rows = []
    for clip in clips:
        path = os.path.join(clips_dir, clip)
        result = analyze(path)
        if result is None:
            print(f"{clip:<42}  (unreadable or no motion)")
            rows.append({"clip": clip, **{k: "N/A" for k in
                ["wall_zone_pct","person_zone_pct","peak_y_pct","peak_x_pct","motion_spread","zone","heatmap_png"]}})
            continue

        zone = "WALL" if result["wall_zone_pct"] > 60 else \
               "MIXED" if result["wall_zone_pct"] > 30 else "PERSON_ZONE"

        print(f"{clip:<42} {result['wall_zone_pct']:>5.1f}%  {result['person_zone_pct']:>6.1f}%  "
              f"{result['peak_y_pct']:>6.3f}  {result['motion_spread']:>6.3f}  {zone}")

        rows.append({"clip": clip, **result, "zone": zone})

    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out = os.path.join(clips_dir, f"heatmap_analysis_{ts}.csv")
    with open(out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["clip","wall_zone_pct","person_zone_pct",
                                                "peak_y_pct","peak_x_pct","motion_spread","zone","heatmap_png"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nCSV saved: {out}")
    print("Heatmap PNGs saved alongside clips in 00-clips/")


if __name__ == "__main__":
    main()