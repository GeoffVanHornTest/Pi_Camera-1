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
# MOTION_THRESHOLD_DAY is used when average frame brightness is above BRIGHTNESS_THRESHOLD.
# MOTION_THRESHOLD_NIGHT is used in IR/dark mode — noise floor is significantly higher
# due to IR LED flicker and increased sensor gain at low light.
# BRIGHTNESS_THRESHOLD is the mean pixel value (0-255) that separates day from night mode.
MOTION_THRESHOLD_DAY = 7500
MOTION_THRESHOLD_NIGHT = 25000
BRIGHTNESS_THRESHOLD = 60
MOTION_COOLDOWN_SEC = 10

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

# --- Notifications ---
# NOTIFICATION_COOLDOWN_SEC is the minimum gap between Telegram alerts.
# This is separate from MOTION_COOLDOWN_SEC — motion can be detected
# every 10 seconds, but you only want one alert per minute at most,
# even if motion is continuous. Currently defined but not enforced (#71).
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
