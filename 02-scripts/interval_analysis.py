"""Inter-clip interval and temporal clustering analysis.

Parses clip timestamps from filenames — no video processing needed.

Clips within CLUSTER_GAP_SEC of each other are assigned the same cluster ID.
A cluster of 2+ clips usually means a sustained or repeating trigger source
(a moving light source, continuous background noise, or a person present for a while).

Metrics:
  interval_from_prev_sec — seconds since previous clip started
  interval_to_next_sec   — seconds until next clip starts
  in_cluster             — True if within CLUSTER_GAP_SEC of a neighbour
  cluster_id             — integer ID shared by clips in the same cluster
  cluster_size           — how many clips share this cluster

Run from 02-scripts/:
    python interval_analysis.py
"""

import csv
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

CLUSTER_GAP_SEC = 120  # clips within 2 minutes = same cluster


def parse_timestamp(clip):
    try:
        ts = clip.replace("motion_", "").replace(".mp4", "")
        return datetime.strptime(ts, "%Y-%m-%d_%H-%M-%S")
    except ValueError:
        return None


def main():
    clips_dir = config.CLIPS_DIR
    clips = sorted(
        [f for f in os.listdir(clips_dir) if f.startswith("motion_") and f.endswith(".mp4")]
    )

    if not clips:
        print("No clips found.")
        return

    # parse timestamps
    entries = []
    for clip in clips:
        ts = parse_timestamp(clip)
        if ts:
            entries.append((clip, ts))

    entries.sort(key=lambda x: x[1])

    # assign clusters
    clusters = []
    current_cluster = [entries[0]]

    for i in range(1, len(entries)):
        gap = (entries[i][1] - entries[i - 1][1]).total_seconds()
        if gap <= CLUSTER_GAP_SEC:
            current_cluster.append(entries[i])
        else:
            clusters.append(current_cluster)
            current_cluster = [entries[i]]
    clusters.append(current_cluster)

    # build lookup: clip → (cluster_id, cluster_size)
    clip_cluster = {}
    for cid, cluster in enumerate(clusters):
        for clip, _ in cluster:
            clip_cluster[clip] = (cid + 1, len(cluster))

    print(
        f"\n{'Clip':<42} {'prev_gap':>8}  {'next_gap':>8}  {'cluster':>7}  {'size':>4}  in_cluster"
    )
    print("-" * 88)

    rows = []
    for i, (clip, ts) in enumerate(entries):
        prev_gap = round((ts - entries[i - 1][1]).total_seconds(), 1) if i > 0 else None
        next_gap = (
            round((entries[i + 1][1] - ts).total_seconds(), 1) if i < len(entries) - 1 else None
        )
        cid, csize = clip_cluster.get(clip, (0, 1))
        in_cluster = csize > 1

        prev_str = f"{prev_gap:>7.0f}s" if prev_gap is not None else "    N/A"
        next_str = f"{next_gap:>7.0f}s" if next_gap is not None else "    N/A"

        print(
            f"{clip:<42} {prev_str}  {next_str}"
            f"  C{cid:>6}  {csize:>4}  {'YES' if in_cluster else 'no'}"
        )

        rows.append(
            {
                "clip": clip,
                "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
                "interval_from_prev_sec": prev_gap if prev_gap is not None else "",
                "interval_to_next_sec": next_gap if next_gap is not None else "",
                "cluster_id": cid,
                "cluster_size": csize,
                "in_cluster": in_cluster,
            }
        )

    # summarise clusters
    print(f"\nClusters (>{CLUSTER_GAP_SEC}s gap = new cluster):")
    for cid, cluster in enumerate(clusters):
        start = cluster[0][1].strftime("%H:%M:%S")
        end = cluster[-1][1].strftime("%H:%M:%S")
        span = round((cluster[-1][1] - cluster[0][1]).total_seconds(), 0)
        print(f"  C{cid + 1}: {len(cluster)} clips  {start}→{end}  ({span:.0f}s span)")

    ts_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out = os.path.join(clips_dir, f"interval_analysis_{ts_str}.csv")
    with open(out, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "clip",
                "timestamp",
                "interval_from_prev_sec",
                "interval_to_next_sec",
                "cluster_id",
                "cluster_size",
                "in_cluster",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nCSV saved: {out}")


if __name__ == "__main__":
    main()
