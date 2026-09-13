import os
import logging
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
MAX_TOKEN = os.getenv("MAX_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
MAX_CHAT_ID = os.getenv("MAX_CHAT_ID") or "-78865734747587"
MAX_WEBHOOK_SECRET = os.getenv("MAX_WEBHOOK_SECRET")
MAX_CA_BUNDLE = "/etc/secrets/max_ca_bundle.pem"


@app.route("/")
def home():
    return "Telegram MAX bridge is running"


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


def get_telegram_sender_name(message):
    sender = message.get("from", {})

    if not isinstance(sender, dict):
        sender = {}

    username = sender.get("username")
    first_name = sender.get("first_name", "")
    last_name = sender.get("last_name", "")

    if username:
        return "@" + username

    name = " ".join(
        x for x in [first_name, last_name]
        if x
    )

    if name:
        return name

    return "Пользователь"


def get_max_sender_name(sender):
    if not isinstance(sender, dict):
        return "Пользователь"

    username = sender.get("username")
    name = sender.get("name")
    first_name = sender.get("first_name", "")
    last_name = sender.get("last_name", "")

    if username:
        return "@" + username

    if name:
        return name

    full_name = " ".join(
        x for x in [first_name, last_name]
        if x
    )

    if full_name:
        return full_name

    return "Пользователь"


def max_headers():
    return {
        "Authorization": MAX_TOKEN,
        "Content-Type": "application/json"
    }


def send_text_to_max(text, sender_name):
    if not MAX_TOKEN or not MAX_CHAT_ID:
        logging.error(
            "MAX TEXT NOT SENT: missing credentials"
        )
        return

    url = (
        "https://platform-api2.max.ru/messages"
        "?chat_id=" + str(int(MAX_CHAT_ID))
    )

    payload = {
        "text": (
            "Telegram -> MAX\n"
            "👤 " + sender_name + "\n"
            + text
        )
    }

    try:
        response = requests.post(
            url,
            headers=max_headers(),
            json=payload,
            timeout=30,
            verify=MAX_CA_BUNDLE
        )

        logging.info(
            "MAX TEXT RESPONSE: %s",
            response.text
        )

    except Exception:
        logging.exception(
            "MAX TEXT ERROR"
        )


def get_max_photo_token(data):
    if not isinstance(data, dict):
        return None

    photos = data.get("photos")

    if isinstance(photos, dict):
        for photo_id in photos:
            photo_data = photos.get(photo_id)

            if isinstance(photo_data, dict):
                token = photo_data.get("token")

                if token:
                    logging.info(
                        "MAX PHOTO TOKEN FOUND"
                    )
                    return token

    token = data.get("token")

    if token:
        return token

    return None


def send_photo_to_max(
    file_bytes,
    content_type,
    caption,
    sender_name
):
    if not MAX_TOKEN or not MAX_CHAT_ID:
        logging.error(
            "MAX PHOTO NOT SENT: missing credentials"
        )
        return

    logging.info(
        "STARTING MAX PHOTO UPLOAD: %s bytes",
        len(file_bytes)
    )

    upload_url = (
        "https://platform-api2.max.ru/uploads"
        "?type=image"
    )

    try:
        init_response = requests.post(
            upload_url,
            headers={
                "Authorization": MAX_TOKEN
            },
            timeout=30,
            verify=MAX_CA_BUNDLE
        )

        logging.info(
            "MAX PHOTO INIT STATUS: %s",
            init_response.status_code
        )

        logging.info(
            "MAX PHOTO INIT RESPONSE: %s",
            init_response.text
        )

        if not init_response.ok:
            logging.error(
                "MAX PHOTO INIT FAILED"
            )
            return

        try:
            init_data = init_response.json()
        except Exception:
            logging.error(
                "MAX PHOTO INIT RESPONSE IS NOT JSON: %s",
                init_response.text
            )
            return

        upload_url_2 = init_data.get("url")

        if not upload_url_2:
            logging.error(
                "MAX PHOTO UPLOAD URL NOT FOUND"
            )
            return

        files = {
            "data": (
                "telegram_photo.jpg",
                file_bytes,
                content_type or "image/jpeg"
            )
        }

        upload_response = requests.post(
            upload_url_2,
            files=files,
            timeout=60
        )

        logging.info(
            "MAX PHOTO UPLOAD STATUS: %s",
            upload_response.status_code
        )

        logging.info(
            "MAX PHOTO UPLOAD RESPONSE: %s",
            upload_response.text
        )

        if not upload_response.ok:
            logging.error(
                "MAX PHOTO UPLOAD FAILED"
            )
            return

        try:
            upload_data = upload_response.json()
        except Exception:
            logging.error(
                "MAX PHOTO UPLOAD RESPONSE IS NOT JSON: %s",
                upload_response.text
            )
            return

        token = get_max_photo_token(upload_data)

        if not token:
            logging.error(
                "MAX PHOTO TOKEN NOT FOUND: %s",
                upload_data
            )
            return

        message_url = (
            "https://platform-api2.max.ru/messages"
            "?chat_id=" + str(int(MAX_CHAT_ID))
        )

        message_text = (
            "Telegram -> MAX\n"
            "👤 " + sender_name
        )

        if caption:
            message_text += "\n" + caption

        payload = {
            "text": message_text,
            "attachments": [
                {
                    "type": "image",
                    "payload": {
                        "token": token
                    }
                }
            ]
        }

        response = requests.post(
            message_url,
            headers=max_headers(),
            json=payload,
            timeout=30,
            verify=MAX_CA_BUNDLE
        )

        logging.info(
            "MAX PHOTO MESSAGE STATUS: %s",
            response.status_code
        )

        logging.info(
            "MAX PHOTO MESSAGE RESPONSE: %s",
            response.text
        )

    except Exception:
        logging.exception(
            "MAX PHOTO ERROR"
        )


def send_audio_to_max(
    file_bytes,
    content_type,
    sender_name
):
    if not MAX_TOKEN or not MAX_CHAT_ID:
        logging.error(
            "MAX AUDIO NOT SENT: missing credentials"
        )
        return

    logging.info(
        "STARTING MAX AUDIO UPLOAD: %s bytes",
        len(file_bytes)
    )

    logging.info(
        "TELEGRAM AUDIO CONTENT TYPE: %s",
        content_type
    )

    upload_url = (
        "https://platform-api2.max.ru/uploads"
        "?type=audio"
    )

    try:
        init_response = requests.post(
            upload_url,
            headers={
                "Authorization": MAX_TOKEN
            },
            timeout=30,
            verify=MAX_CA_BUNDLE
        )

        logging.info(
            "MAX AUDIO INIT STATUS: %s",
            init_response.status_code
        )

        logging.info(
            "MAX AUDIO INIT RESPONSE: %s",
            init_response.text
        )

        if not init_response.ok:
            logging.error(
                "MAX AUDIO INIT FAILED: status=%s body=%s",
                init_response.status_code,
                init_response.text
            )
            return

        try:
            init_data = init_response.json()
        except Exception:
            logging.error(
                "MAX AUDIO INIT RESPONSE IS NOT JSON: %s",
                init_response.text
            )
            return

        upload_url_2 = init_data.get("url")
        token = init_data.get("token")

        if not upload_url_2:
            logging.error(
                "MAX AUDIO UPLOAD URL NOT FOUND: %s",
                init_data
            )
            return

        if not token:
            logging.error(
                "MAX AUDIO TOKEN NOT FOUND IN INIT RESPONSE: %s",
                init_data
            )
            return

        logging.info(
            "MAX AUDIO TOKEN RECEIVED FROM INIT"
        )

        files = {
            "data": (
                "telegram_voice.ogg",
                file_bytes,
                content_type or "audio/ogg"
            )
        }

        upload_response = requests.post(
            upload_url_2,
            files=files,
            timeout=60
        )

        logging.info(
            "MAX AUDIO UPLOAD STATUS: %s",
            upload_response.status_code
        )

        logging.info(
            "MAX AUDIO UPLOAD RESPONSE: %s",
            upload_response.text
        )

        if not upload_response.ok:
            logging.error(
                "MAX AUDIO UPLOAD FAILED: status=%s body=%s",
                upload_response.status_code,
                upload_response.text
            )
            return

        logging.info(
            "MAX AUDIO FILE UPLOAD COMPLETED"
        )

        message_url = (
            "https://platform-api2.max.ru/messages"
            "?chat_id=" + str(int(MAX_CHAT_ID))
        )

        payload = {
            "text": (
                "Telegram -> MAX\n"
                "👤 " + sender_name
            ),
            "attachments": [
                {
                    "type": "audio",
                    "payload": {
                        "token": token
                    }
                }
            ]
        }

        logging.info(
            "SENDING MAX AUDIO MESSAGE"
        )

        response = requests.post(
            message_url,
            headers=max_headers(),
            json=payload,
            timeout=30,
            verify=MAX_CA_BUNDLE
        )

        logging.info(
            "MAX AUDIO MESSAGE STATUS: %s",
            response.status_code
        )

        logging.info(
            "MAX AUDIO MESSAGE RESPONSE: %s",
            response.text
        )

    except Exception:
        logging.exception(
            "MAX AUDIO ERROR"
        )


def download_telegram_file(file_id):
    if not TELEGRAM_TOKEN:
        logging.error(
            "TELEGRAM TOKEN IS MISSING"
        )
        return None, None

    get_file_url = (
        "https://api.telegram.org/bot"
        + TELEGRAM_TOKEN
        + "/getFile"
    )

    try:
        response = requests.get(
            get_file_url,
            params={
                "file_id": file_id
            },
            timeout=30
        )

        logging.info(
            "TE
