# Pi Night Vision Motion Camera — Progress Log

This document captures all decisions made and code written so far.
Use it to resume work on a new machine or after a long break.

---

## Project Summary

A motion-detection security camera using a Raspberry Pi 4 and an Arducam
5MP OV5647 camera module with IR LEDs for night vision. When motion is
detected the Pi records a video clip, saves a snapshot, and emails an alert
with the snapshot attached to a Gmail address.

---

## Key Decisions Made

| Decision | Choice | Reason |
|---|---|---|
| Notification method | Gmail via SMTP | Rogers Canada discontinued their email-to-SMS gateway. Gmail push notification via the Gmail app works just as well. |
| Gmail auth | App Password (not login password) | Google requires App Passwords for SMTP access when 2-Step Verification is on |
| OpenCV install | `opencv-python-headless` | Pi doesn't need the GUI display components — headless is lighter |
| Motion algorithm | MOG2 background subtraction | Adapts to gradual lighting changes, better than simple frame-diff for night scenes |
| Config format | `config.py` (not JSON) | Pure Python project — no parsing boilerplate, supports logic and comments |

---

## Project Structure

```
pi_camera/
├── main.py              # Entry point — wires all modules together (not started)
├── config.py            # All settings and constants (COMPLETE)
├── camera.py            # Camera setup, frame capture, video recording (COMPLETE)
├── motion_detector.py   # Motion detection logic (COMPLETE)
├── notifier.py          # Sends Gmail alert with snapshot attached (COMPLETE)
├── storage.py           # Timestamped filenames, clip/disk management (COMPLETE)
├── .env                 # Secrets — fill in before running
├── .gitignore           # Excludes .env and clips/ from version control
├── requirements.txt     # Third-party dependencies
└── clips/               # Where recorded video and snapshots are saved
```

---

## Dependencies

```
# requirements.txt
picamera2
opencv-python-headless
python-dotenv
```

Install on the Pi:
```bash
pip install picamera2 opencv-python-headless python-dotenv
```

---

## `.env` File

Create this file in the project root and fill in your real values.
**Never commit this file** — it is already listed in `.gitignore`.

```
GMAIL_SENDER=your_address@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
GMAIL_RECIPIENT=your_address@gmail.com
```

Generate a Gmail App Password at:
Google Account → Security → 2-Step Verification → App Passwords

---

## Completed Files

### `config.py` — COMPLETE

```python
# config.py
# Central settings file for the Pi Night Vision Motion Camera.
# All other modules import their settings from here — change a value
# once here and it takes effect everywhere.

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
GMAIL_SENDER    = os.getenv("GMAIL_SENDER")       # address the Pi sends from
GMAIL_PASSWORD  = os.getenv("GMAIL_APP_PASSWORD") # Gmail App Password (not your login password)
GMAIL_RECIPIENT = os.getenv("GMAIL_RECIPIENT")    # address the alert is sent to

# --- Camera ---
# RESOLUTION is a (width, height) tuple in pixels. 1920x1080 is full HD
# and well within the OV5647's capability.
# FPS is frames per second captured — 30 is standard for smooth video.
RESOLUTION  = (1920, 1080)
FPS         = 30

# --- Motion detection ---
# MOTION_THRESHOLD is the minimum contour area in pixels that counts as
# real motion. Anything smaller is ignored as noise (insects, compression
# artifacts, etc.). Raise this value if you get too many false triggers;
# lower it if real motion is being missed. 500 is a good starting point.
#
# MOTION_COOLDOWN_SEC is how many seconds must pass after motion is first
# detected before the detector can fire again. Prevents one continuous
# movement from triggering hundreds of events.
MOTION_THRESHOLD    = 500
MOTION_COOLDOWN_SEC = 10

# --- Recording ---
# POST_MOTION_BUFFER_SEC keeps the camera recording for this many seconds
# after motion stops. Without it, the clip would cut off the moment the
# subject leaves frame.
#
# CLIPS_DIR is the folder where video files are saved. This matches the
# clips/ directory in the project folder.
POST_MOTION_BUFFER_SEC = 5
CLIPS_DIR              = "clips"

# --- Notifications ---
# NOTIFICATION_COOLDOWN_SEC is the minimum gap between alert emails.
# This is separate from MOTION_COOLDOWN_SEC — motion can be detected
# every 10 seconds, but you only want one email per minute at most,
# even if motion is continuous.
NOTIFICATION_COOLDOWN_SEC = 60
```

---

### `storage.py` — COMPLETE

