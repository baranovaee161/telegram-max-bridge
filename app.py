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
    return "Telegram ↔ MAX bridge is running"


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/setup-max")
def setup_max():
    if not MAX_TOKEN:
        return jsonify({
            "ok": False,
            "error": "MAX_TOKEN is not set"
        }), 500

    url = "https://platform-api2.max.ru/subscriptions"

    headers = {
        "Authorization": MAX_TOKEN,
        "Content-Type": "application/json"
    }

    payload = {
        "url": "https://telegram-max-bridge.onrender.com/max/webhook",
        "update_types": [
            "message_created",
            "bot_added",
            "bot_started"
        ],
        "secret": MAX_WEBHOOK_SECRET
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=20,
            verify=MAX_CA_BUNDLE
        )

        logging.info(
            "MAX SUBSCRIPTION RESPONSE: %s",
            response.text
        )

        try:
            response_data = response.json()
        except Exception:
            response_data = response.text

        return jsonify({
            "ok": response.ok,
            "status_code": response.status_code,
            "response": response_data
        })

    except requests.exceptions.RequestException as e:
        logging.exception("MAX SUBSCRIPTION ERROR")

        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500


def get_telegram_sender_name(message):
    sender = message.get("from", {})

    if not isinstance(sender, dict):
        sender = {}

    username = sender.get("username")
    first_name = sender.get("first_name", "")
    last_name = sender.get("last_name", "")

    if username:
        return "@" + username

    sender_name = " ".join(
        part for part in [first_name, last_name]
        if part
    )

    if sender_name:
        return sender_name

    return "Пользователь"


def send_text_to_max(text, sender_name):
    if not MAX_TOKEN or not MAX_CHAT_ID:
        logging.error(
            "MAX TEXT NOT SENT: MAX_TOKEN or MAX_CHAT_ID is missing"
        )
        return

    url = (
        "https://platform-api2.max.ru/messages"
        f"?chat_id={int(MAX_CHAT_ID)}"
    )

    headers = {
        "Authorization": MAX_TOKEN,
        "Content-Type": "application/json"
    }

    payload = {
        "text": (
            "Telegram → MAX\n"
            f"👤 {sender_name}\n"
            f"{text}"
        )
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=20,
            verify=MAX_CA_BUNDLE
        )

        logging.info(
            "MAX TEXT RESPONSE: %s",
            response.text
        )

    except requests.exceptions.RequestException:
        logging.exception("MAX TEXT MESSAGE ERROR")


