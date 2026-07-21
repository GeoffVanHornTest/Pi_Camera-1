"""Cross-analysis — joins all five datasets into a single scored verdict.

Auto-discovers the most recent CSV of each type in 00-clips/ and joins them
on clip name. Produces a confidence score (0-9) and final verdict per clip.

Scoring (one point each unless noted):
  gap_ratio > 0.85          +2  strong empty-room signal
  gap_ratio > 0.60          +1  partial empty-room signal
  wall_zone_pct > 60        +1  motion concentrated on wall
  brightness_class SPIKE*   +1  brightness spike detected
  mb_per_sec < 0.25         +1  low file complexity (static scene)
  in_cluster = True         +1  rapid repeat trigger
  reflection_pct > 50       +1  reflection heuristics fired
  duration_class SHORT       +1  clip at minimum duration

Final verdict:
  0-2  PERSON
  3-4  LIKELY_PERSON
  5-6  LIKELY_FALSE
  7-9  FALSE_TRIGGER

Run from 02-scripts/:
    python cross_analysis.py
"""

import csv
import glob
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config


def latest(pattern):
    files = sorted(glob.glob(os.path.join(config.CLIPS_DIR, pattern)))
    return files[-1] if files else None


def read_csv(path):
    if not path:
        return {}
    with open(path, newline="") as f:
        return {row["clip"]: row for row in csv.DictReader(f)}


def safe_float(val, default=0.0):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def safe_bool(val):
    return str(val).strip().upper() in ("TRUE", "1", "YES")


def score_clip(gap, ref, heat, bright, dur, interval):
    points = 0
    reasons = []

    gap_ratio = safe_float(gap.get("gap_ratio", 0))
    if gap_ratio > 0.85:
        points += 2
        reasons.append(f"gap_ratio={gap_ratio:.2f}(+2)")
    elif gap_ratio > 0.60:
        points += 1
        reasons.append(f"gap_ratio={gap_ratio:.2f}(+1)")

    wall_pct = safe_float(heat.get("wall_zone_pct", 0))
    if wall_pct > 60:
        points += 1
        reasons.append(f"wall={wall_pct:.0f}%")

    b_class = bright.get("brightness_class", "")
    if "SPIKE" in b_class:
        points += 1
        reasons.append(f"brightness={b_class}")

    mb_per_sec = safe_float(dur.get("mb_per_sec", 99))
    if 0 < mb_per_sec < 0.25:
        points += 1
        reasons.append(f"mb/s={mb_per_sec:.2f}")

    in_cluster = safe_bool(interval.get("in_cluster", False))
    if in_cluster:
        points += 1
        reasons.append(f"cluster_size={interval.get('cluster_size', '?')}")

    reflect_pct = safe_float(ref.get("reflection_pct", 0))
    if reflect_pct > 50:
        points += 1
        reasons.append(f"reflect={reflect_pct:.0f}%")

    dur_class = dur.get("duration_class", "")
    if dur_class == "SHORT":
        points += 1
        reasons.append("SHORT_clip")

    if points >= 7:
        verdict = "FALSE_TRIGGER"
    elif points >= 5:
        verdict = "LIKELY_FALSE"
    elif points >= 3:
        verdict = "LIKELY_PERSON"
    else:
        verdict = "PERSON"

    return points, verdict, ", ".join(reasons)


def main():
    gap_path = latest("combined_analysis_*.csv")
    ref_path = latest("reflection_analysis_*.csv")
    heat_path = latest("heatmap_analysis_*.csv")
    bright_path = latest("brightness_trajectory_*.csv")
    dur_path = latest("duration_stats_*.csv")
    int_path = latest("interval_analysis_*.csv")

    print("Input files:")
    for label, path in [
        ("combined", gap_path),
        ("reflection", ref_path),
        ("heatmap", heat_path),
        ("brightness", bright_path),
        ("duration", dur_path),
        ("interval", int_path),
    ]:
        print(f"  {label:<12} {os.path.basename(path) if path else 'NOT FOUND'}")

    gaps = read_csv(gap_path)
    refs = read_csv(ref_path)
    heats = read_csv(heat_path)
    brights = read_csv(bright_path)
    durs = read_csv(dur_path)
    intervals = read_csv(int_path)

    all_clips = sorted(
        set(
            list(gaps.keys())
            + list(refs.keys())
            + list(heats.keys())
            + list(brights.keys())
            + list(durs.keys())
            + list(intervals.keys())
        )
    )

    print(f"\n{'Clip':<42} {'Score':>5}  {'Verdict':<16}  Reasons")
    print("-" * 110)

    rows = []
    verdict_counts = {}
    for clip in all_clips:
        if not clip.endswith(".mp4"):
            continue
        score, verdict, reasons = score_clip(
            gaps.get(clip, {}),
            refs.get(clip, {}),
            heats.get(clip, {}),
            brights.get(clip, {}),
            durs.get(clip, {}),
            intervals.get(clip, {}),
        )
        verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1
        print(f"{clip:<42} {score:>5}  {verdict:<16}  {reasons}")
        rows.append(
            {
                "clip": clip,
                "score": score,
                "verdict": verdict,
                "reasons": reasons,
                "gap_ratio": gaps.get(clip, {}).get("gap_ratio", ""),
                "wall_zone_pct": heats.get(clip, {}).get("wall_zone_pct", ""),
                "brightness_class": brights.get(clip, {}).get("brightness_class", ""),
                "mb_per_sec": durs.get(clip, {}).get("mb_per_sec", ""),
                "in_cluster": intervals.get(clip, {}).get("in_cluster", ""),
                "reflection_pct": refs.get(clip, {}).get("reflection_pct", ""),
                "duration_class": durs.get(clip, {}).get("duration_class", ""),
            }
        )

    print(f"\nVerdict summary: {verdict_counts}")
    print(f"Total clips: {len(rows)}")

    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out = os.path.join(config.CLIPS_DIR, f"cross_analysis_{ts}.csv")
    fieldnames = [
        "clip",
        "score",
        "verdict",
        "reasons",
        "gap_ratio",
        "wall_zone_pct",
        "brightness_class",
        "mb_per_sec",
        "in_cluster",
        "reflection_pct",
        "duration_class",
    ]
    with open(out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nCSV saved: {out}")


if __name__ == "__main__":
    main()