```python
# storage.py
# Handles all file system operations — generating timestamped filenames
# for video clips and snapshots, saving images to disk, and ensuring the
# clips folder exists before anything tries to write to it.

import os       # built-in: used to build file paths and create directories
import cv2      # OpenCV: used to encode and write image frames to disk as JPEG
from datetime import datetime  # built-in: used to generate timestamps for filenames
import config   # our settings file — provides CLIPS_DIR so the path isn't hardcoded here

os.makedirs(config.CLIPS_DIR, exist_ok=True)
# os.makedirs() creates the clips folder if it doesn't already exist.
# exist_ok=True prevents a crash if the folder is already there — it simply moves on.
# This runs once when the module is first imported, so the folder is always
# guaranteed to exist before any file-saving functions are called.

def get_video_path():
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    # gets current date and time and formats the string ie: 2026-06-20_21-30-00

    filename = f"motion_{timestamp}.mp4"
    # sets the name of the recording file

    return os.path.join(config.CLIPS_DIR, filename)

def get_snapshot_path():
    # Almost identical to get_video_path() — the only differences are the
    # prefix (snapshot_ instead of motion_) and the extension
    # (.jpg instead of .mp4).

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"snapshot_{timestamp}.jpg"
    return os.path.join(config.CLIPS_DIR, filename)

def save_snapshot(frame): # frame is a NumPy array

    path = get_snapshot_path()
    cv2.imwrite(path, frame)
    # cv2.imwrite() encodes that array as a JPEG and writes it to
    # disk at the given path
    return path
```

---

### `notifier.py` — COMPLETE

```python
# notifier.py

import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import config

_last_sent = 0
# module-level variable storing the timestamp of the last alert sent
# set to 0 so the first motion event always triggers immediately

def send_alert(snapshot_path):
    global _last_sent
    now = time.time()

    if now - _last_sent < config.NOTIFICATION_COOLDOWN_SEC:
        # not enough time has passed — exit quietly, no email sent
        return

    msg = MIMEMultipart()
    msg["From"]    = config.GMAIL_SENDER
    msg["To"]      = config.GMAIL_RECIPIENT
    msg["Subject"] = "Motion Detected!"

    body = "Motion was detected. See the attached snapshot."
    msg.attach(MIMEText(body, "plain"))

    with open(snapshot_path, "rb") as f:
        # open image in read binary mode — images are binary, not text
        attachment = MIMEBase("application", "octet-stream")
        attachment.set_payload(f.read())

    encoders.encode_base64(attachment)
    # converts binary image data to Base64 so it survives email transmission
    attachment.add_header("Content-Disposition", f"attachment; filename={snapshot_path}")
    msg.attach(attachment)

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.ehlo()       # required SMTP handshake
        server.starttls()   # upgrade to encrypted TLS before sending credentials
        server.login(config.GMAIL_SENDER, config.GMAIL_PASSWORD)
        server.sendmail(config.GMAIL_SENDER, config.GMAIL_RECIPIENT, msg.as_string())

    _last_sent = time.time()
    # record send time so cooldown starts counting
```

---

### `camera.py` — COMPLETE

```python
# camera.py

from picamera2 import Picamera2
#the main camera object
from picamera2.encoders import H264Encoder
#compresses video using the Pi's built-in hardware encoder (fast, low CPU)
from picamera2.outputs import FfmpegOutput
#wraps that compressed video in an .mp4 container so it's playable on any device
import config

_camera = Picamera2()
#creates the camera object

_camera.configure(
    #create_video_configuration() tells picamera2 we want video mode 
    # (as opposed to still photo mode), at the resolution from our config file
    # "format": "BGR888" is the key one — cameras naturally output RGB (Red-Green-Blue), 
    # but OpenCV expects BGR (Blue-Green-Red). By telling picamera2 to flip the channel order here, 
    # every frame is already in the right format and we never have to convert

    _camera.create_video_configuration(
        main={"size": config.RESOLUTION, "format": "BGR888"}
    )
)

_camera.start()
#This runs once when the module is first imported — same pattern as os.makedirs() 
# in storage.py. By the time main.py calls any of our functions, 
# the camera is already warmed up and ready.


def get_frame():
    #  capture_array() takes a snapshot from the live camera feed and 
    # returns it as a NumPy array — a grid of pixel values that OpenCV 
    # knows how to work with. This is what the main loop will call on 
    # every single iteration to get a fresh frame for motion detection. 
    # It's fast because the camera is already running — we're just 
    # grabbing whatever it's currently seeing.

    return _camera.capture_array()


def start_recording(filepath):
    #H264Encoder() — H264 is a video compression format. 
    # The Pi 4 has a dedicated hardware chip for this, so it compresses 
    # video without eating your CPU. We create a fresh encoder each time a new clip starts.
    # FfmpegOutput(filepath) — takes the compressed H264 data and writes it 
    # into an .mp4 file at the path we pass in. ffmpeg is a standard tool already 
    # on the Pi that handles the container format.
    _camera.start_recording(H264Encoder(), FfmpegOutput(filepath))


def stop_recording():
    #tells picamera2 to finish writing the video file and shut down the encoder. 
    # The camera itself keeps running, so we can keep calling get_frame() after a clip ends.
    _camera.stop_recording()


def close():
    # fully shuts down the camera. This will be called in main.py 
    # when the user hits Ctrl+C, so the hardware is released cleanly 
    # instead of just dying mid-frame.
    _camera.stop()
```

