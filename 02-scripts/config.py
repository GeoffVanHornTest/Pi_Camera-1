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

# --- Gmail credentials ---
# These are loaded from the .env file so they never appear in source code.
# os.getenv() looks up the value by key name. If the key is missing it
# returns None, which will produce a clear error later rather than a
# mysterious crash.
GMAIL_SENDER = os.getenv("GMAIL_SENDER")  # address the Pi sends from
GMAIL_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")  # Gmail App Password (not your login password)
GMAIL_RECIPIENT = os.getenv("GMAIL_RECIPIENT")  # address the alert is sent to

# --- Camera ---
# RESOLUTION is a (width, height) tuple in pixels. 1920x1080 is full HD
# and well within the OV5647's capability.
# FPS is frames per second captured — 30 is standard for smooth video.
RESOLUTION = (1920, 1080)
FPS = 30

# --- Motion detection ---
# MOTION_THRESHOLD is the minimum contour area in pixels that counts as
# real motion. Anything smaller is ignored as noise (insects, compression
# artifacts, etc.). Raise this value if you get too many false triggers;
# lower it if real motion is being missed. 500 is a good starting point.
#
# MOTION_COOLDOWN_SEC is how many seconds must pass after motion is first
# detected before the detector can fire again. Prevents one continuous
# movement from triggering hundreds of events.
MOTION_THRESHOLD = 500
MOTION_COOLDOWN_SEC = 10

# --- Recording ---
# POST_MOTION_BUFFER_SEC keeps the camera recording for this many seconds
# after motion stops. Without it, the clip would cut off the moment the
# subject leaves frame.
#
# CLIPS_DIR is the folder where video files are saved, anchored to the
# project root regardless of which directory the script is run from.
POST_MOTION_BUFFER_SEC = 5
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIPS_DIR = os.path.join(_BASE_DIR, "00-clips")

# --- Notifications ---
# NOTIFICATION_COOLDOWN_SEC is the minimum gap between alert emails (Gmail backend).
# This is separate from MOTION_COOLDOWN_SEC — motion can be detected
# every 10 seconds, but you only want one email per minute at most,
# even if motion is continuous.
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
