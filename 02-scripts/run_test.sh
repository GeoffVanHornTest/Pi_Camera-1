#!/usr/bin/env bash
# run_test.sh — run the camera until N clips have been recorded, then stop.
# Usage: bash run_test.sh [N]   (default N=10)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CLIPS_DIR="$PROJECT_DIR/00-clips"
MAX_CLIPS="${1:-10}"

cd "$PROJECT_DIR"

# find exits 0 even when no files match, unlike ls with a glob
count_clips() {
    find "$CLIPS_DIR" -maxdepth 1 -name "motion_*.mp4" | wc -l
}

INITIAL=$(count_clips)
TARGET=$(( INITIAL + MAX_CLIPS ))

echo "============================================"
echo "  PI Camera test — stop after $MAX_CLIPS clips"
echo "  Clips already in $CLIPS_DIR: $INITIAL"
echo "  Will stop at: $TARGET total clips"
echo "============================================"
echo ""
echo "Starting in 60 seconds — position the camera now."
for i in $(seq 60 -5 5); do
    echo "  $i seconds..."
    sleep 5
done
echo "  Starting now."
echo ""

uv run python 02-scripts/main.py &
CAMERA_PID=$!
echo "Camera started (PID $CAMERA_PID)"
echo ""

while true; do
    sleep 5
    CURRENT=$(count_clips)
    NEW=$(( CURRENT - INITIAL ))
    echo "$(date '+%H:%M:%S')  clips this session: $NEW / $MAX_CLIPS"

    if [ "$CURRENT" -ge "$TARGET" ]; then
        echo ""
        echo "$MAX_CLIPS clips recorded — stopping camera."
        kill "$CAMERA_PID" 2>/dev/null || true
        wait "$CAMERA_PID" 2>/dev/null || true
        echo "Done."
        break
    fi
done