---

### `motion_detector.py` — COMPLETE

```python
# motion_detector.py
import cv2
import time
import config

_bg_subtractor = cv2.createBackgroundSubtractorMOG2(detectShadows=False)
_last_motion = 0

#Two module-level variables, same pattern as _camera in camera.py.

#_bg_subtractor — MOG2 stands for "Mixture of Gaussians 2". It works by 
# watching many frames over time and building a statistical model of 
# what the "background" looks like. When a new frame comes in, 
# anything that doesn't match that model gets painted white in a mask 
# — that's your moving object. detectShadows=False tells it 
# not to bother classifying shadows separately, which saves 
# CPU and keeps the mask simpler.

#_last_motion — stores the timestamp of the last time motion was detected. 
# Set to 0 so the very first motion event always triggers immediately 
# (same trick we used with _last_sent in notifier.py).

def detect(frame):
    global _last_motion
    # tells Python we want to modify the module-level variable, not create a new 
    # local one (same pattern as global _last_sent in notifier.py)

    fg_mask = _bg_subtractor.apply(frame)

#apply() is where the MOG2 magic happens. You hand it a frame, it compares 
# it against its background model, and returns a foreground mask 
# — a black-and-white image the same size as your frame where:

# White pixels = something moved here
# Black pixels = background, nothing changed
#The mask is noisy at this point — there'll be speckles and small blobs 
# from things like a leaf moving or a camera artifact. The next step is 
# where we filter those out.

    contours, _ = cv2.findContours(fg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    #fg_mask — the black-and-white image we just made
    # cv2.RETR_EXTERNAL — only return the outermost outline of each blob, ignore any holes inside
    # cv2.CHAIN_APPROX_SIMPLE — compress the outline down to just its corner points instead 
    # of storing every single pixel on the edge (saves memory, still accurate enough)

    motion_detected = False

    for contour in contours:
        #  start by assuming no motion. Then we loop through every contour and measure its area in pixels. 
        # If any single contour is larger than MOTION_THRESHOLD (which we set to 500 in config.py), 
        # something real moved — we set the flag and break out of the loop immediately 
        # since we don't need to check the rest.
        # This is the noise filter. A speck of dust or a compression artifact might produce a 
        # contour of 10–20 pixels. A person walking through frame will produce a contour of thousands of pixels. 
        # The threshold sits in between.

        if cv2.contourArea(contour) > config.MOTION_THRESHOLD:
            motion_detected = True
            break

    now = time.time()
    # how many seconds have passed since the last confirmed motion event

    if motion_detected and (now - _last_motion) > config.MOTION_COOLDOWN_SEC:
        # The if only returns True when motion was detected and enough time has passed. 
        # If motion is detected but we're still in cooldown, it falls through to return False, frame 
        # — silently ignored.
       
        _last_motion = now
        return True, frame
        # We always return the frame either way so main.py can use it regardless

    return False, frame
```

---

## Remaining Modules (not started)

### `main.py`
- Initialize all modules
- Main loop: capture → detect → record → notify
- Graceful shutdown on Ctrl+C

---

## Build Order (for reference)

1. ~~`config.py`~~ — DONE
2. ~~`storage.py`~~ — DONE
3. ~~`notifier.py`~~ — DONE
4. ~~`camera.py`~~ — DONE
5. ~~`motion_detector.py`~~ — DONE
6. `main.py` — not started

---

## Pi Hardware Setup Checklist

- [ ] Enable camera: `sudo raspi-config` → Interface Options → Camera
- [ ] Update system: `sudo apt update && sudo apt upgrade`
- [ ] Install dependencies: `pip install picamera2 opencv-python-headless python-dotenv`
- [ ] Fill in `.env` with Gmail credentials
- [ ] Test camera is detected: `libcamera-hello`
