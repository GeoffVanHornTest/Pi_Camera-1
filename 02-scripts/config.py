# config.py
# Central settings file for the Pi Night Vision Motion Camera.
# All other modules import their settings from here — change a value
# once here and it takes effect everywhere.

"""Central settings for the PI Camera system.

All other modules import their configuration from here. Values are
loaded from a .env file for credentials and defined as constants for
tunable parameters. Change a value here and it takes effect everywhere.
"""

import os

from dotenv import load_dotenv

# load_dotenv() reads the .env file in this folder and pushes its
# key=value pairs into the environment so os.getenv() can find them.
# This must be called before any os.getenv() calls below.
load_dotenv()

# --- Camera ---
# RESOLUTION is a (width, height) tuple in pixels. 1280x720 (720p) balances
# detail and encoder load on the Pi 4 — confirmed <1% frame drop in field tests.
# FPS is frames per second captured — 30 is standard for smooth video.
RESOLUTION = (1280, 720)
FPS = 30

# --- Motion detection ---
# MOTION_THRESHOLD is the minimum contour area in pixels that counts as
# real motion. Anything smaller is ignored as noise (insects, compression
# artifacts, etc.). Raise this value if you get too many false triggers;
# lower it if real motion is being missed. 500 is a good starting point.
#
# MOTION_COOLDOWN_SEC is the minimum gap between the *start* of one clip and
# the start of the next. new_event_allowed() in motion_detector.py enforces
# this — a second trigger arriving within the window is ignored so one long
# motion event doesn't spawn back-to-back clips. Distinct from
# POST_MOTION_BUFFER_SEC, which controls when the *current* clip ends.
# MOTION_THRESHOLD_DAY is used when grayscale frame brightness is above BRIGHTNESS_THRESHOLD.
# MOTION_THRESHOLD_NIGHT is used in IR/dark mode. Previously 25000 — lowered to 7500 after
# field analysis (#19) showed 25000 suppressed real motion; Blue-channel inflation (#60) was
# also masking night mode entirely. Brightness now derived from grayscale, not Blue channel.
# BRIGHTNESS_THRESHOLD is the mean grayscale pixel value (0-255) separating day from night.
MOTION_THRESHOLD_DAY = 7500
MOTION_THRESHOLD_NIGHT = 7500
BRIGHTNESS_THRESHOLD = 60
MOTION_COOLDOWN_SEC = 10

# --- Scene-change detection gate ---
# MOG2 cannot distinguish a global lighting change (AGC/AEC step adjustments,
# lights on/off, sunrise glare) from real motion — it sees both as foreground.
# This gate tracks a rolling window of mean frame brightness and suppresses
# detection when a significant jump is detected, giving MOG2 time to re-adapt.
#
# Confirmed root cause of 2026-07-22 false-positive burst (10 clips, 07:48–08:28):
# camera AGC/AEC stepped during sunrise, creating frame-wide pixel-value shifts
# that MOG2 classified as foreground. See issue #96 and #19 for full analysis.
#
# SCENE_CHANGE_WINDOW_FRAMES: frames of brightness history to track.
#   150 frames = 5 seconds at 30 fps — long enough to smooth sensor noise,
#   short enough to catch a discrete AGC step within one suppression window.
# SCENE_CHANGE_THRESHOLD: gray-unit delta across the window that arms the gate.
#   5.0 catches AGC steps (~10+ units) while ignoring sunrise drift
#   (~0.03 units over 5 s) and sensor noise (~1–2 units peak-to-peak).
# SCENE_CHANGE_SUPPRESS_SEC: seconds to hold detection suppressed after the gate
#   fires. 10 s gives MOG2 ~300 frames to re-adapt to the new brightness level.
SCENE_CHANGE_WINDOW_FRAMES = 150
SCENE_CHANGE_THRESHOLD = 5.0
SCENE_CHANGE_SUPPRESS_SEC = 10

