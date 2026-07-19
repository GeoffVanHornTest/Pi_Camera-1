# PI Camera

A Raspberry Pi night vision motion camera. Detects motion using OpenCV MOG2 background subtraction, records H264 video with pre-roll, and sends a Telegram alert with a snapshot and a Dropbox share link when a clip is ready.

## Hardware

- Raspberry Pi 4
- Arducam 5MP OV5647 Camera Module with IR LED (CSI interface)

## Prerequisites

```bash
# System packages — must be installed via apt, not pip
sudo apt install python3-picamera2 ffmpeg

# Python tooling
pip install uv
```

## Setup

```bash
git clone https://github.com/GeoffVanHornTest/Pi_Camera-1.git
cd Pi_Camera-1

# Create venv with access to system-installed picamera2
uv venv --system-site-packages
uv sync --dev

# Copy the credentials template and fill in your values
cp .env.example .env   # then edit .env with your credentials
```

### `.env` file

Create `.env` at the repo root (the directory you cloned into) with the following keys:

```
TELEGRAM_BOT_TOKEN=your_bot_token_from_BotFather
TELEGRAM_CHAT_ID=your_numeric_chat_id
DROPBOX_APP_KEY=your_app_key
DROPBOX_APP_SECRET=your_app_secret
DROPBOX_REFRESH_TOKEN=your_refresh_token
```

**Telegram:** message @BotFather → `/newbot` → copy the token. Then message your bot and call `https://api.telegram.org/bot<TOKEN>/getUpdates` to find the chat ID.

**Dropbox:** create an app at dropbox.com/developers (Scoped access, Full Dropbox), copy the App Key and Secret, then run the OAuth flow described in `PROGRESS.md`.

## Running

```bash
# Run directly
uv run python 02-scripts/main.py

# Stop-after-N-clips field test
bash 02-scripts/run_test.sh 20
```

## Development

```bash
uv run pytest -v          # run tests
uv run ruff check .       # lint
uv run ruff format .      # format
uv run mkdocs serve       # preview docs at http://127.0.0.1:8000
uv run mkdocs gh-deploy   # deploy docs to GitHub Pages
```

## Documentation

Full documentation — detection pipeline, clip timing, API reference, and analysis scripts — is published at **https://GeoffVanHornTest.github.io/Pi_Camera-1/**.

## Project layout

```
02-scripts/      Main camera scripts (main.py, camera.py, motion_detector.py, …)
03-tests/        pytest unit tests
04-docs/         MkDocs source (deployed to GitHub Pages)
00-clips/        Recorded clips and snapshots (gitignored)
01-reqs/         pip fallback requirements.txt
pi-camera.service  systemd unit for auto-start
```

See `CHANGELOG.md` for release history and `PROGRESS.md` for current project state.