def send_photo_to_max(
    file_bytes,
    file_name,
    content_type,
    caption,
    sender_name
):
    if not MAX_TOKEN or not MAX_CHAT_ID:
        logging.error(
            "MAX PHOTO NOT SENT: MAX_TOKEN or MAX_CHAT_ID is missing"
        )
        return

    logging.info(
        "STARTING MAX PHOTO UPLOAD: %s bytes",
        len(file_bytes)
    )

    upload_url = "https://platform-api2.max.ru/uploads?type=image"

    upload_headers = {
        "Authorization": MAX_TOKEN
    }

    try:
        init_response = requests.post(
            upload_url,
            headers=upload_headers,
            timeout=20,
            verify=MAX_CA_BUNDLE
        )

        logging.info(
            "MAX UPLOAD INIT STATUS: %s",
            init_response.status_code
        )

        logging.info(
            "MAX UPLOAD INIT RESPONSE: %s",
            init_response.text
        )

        if not init_response.ok:
            logging.error("MAX UPLOAD INIT FAILED")
            return

        init_data = init_response.json()

        upload_target = init_data.get("url")

        if not upload_target:
            logging.error(
                "MAX UPLOAD URL NOT FOUND: %s",
                init_data
            )
            return

        files = {
            "data": (
                file_name,
                file_bytes,
                content_type
            )
        }

        upload_response = requests.post(
            upload_target,
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
            logging.error("MAX PHOTO UPLOAD FAILED")
            return

        upload_data = upload_response.json()

        token = upload_data.get("token")

        if not token:
            token = init_data.get("token")

        if not token:
            logging.error(
                "MAX PHOTO TOKEN NOT FOUND: %s",
                upload_data
            )
            return

        message_url = (
            "https://platform-api2.max.ru/messages"
            f"?chat_id={int(MAX_CHAT_ID)}"
        )

        message_headers = {
            "Authorization": MAX_TOKEN,
            "Content-Type": "application/json"
        }

        message_text = (
            "Telegram → MAX\n"
            f"👤 {sender_name}"
        )

        if caption:
            message_text += f"\n{caption}"

        message_payload = {
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

        message_response = requests.post(
            message_url,
            headers=message_headers,
            json=message_payload,
            timeout=30,
            verify=MAX_CA_BUNDLE
        )

        logging.info(
            "MAX PHOTO MESSAGE STATUS: %s",
            message_response.status_code
        )

        logging.info(
            "MAX PHOTO MESSAGE RESPONSE: %s",
            message_response.text
        )

    except Exception:
        logging.exception("MAX PHOTO ERROR")


@app.route("/telegram/webhook", methods=["POST"])
def telegram_webhook():
    data = request.get_json(silent=True) or {}

    logging.info(
        "TELEGRAM UPDATE: %s",
        data
    )

    message = data.get("message", {})

    if not isinstance(message, dict):
        message = {}

    sender_name = get_telegram_sender_name(message)

    # Обычное текстовое сообщение
    text = message.get("text")

    if text:
        send_text_to_max(
            text,
            sender_name
        )

    # Фотография
    photos = message.get("photo")

    if isinstance(photos, list) and photos:
        biggest_photo = photos[-1]

        file_id = biggest_photo.get("file_id")

        logging.info(
            "TELEGRAM PHOTO FILE ID: %s",
            file_id
        )

        if file_id and TELEGRAM_TOKEN:
            try:
                # Получаем информацию о файле Telegram
                file_info_url = (
                    f"https://api.telegram.org/bot"
                    f"{TELEGRAM_TOKEN}/getFile"
                )

                file_info_response = requests.get(
                    file_info_url,
                    params={"file_id": file_id},
                    timeout=20
                )

                logging.info(
                    "TELEGRAM FILE INFO RESPONSE: %s",
                    file_info_response.text
                )

                if file_info_response.ok:
                    file_info = file_info_response.json()

                    file_path = (
                        file_info
                        .get("result", {})
                        .get("file_path")
                    )

                    if file_path:
                        # Скачиваем фотографию из Telegram
                        download_url = (
                            "https://api.telegram.org/file/bot"
                            f"{TELEGRAM_TOKEN}/{file_path}"
                        )

                        photo_response = requests.get(
                            download_url,
                            timeout=60
                        )

                        logging.info(
                            "TELEGRAM PHOTO DOWNLOAD STATUS: %s",
                            photo_response.status_code
                        )

                        if photo_response.ok:
                            send_photo_to_max(
                                file_bytes=photo_response.content,
                                file_name="telegram_photo.jpg",
                                content_type=photo_response.headers.get(
                                    "Content-Type",
                                    "image/jpeg"
                                ),
                                caption=message.get(
                                    "caption",
                                    ""
                                ),
                                sender_name=sender_name
                            )
                        else:
                            logging.error(
                                "TELEGRAM PHOTO DOWNLOAD FAILED: %s",
                                photo_response.text
                            )
                    else:
                        logging.error(
                            "TELEGRAM FILE PATH NOT FOUND"
                        )

            except requests.exceptions.RequestException:
                logging.exception(
                    "TELEGRAM PHOTO REQUEST ERROR"
                )

            except Exception:
                logging.exception(
                    "TELEGRAM PHOTO PROCESSING ERROR"
                )

    return jsonify({"ok": True})


@app.route("/max/webhook", methods=["POST"])
def max_webhook():
    if MAX_WEBHOOK_SECRET:
        received_secret = request.headers.get(
            "X-Max-Bot-Api-Secret"
        )

        if received_secret != MAX_WEBHOOK_SECRET:
            logging.warning(
                "Invalid MAX webhook secret"
            )

            return jsonify({
                "ok": False
            }), 401

    data = request.get_json(silent=True) or {}

    logging.info(
        "MAX UPDATE: %s",
        data
    )

    update_type = data.get("update_type")

    if update_type == "bot_added":
        chat_id = data.get("chat_id")

        logging.info(
            "MAX CHAT ID: %s",
            chat_id
        )

    message = data.get("message", {})

    if not isinstance(message, dict):
        message = {}

    body = message.get("body", {})

    if not isinstance(body, dict):
        body = {}

    text = body.get("text")

    sender = message.get("sender", {})

    if not isinstance(sender, dict):
        sender = {}

    username = sender.get("username")
    first_name = sender.get("first_name", "")
    last_name = sender.get("last_name", "")
    name = sender.get("name", "")

    if username:
        sender_name = "@" + username

    elif name:
        sender_name = name

    else:
        sender_name = " ".join(
            part for part in [first_name, last_name]
            if part
        )

    if not sender_name:
        sender_name = "Пользователь"

    if text and TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        url = (
            f"https://api.telegram.org/bot"
            f"{TELEGRAM_TOKEN}/sendMessage"
        )

        telegram_text = (
            "MAX → Telegram\n"
            f"👤 {sender_name}\n"
            f"{text}"
        )

        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": telegram_text
        }

        try:
            response = requests.post(
                url,
                json=payload,
                timeout=20
            )

            logging.info(
                "TELEGRAM RESPONSE: %s",
                response.text
            )

        except requests.exceptions.RequestException:
            logging.exception(
                "TELEGRAM MESSAGE ERROR"
            )

    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