# --- Layered motion filters ---
# MIN_CONSECUTIVE_FRAMES: how many back-to-back frames must pass all blob checks
# before detect() returns True. Flickering leaves rarely sustain N consecutive
# frames; a walking person typically does. Start at 3 (≈0.1s at 30 fps).
#
# MIN_BLOB_COHERENCE: fraction of total foreground pixels that must belong to
# the single largest blob. A person is one large shape (coherence near 1.0);
# scattered leaf specks have many small blobs (coherence near 0.0). 0.3 means
# "the biggest blob must account for at least 30% of all moving pixels".
#
# CENTROID_HISTORY_LEN: how many past centroid positions to keep in memory.
# Used for the translation-vs-oscillation discriminator: a person's centroid
# moves steadily across the frame; windblown foliage oscillates back and forth.
# Not yet a hard gate — infrastructure for the v0.3.x calibration step.
MIN_CONSECUTIVE_FRAMES = 3
MIN_BLOB_COHERENCE = 0.30
CENTROID_HISTORY_LEN = 10

# --- Pre-record ring buffer ---
# PRE_ROLL_SEC is how many seconds of footage to buffer continuously so that
# the start of a motion event is captured even though recording begins after
# the trigger. The circular output keeps this much H264 data in memory at all
# times; when a clip starts, the buffer is flushed to the file first.
#
# VIDEO_BITRATE_BPS is the H264 encoder target bitrate in bits-per-second.
# Setting this explicitly avoids picamera2's low default (~1 Mbps).
# 2.5 Mbps gives good detail at 720p while keeping file sizes reasonable.
# Note: CircularOutput buffersize is in frames (not bytes), so buffer duration
# is controlled by PRE_ROLL_SEC * FPS, not by this bitrate.
PRE_ROLL_SEC = 8
VIDEO_BITRATE_BPS = 2_500_000

# --- Recording ---
# POST_MOTION_BUFFER_SEC is how long motion must be continuously absent before
# the current clip is finalised. Recording continues for this many seconds
# after the last detected motion frame — the clip tail/debounce timer.
# Distinct from MOTION_COOLDOWN_SEC, which gates when the *next* clip can start.
#
# MAX_RECORD_SEC caps a single clip. If motion continues beyond this point
# the clip is closed, uploaded, and a new one starts immediately.
#
# CLIPS_DIR is the folder where video files are saved, anchored to the
# project root regardless of which directory the script is run from.
POST_MOTION_BUFFER_SEC = 20
MAX_RECORD_SEC = 120
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIPS_DIR = os.path.join(_BASE_DIR, "00-clips")

# --- Logging ---
# LOG_FILE is the persistent event log path. Rotated at 1 MB; 5 backups kept.
# The 05-logs/ directory is created automatically on first write.
LOG_FILE = os.path.join(_BASE_DIR, "05-logs", "pi_camera.log")

# --- Notifications ---
# NOTIFICATION_COOLDOWN_SEC is the minimum gap between Telegram alerts.
# This is separate from MOTION_COOLDOWN_SEC — motion can be detected
# every 10 seconds, but you only want one alert per minute at most,
# even if motion is continuous. Enforced for send_photo() in telegram_notifier.py;
# send_message() (clip-ready links) is intentionally not rate-limited.
NOTIFICATION_COOLDOWN_SEC = 60

# --- Telegram ---
# TELEGRAM_BOT_TOKEN is issued by @BotFather when you create a bot.
# TELEGRAM_CHAT_ID is the numeric ID of the chat the bot should post to —
# find it by messaging your bot and calling /getUpdates on the Bot API.
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# --- Dropbox ---
# DROPBOX_APP_KEY and DROPBOX_APP_SECRET are from the Dropbox app settings page.
# DROPBOX_REFRESH_TOKEN is obtained once via OAuth and never expires unless revoked.
DROPBOX_APP_KEY = os.getenv("DROPBOX_APP_KEY")
DROPBOX_APP_SECRET = os.getenv("DROPBOX_APP_SECRET")
DROPBOX_REFRESH_TOKEN = os.getenv("DROPBOX_REFRESH_TOKEN")
