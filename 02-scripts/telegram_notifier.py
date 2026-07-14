"""Telegram notification sender for the PI Camera system.

Sends snapshot photos and text messages to a Telegram chat via the Bot API.
No cooldown is applied here — gate alerts upstream with motion_detector.new_event_allowed().
"""

import config
import requests


def send_photo(image_path, caption="Motion detected!"):
    """Send a JPEG image to the configured Telegram chat.

    Args:
        image_path: Path to the .jpg file to send.
        caption: Text shown below the photo. Defaults to "Motion detected!".
    """
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendPhoto"
    try:
        with open(image_path, "rb") as f:
            requests.post(
                url,
                data={"chat_id": config.TELEGRAM_CHAT_ID, "caption": caption},
                files={"photo": f},
                timeout=15,
            )
    except Exception as e:
        print(f"[telegram] send_photo failed: {e}")


def send_message(text):
    """Send a plain text message to the configured Telegram chat.

    Args:
        text: The message to send.
    """
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(
            url,
            data={"chat_id": config.TELEGRAM_CHAT_ID, "text": text},
            timeout=15,
        )
    except Exception as e:
        print(f"[telegram] send_message failed: {e}")
