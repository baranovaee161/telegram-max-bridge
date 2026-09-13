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
        logging.error("MAX TEXT NOT SENT: missing credentials")
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
        logging.exception("MAX TEXT ERROR")


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
                    logging.info("MAX PHOTO TOKEN FOUND")
                    return token

    token = data.get("token")

    if token:
        return token

    return None


def get_upload_token(data):
    if not isinstance(data, dict):
        return None

    token = data.get("token")

    if token:
        return token

    audio = data.get("audio")

    if isinstance(audio, dict):
        token = audio.get("token")

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

        if not upload_url_2:
            logging.error(
                "MAX AUDIO UPLOAD URL NOT FOUND: %s",
                init_data
            )
            return

        logging.info(
            "MAX AUDIO UPLOAD URL RECEIVED"
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

        try:
            upload_data = upload_response.json()
        except Exception:
            logging.error(
                "MAX AUDIO UPLOAD RESPONSE IS NOT JSON."
            )

            logging.error(
                "MAX AUDIO RAW RESPONSE: %s",
                upload_response.text
            )

            logging.error(
                "MAX AUDIO RESPONSE HEADERS: %s",
                dict(upload_response.headers)
            )

            return

        logging.info(
            "MAX AUDIO PARSED RESPONSE: %s",
            upload_data
        )

        token = get_upload_token(upload_data)

        if not token:
            logging.error(
                "MAX AUDIO TOKEN NOT FOUND: %s",
                upload_data
            )
            return

        logging.info(
            "MAX AUDIO TOKEN FOUND"
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
            "TELEGRAM GET FILE RESPONSE: %s",
            response.text
        )

        if not response.ok:
            return None, None

        data = response.json()

        file_path = (
            data
            .get("result", {})
            .get("file_path")
        )

        if not file_path:
            logging.error(
                "TELEGRAM FILE PATH NOT FOUND"
            )
            return None, None

        download_url = (
            "https://api.telegram.org/file/bot"
            + TELEGRAM_TOKEN
            + "/"
            + file_path
        )

        file_response = requests.get(
            download_url,
            timeout=60
        )

        logging.info(
            "TELEGRAM FILE DOWNLOAD STATUS: %s",
            file_response.status_code
        )

        if not file_response.ok:
            logging.error(
                "TELEGRAM FILE DOWNLOAD FAILED: %s",
                file_response.text
            )
            return None, None

        content_type = file_response.headers.get(
            "Content-Type",
            "application/octet-stream"
        )

        logging.info(
            "TELEGRAM FILE CONTENT TYPE: %s",
            content_type
        )

        logging.info(
            "TELEGRAM FILE SIZE: %s bytes",
            len(file_response.content)
        )

        return (
            file_response.content,
            content_type
        )

    except Exception:
        logging.exception(
            "TELEGRAM FILE DOWNLOAD ERROR"
        )
        return None, None


@app.route(
    "/telegram/webhook",
    methods=["POST"]
)
def telegram_webhook():
    data = request.get_json(
        silent=True
    ) or {}

    logging.info(
        "TELEGRAM UPDATE: %s",
        data
    )

    message = data.get(
        "message",
        {}
    )

    if not isinstance(message, dict):
        message = {}

    sender_name = get_telegram_sender_name(
        message
    )

    text = message.get("text")

    if text:
        send_text_to_max(
            text,
            sender_name
        )

    photos = message.get("photo")

    if isinstance(photos, list) and photos:
        photo = photos[-1]

        file_id = photo.get(
            "file_id"
        )

        logging.info(
            "TELEGRAM PHOTO FILE ID: %s",
            file_id
        )

        if file_id:
            file_bytes, content_type = (
                download_telegram_file(
                    file_id
                )
            )

            if file_bytes:
                send_photo_to_max(
                    file_bytes,
                    content_type,
                    message.get(
                        "caption",
                        ""
                    ),
                    sender_name
                )

    voice = message.get("voice")

    if isinstance(voice, dict):
        file_id = voice.get(
            "file_id"
        )

        logging.info(
            "TELEGRAM VOICE FILE ID: %s",
            file_id
        )

        if file_id:
            file_bytes, content_type = (
                download_telegram_file(
                    file_id
                )
            )

            if file_bytes:
                send_audio_to_max(
                    file_bytes,
                    content_type,
                    sender_name
                )

    return jsonify({
        "ok": True
    })


@app.route(
    "/max/webhook",
    methods=["POST"]
)
def max_webhook():
    if MAX_WEBHOOK_SECRET:
        secret = request.headers.get(
            "X-Max-Bot-Api-Secret"
        )

        if secret != MAX_WEBHOOK_SECRET:
            logging.warning(
                "INVALID MAX WEBHOOK SECRET"
            )

            return jsonify({
                "ok": False
            }), 401

    data = request.get_json(
        silent=True
    ) or {}

    logging.info(
        "MAX UPDATE: %s",
        data
    )

    message = data.get(
        "message",
        {}
    )

    if not isinstance(message, dict):
        message = {}

    body = message.get(
        "body",
        {}
    )

    if not isinstance(body, dict):
        body = {}

    sender = message.get(
        "sender",
        {}
    )

    sender_name = get_max_sender_name(
        sender
    )

    text = body.get("text")

    if (
        text
        and TELEGRAM_TOKEN
        and TELEGRAM_CHAT_ID
    ):
        telegram_url = (
            "https://api.telegram.org/bot"
            + TELEGRAM_TOKEN
            + "/sendMessage"
        )

        telegram_text = (
            "MAX -> Telegram\n"
            "👤 " + sender_name + "\n"
            + text
        )

        try:
            response = requests.post(
                telegram_url,
                json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": telegram_text
                },
                timeout=30
            )

            logging.info(
                "TELEGRAM TEXT RESPONSE: %s",
                response.text
            )

        except Exception:
            logging.exception(
                "MAX TEXT TO TELEGRAM ERROR"
            )

    attachments = body.get(
        "attachments",
        []
    )

    if not isinstance(
        attachments,
        list
    ):
        attachments = []

    for attachment in attachments:
        if not isinstance(
            attachment,
            dict
        ):
            continue

        attachment_type = attachment.get(
            "type"
        )

        payload = attachment.get(
            "payload",
            {}
        )

        if not isinstance(
            payload,
            dict
        ):
            payload = {}

        media_url = payload.get(
            "url"
        )

        if (
            attachment_type == "image"
            and media_url
            and TELEGRAM_TOKEN
            and TELEGRAM_CHAT_ID
        ):
            try:
                photo_response = requests.get(
                    media_url,
                    timeout=60
                )

                logging.info(
                    "MAX PHOTO DOWNLOAD STATUS: %s",
                    photo_response.status_code
                )

                if photo_response.ok:
                    telegram_url = (
                        "https://api.telegram.org/bot"
                        + TELEGRAM_TOKEN
                        + "/sendPhoto"
                    )

                    files = {
                        "photo": (
                            "max_photo.jpg",
                            photo_response.content,
                            photo_response.headers.get(
                                "Content-Type",
                                "image/jpeg"
                            )
                        )
                    }

                    caption = (
                        "MAX -> Telegram\n"
                        "👤 " + sender_name
                    )

                    response = requests.post(
                        telegram_url,
                        data={
                            "chat_id": TELEGRAM_CHAT_ID,
                            "caption": caption
                        },
                        files=files,
                        timeout=60
                    )

                    logging.info(
                        "TELEGRAM PHOTO RESPONSE: %s",
                        response.text
                    )

            except Exception:
                logging.exception(
                    "MAX PHOTO TO TELEGRAM ERROR"
                )

        if (
            attachment_type == "audio"
            and media_url
            and TELEGRAM_TOKEN
            and TELEGRAM_CHAT_ID
        ):
            try:
                audio_response = requests.get(
                    media_url,
                    timeout=60
                )

                logging.info(
                    "MAX AUDIO DOWNLOAD STATUS: %s",
                    audio_response.status_code
                )

                if audio_response.ok:
                    telegram_url = (
                        "https://api.telegram.org/bot"
                        + TELEGRAM_TOKEN
                        + "/sendAudio"
                    )

                    files = {
                        "audio": (
                            "max_audio.mp3",
                            audio_response.content,
                            audio_response.headers.get(
                                "Content-Type",
                                "audio/mpeg"
                            )
                        )
                    }

                    caption = (
                        "MAX -> Telegram\n"
                        "👤 " + sender_name
                    )

                    response = requests.post(
                        telegram_url,
                        data={
                            "chat_id": TELEGRAM_CHAT_ID,
                            "caption": caption
                        },
                        files=files,
                        timeout=60
                    )

                    logging.info(
                        "TELEGRAM AUDIO RESPONSE: %s",
                        response.text
                    )

            except Exception:
                logging.exception(
                    "MAX AUDIO TO TELEGRAM ERROR"
                )

    return jsonify({
        "ok": True
    })


@app.route("/setup-max")
def setup_max():
    if not MAX_TOKEN:
        return jsonify({
            "ok": False,
            "error": "MAX_TOKEN is not set"
        }), 500

    url = (
        "https://platform-api2.max.ru/"
        "subscriptions"
    )

    payload = {
        "url": (
            "https://telegram-max-bridge.onrender.com/"
            "max/webhook"
        ),
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
            headers=max_headers(),
            json=payload,
            timeout=30,
            verify=MAX_CA_BUNDLE
        )

        logging.info(
            "MAX SUBSCRIPTION RESPONSE: %s",
            response.text
        )

        try:
            result = response.json()
        except Exception:
            result = response.text

        return jsonify({
            "ok": response.ok,
            "status_code": response.status_code,
            "response": result
        })

    except Exception as e:
        logging.exception(
            "MAX SUBSCRIPTION ERROR"
        )

        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500


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
