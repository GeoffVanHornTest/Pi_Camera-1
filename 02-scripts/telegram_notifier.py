"""Telegram notification sender for the PI Camera system.

Sends snapshot photos and text messages to a Telegram chat via the Bot API.
send_photo() enforces NOTIFICATION_COOLDOWN_SEC between alerts so that rapid
re-triggers don't flood the chat. send_message() (clip-ready links) always sends.
"""

import time

import config
import requests

_last_photo_sent = 0.0


def _safe_err(exc):
    """Return exc's string representation with the bot token redacted."""
    token = config.TELEGRAM_BOT_TOKEN or ""
    msg = str(exc)
    return msg.replace(token, "***") if token else msg


def send_photo(image_path, caption="Motion detected!"):
    """Send a JPEG image to the configured Telegram chat.

    Skipped silently if called within NOTIFICATION_COOLDOWN_SEC of the last
    successful send, so rapid re-triggers don't flood the chat.

    Args:
        image_path: Path to the .jpg file to send.
        caption: Text shown below the photo. Defaults to "Motion detected!".
    """
    global _last_photo_sent
    if time.time() - _last_photo_sent < config.NOTIFICATION_COOLDOWN_SEC:
        print("[telegram] send_photo suppressed — within cooldown window")
        return
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendPhoto"
    try:
        with open(image_path, "rb") as f:
            resp = requests.post(
                url,
                data={"chat_id": config.TELEGRAM_CHAT_ID, "caption": caption},
                files={"photo": f},
                timeout=15,
            )
        body = resp.json()
        if body.get("ok"):
            _last_photo_sent = time.time()
        else:
            print(f"[telegram] send_photo API error: {body.get('description', body)}")
    except Exception as e:
        print(f"[telegram] send_photo failed: {_safe_err(e)}")


def send_message(text):
    """Send a plain text message to the configured Telegram chat.

    Args:
        text: The message to send.
    """
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(
            url,
            data={"chat_id": config.TELEGRAM_CHAT_ID, "text": text},
            timeout=15,
        )
        body = resp.json()
        if not body.get("ok"):
            print(f"[telegram] send_message API error: {body.get('description', body)}")
    except Exception as e:
        print(f"[telegram] send_message failed: {_safe_err(e)}")
