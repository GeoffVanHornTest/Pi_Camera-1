"""Combine gap analysis and reflection analysis CSVs into one dataset.

Auto-discovers the most recent analysis_*.csv and reflection_analysis_*.csv
in 00-clips/ and joins them on clip name, adding gap_ratio as a derived metric.

Run from 02-scripts/:
    python combine_analysis.py
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
    with open(path, newline="") as f:
        return {row["clip"]: row for row in csv.DictReader(f)}


def main():
    gap_path = latest("analysis_*.csv")
    ref_path = latest("reflection_analysis_*.csv")

    if not gap_path:
        print("No gap analysis CSV found — run analyze_clips.py first.")
        return
    if not ref_path:
        print("No reflection analysis CSV found — run analyze_reflections.py first.")
        return

    print(f"Gap data:        {os.path.basename(gap_path)}")
    print(f"Reflection data: {os.path.basename(ref_path)}")

    gaps = read_csv(gap_path)
    refs = read_csv(ref_path)

    all_clips = sorted(set(list(gaps.keys()) + list(refs.keys())))

    rows = []
    print(
        f"\n{'Clip':<42} {'Dur':>6}  {'gap_T5k':>7}  {'gap_ratio':>9}"
        f"  {'reflect%':>8}  {'verdict':<12}  {'combined'}"
    )
    print("-" * 105)

    for clip in all_clips:
        g = gaps.get(clip, {})
        r = refs.get(clip, {})

        raw = g.get("duration_sec", 0)
        try:
            duration = float(raw or 0)
        except (ValueError, TypeError):
            duration = 0.0
        try:
            gap_t5k = float(g.get("gap_T5000", 0) or 0)
        except (ValueError, TypeError):
            gap_t5k = 0.0
        gap_ratio = round(gap_t5k / duration, 3) if duration > 0 else 0
        try:
            reflect_pct = float(r.get("reflection_pct", 0) or 0)
        except (ValueError, TypeError):
            reflect_pct = 0.0
        verdict = r.get("verdict", "N/A")

        # combined verdict: gap_ratio is ground truth, reflection is soft signal
        if duration == 0 or g.get("duration_sec") == "unreadable":
            combined = "UNREADABLE"
        elif gap_ratio > 0.85:
            combined = "FALSE_TRIGGER" if reflect_pct > 20 else "BRIEF_EVENT"
        elif gap_ratio < 0.35 and reflect_pct < 25:
            combined = "PERSON"
        elif gap_ratio < 0.35 and reflect_pct >= 25:
            combined = "PERSON+REFLECT"
        elif gap_ratio > 0.6 and reflect_pct > 40:
            combined = "LIKELY_FALSE"
        else:
            combined = "AMBIGUOUS"

        rows.append(
            {
                "clip": clip,
                "duration_sec": duration,
                "gap_T5k": gap_t5k,
                "gap_ratio": gap_ratio,
                "reflection_pct": reflect_pct,
                "verdict": verdict,
                "combined_verdict": combined,
            }
        )

        print(
            f"{clip:<42} {duration:>5.1f}s  {gap_t5k:>6.1f}s"
            f"  {gap_ratio:>9.3f}  {reflect_pct:>7.1f}%  {verdict:<12}  {combined}"
        )

    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out = os.path.join(config.CLIPS_DIR, f"combined_analysis_{ts}.csv")
    with open(out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nCSV saved: {out}")


if __name__ == "__main__":
    main()
