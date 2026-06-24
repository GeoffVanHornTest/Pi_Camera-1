# Pi Night Vision Motion Camera — Project Plan

## Hardware

- Raspberry Pi 4
- Arducam 5MP OV5647 Camera Module with IR LED (CSI interface)

---

## Tech Stack

| Purpose           | Tool / Library     | Notes                                          |
|-------------------|--------------------|------------------------------------------------|
| Camera            | `picamera2`        | Modern Pi camera library                       |
| Motion detection  | `opencv-python`    | Background subtraction via MOG2 algorithm      |
| Notifications     | `smtplib`          | Python standard library — no install needed    |
| Email formatting  | `email` (stdlib)   | Build MIME emails with image attachments       |
| Config / secrets  | `python-dotenv`    | Keeps credentials out of source code           |

---

## Notification Approach

**Gmail via SMTP** — The Pi sends an email to your Gmail address with a snapshot
image attached. The Gmail app on your phone delivers it as a push notification.

- Uses Python's built-in `smtplib` — no extra packages required on the Pi
- Requires a Gmail **App Password** (not your regular password)
  - Google Account → Security → 2-Step Verification → App Passwords
- No carrier SMS gateway needed

---

## Project Structure

```
pi_camera/
├── main.py              # Entry point — initializes modules and runs the main loop
├── config.py            # All settings and constants in one place
├── camera.py            # Camera setup, frame capture, video recording
├── motion_detector.py   # Motion detection logic (OpenCV MOG2)
├── notifier.py          # Sends Gmail alert with snapshot attachment
├── storage.py           # Timestamped filenames, clip/disk management
├── .env                 # Secrets — never commit this file
├── .gitignore           # Excludes .env and video clips from version control
└── requirements.txt     # Third-party dependencies
```

---

## Module Responsibilities

### `config.py`
- Loads values from `.env` using `python-dotenv`
- Defines all tunable constants:
  - Camera resolution and FPS
  - Motion sensitivity threshold (contour area in pixels)
  - Minimum seconds between notifications (rate limiting)
  - Post-motion recording buffer (seconds to keep recording after motion stops)
  - Video storage folder path
  - Gmail sender address, App Password, recipient address

### `camera.py`
- Initializes `picamera2`
- `get_frame()` — captures a single frame as a NumPy array for motion analysis
- `start_recording(filepath)` — begins saving video to disk
- `stop_recording()` — ends the recording
- IR LEDs on the OV5647 module operate automatically in low light

### `motion_detector.py`
- Creates an OpenCV `MOG2` background subtractor on init
  - MOG2 adapts to gradual lighting changes (better than simple frame differencing for night scenes)
- `detect(frame)` — returns `(motion_detected: bool, frame_with_overlay)`
- Internal cooldown timer prevents triggering more than once per N seconds
- Sensitivity controlled by a minimum contour area threshold from `config.py`

### `storage.py`
- `get_video_path()` — returns a timestamped filepath, e.g. `clips/motion_2026-06-20_21-30-00.mp4`
- `get_snapshot_path()` — same pattern for `.jpg` snapshots
- `save_snapshot(frame)` — writes a single frame to disk as JPEG
- Optional: `cleanup_old_clips(days)` — deletes clips older than N days

### `notifier.py`
- `send_alert(snapshot_path)` — builds a MIME email with the snapshot attached and sends via Gmail SMTP
- Internal timestamp check prevents sending more than one alert per configured interval
- SMTP connection details:
  - Host: `smtp.gmail.com`
  - Port: `587`
  - Auth: Gmail address + App Password from `.env`

### `main.py`
- Initializes all modules
- Runs the main loop:
  ```
  while True:
      frame = camera.get_frame()
      motion, annotated_frame = motion_detector.detect(frame)

      if motion and not currently_recording:
          filepath = storage.get_video_path()
          camera.start_recording(filepath)
          snapshot = storage.save_snapshot(frame)
          notifier.send_alert(snapshot)

      if not motion and currently_recording:
          wait for post-motion buffer
          camera.stop_recording()
  ```
- Handles `KeyboardInterrupt` (Ctrl+C) gracefully — stops recording and releases camera

---

## `.env` File Template

```
GMAIL_SENDER=your_address@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
GMAIL_RECIPIENT=your_address@gmail.com
```

> Generate an App Password at: Google Account → Security → 2-Step Verification → App Passwords

---

## Build Order

Work through modules in this order so each piece can be tested before the next depends on it:

1. **`config.py`** — No dependencies. Set up all constants and `.env` loading.
2. **`camera.py`** — Get a live frame on screen. Confirm the camera is wired and working.
3. **`motion_detector.py`** — Pass frames in, print `"Motion detected!"` to the console.
4. **`storage.py`** — Save a test clip and snapshot. Confirm files appear on disk.
5. **`notifier.py`** — Send a test email to yourself with a dummy image attached.
6. **`main.py`** — Wire all modules together into the full working system.

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

> Use `opencv-python-headless` instead of `opencv-python` — the Pi doesn't need
> the GUI display components, and headless is lighter.

---

## Pi Setup Checklist

- [ ] Enable camera interface: `sudo raspi-config` → Interface Options → Camera
- [ ] Update the system: `sudo apt update && sudo apt upgrade`
- [ ] Install pip dependencies (see above)
- [ ] Create `.env` file with Gmail credentials
- [ ] Create `clips/` directory for video output
- [ ] Test camera is detected: `libcamera-hello`

---

## Future Enhancements (out of scope for now)

- Web dashboard to view clips remotely
- Upload clips to Google Drive
- Schedule active hours (e.g., only monitor 10pm–6am)
- Telegram bot for richer notifications (send video clips, not just snapshots)
