import os
import logging
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

# =========================================================
# НАСТРОЙКИ
# =========================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
MAX_TOKEN = os.getenv("MAX_TOKEN")

TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
MAX_CHAT_ID = os.getenv("MAX_CHAT_ID") or "-78865734747587"

MAX_WEBHOOK_SECRET = os.getenv("MAX_WEBHOOK_SECRET")

MAX_API = "https://platform-api2.max.ru"

# =========================================================
# ПРОВЕРКА НАСТРОЕК
# =========================================================

logging.info("=== APPLICATION START ===")
logging.info("TELEGRAM_TOKEN: %s", "SET" if TELEGRAM_TOKEN else "NOT SET")
logging.info("MAX_TOKEN: %s", "SET" if MAX_TOKEN else "NOT SET")
logging.info("TELEGRAM_CHAT_ID: %s", TELEGRAM_CHAT_ID)
logging.info("MAX_CHAT_ID: %s", MAX_CHAT_ID)
logging.info(
    "MAX_WEBHOOK_SECRET: %s",
    "SET" if MAX_WEBHOOK_SECRET else "NOT SET"
)

# =========================================================
# БАЗОВЫЕ ROUTES
# =========================================================

@app.route("/", methods=["GET"])
def index():
    return "Telegram MAX bridge is running", 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "telegram": bool(TELEGRAM_TOKEN),
        "max": bool(MAX_TOKEN),
        "telegram_chat_id": TELEGRAM_CHAT_ID,
        "max_chat_id": MAX_CHAT_ID
    }), 200


# =========================================================
# TELEGRAM API
# =========================================================

def telegram_api(method, data=None, files=None):
    if not TELEGRAM_TOKEN:
        logging.error("TELEGRAM_TOKEN is not configured")
        return None

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}"

    try:
        response = requests.post(
            url,
            data=data,
            files=files,
            timeout=60
        )

        logging.info(
            "Telegram API %s -> %s %s",
            method,
            response.status_code,
            response.text[:500]
        )

        if not response.ok:
            return None

        return response.json()

    except Exception:
        logging.exception("Telegram API error")
        return None


def send_telegram_text(text):
    if not TELEGRAM_CHAT_ID:
        logging.error("TELEGRAM_CHAT_ID is not configured")
        return False

    result = telegram_api(
        "sendMessage",
        data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text
        }
    )

    return bool(result and result.get("ok"))


def send_telegram_photo(photo_bytes, filename="photo.jpg", caption=None):
    if not TELEGRAM_CHAT_ID:
        logging.error("TELEGRAM_CHAT_ID is not configured")
        return False

    files = {
        "photo": (
            filename,
            photo_bytes,
            "image/jpeg"
        )
    }

    data = {
        "chat_id": TELEGRAM_CHAT_ID
    }

    if caption:
        data["caption"] = caption

    result = telegram_api(
        "sendPhoto",
        data=data,
        files=files
    )

    return bool(result and result.get("ok"))


def send_telegram_voice(audio_bytes, filename="voice.ogg"):
    if not TELEGRAM_CHAT_ID:
        logging.error("TELEGRAM_CHAT_ID is not configured")
        return False

    files = {
        "voice": (
            filename,
            audio_bytes,
            "audio/ogg"
        )
    }

    result = telegram_api(
        "sendVoice",
        data={
            "chat_id": TELEGRAM_CHAT_ID
        },
        files=files
    )

    return bool(result and result.get("ok"))


def get_telegram_file(file_id):
    if not TELEGRAM_TOKEN:
        return None

    result = telegram_api(
        "getFile",
        data={
            "file_id": file_id
        }
    )

    if not result or not result.get("ok"):
        return None

    file_path = result["result"].get("file_path")

    if not file_path:
        return None

    url = (
        f"https://api.telegram.org/file/bot"
        f"{TELEGRAM_TOKEN}/{file_path}"
    )

    try:
        response = requests.get(url, timeout=60)

        logging.info(
            "Telegram file download -> %s",
            response.status_code
        )

        if not response.ok:
            return None

        return response.content, file_path

    except Exception:
        logging.exception("Telegram file download error")
        return None


# =========================================================
# MAX API
# =========================================================

def max_headers():
    headers = {
        "Authorization": MAX_TOKEN
    }

    return headers


def max_request(method, endpoint, **kwargs):
    if not MAX_TOKEN:
        logging.error("MAX_TOKEN is not configured")
        return None

    url = f"{MAX_API}{endpoint}"

    headers = kwargs.pop("headers", {})
    headers.update(max_headers())

    try:
        response = requests.request(
            method,
            url,
            headers=headers,
            timeout=60,
            **kwargs
        )

        logging.info(
            "MAX API %s %s -> %s %s",
            method,
            endpoint,
            response.status_code,
            response.text[:1000]
        )

        if not response.ok:
            return None

        if not response.text:
            return {}

        return response.json()

    except Exception:
        logging.exception("MAX API error")
        return None


def send_max_text(text):
    if not MAX_CHAT_ID:
        logging.error("MAX_CHAT_ID is not configured")
        return False

    payload = {
        "text": text,
        "chat_id": int(MAX_CHAT_ID)
    }

    result = max_request(
        "POST",
        "/messages",
        json=payload
    )

    return result is not None


def upload_to_max(file_bytes, file_type, filename):
    """
    Загружает файл в MAX и возвращает token.
    file_type:
      image
      audio
      video
      file
    """

    if not MAX_TOKEN:
        logging.error("MAX_TOKEN is not configured")
        return None

    try:
        # Получаем upload URL
        response = requests.post(
            f"{MAX_API}/uploads",
            headers=max_headers(),
            params={
                "type": file_type
            },
            timeout=60
        )

        logging.info(
            "MAX upload initialization -> %s %s",
            response.status_code,
            response.text[:1000]
        )

        if not response.ok:
            return None

        upload_data = response.json()

        upload_url = upload_data.get("url")

        if not upload_url:
            logging.error(
                "MAX upload URL was not returned: %s",
                upload_data
            )
            return None

        # Загружаем сам файл
        upload_response = requests.post(
            upload_url,
            files={
                "file": (
                    filename,
                    file_bytes
                )
            },
            timeout=120
        )

        logging.info(
            "MAX file upload -> %s %s",
            upload_response.status_code,
            upload_response.text[:1000]
        )

        if not upload_response.ok:
            return None

        result = upload_response.json()

        token = result.get("token")

        if not token:
            logging.error(
                "MAX upload token was not returned: %s",
                result
            )
            return None

        return token

    except Exception:
        logging.exception("MAX upload error")
        return None


def send_max_image(image_bytes, filename="photo.jpg"):
    token = upload_to_max(
        image_bytes,
        "image",
        filename
    )

    if not token:
        return False

    payload = {
        "chat_id": int(MAX_CHAT_ID),
        "attachments": [
            {
                "type": "image",
                "payload": {
                    "token": token
                }
            }
        ]
    }

    result = max_request(
        "POST",
        "/messages",
        json=payload
    )

    return result is not None


def send_max_audio(audio_bytes, filename="voice.ogg"):
    token = upload_to_max(
        audio_bytes,
        "audio",
        filename
    )

    if not token:
        return False

    payload = {
        "chat_id": int(MAX_CHAT_ID),
        "attachments": [
            {
                "type": "audio",
                "payload": {
                    "token": token
                }
            }
        ]
    }

    result = max_request(
        "POST",
        "/messages",
        json=payload
    )

    return result is not None


def send_max_file(file_bytes, filename="file"):
    token = upload_to_max(
        file_bytes,
        "file",
        filename
    )

    if not token:
        return False

    payload = {
        "chat_id": int(MAX_CHAT_ID),
        "attachments": [
            {
                "type": "file",
                "payload": {
                    "token": token
                }
            }
        ]
    }

    result = max_request(
        "POST",
        "/messages",
        json=payload
    )

    return result is not None


# =========================================================
# ИМЯ ОТПРАВИТЕЛЯ TELEGRAM
# =========================================================

def telegram_sender_name(message):
    sender = message.get("from", {})

    first_name = sender.get("first_name", "")
    last_name = sender.get("last_name", "")
    username = sender.get("username", "")

    full_name = " ".join(
        x for x in [first_name, last_name]
        if x
    ).strip()

    if full_name:
        return full_name

    if username:
        return f"@{username}"

    return "Пользователь Telegram"


# =========================================================
# TELEGRAM -> MAX
# =========================================================

def handle_telegram_message(message):
    if not isinstance(message, dict):
        return

    sender_name = telegram_sender_name(message)

    # -----------------------------
    # ТЕКСТ
    # -----------------------------

    text = message.get("text")

    if text:
        max_text = f"💬 {sender_name}:\n{text}"

        logging.info(
            "Telegram -> MAX text: %s",
            max_text
        )

        send_max_text(max_text)

    # -----------------------------
    # ФОТО
    # -----------------------------

    photo = message.get("photo")

    if photo:
        try:
            # Берём самое большое фото
            largest_photo = photo[-1]

            file_id = largest_photo.get("file_id")

            if file_id:
                downloaded = get_telegram_file(file_id)

                if downloaded:
                    file_bytes, file_path = downloaded

                    filename = os.path.basename(file_path)

                    logging.info(
                        "Telegram -> MAX photo: %s",
                        filename
                    )

                    send_max_image(
                        file_bytes,
                        filename
                    )

        except Exception:
            logging.exception(
                "Error processing Telegram photo"
            )

    # -----------------------------
    # ГОЛОСОВОЕ
    # -----------------------------

    voice = message.get("voice")

    if voice:
        try:
            file_id = voice.get("file_id")

            if file_id:
                downloaded = get_telegram_file(file_id)

                if downloaded:
                    file_bytes, file_path = downloaded

                    filename = os.path.basename(file_path)

                    logging.info(
                        "Telegram -> MAX voice: %s",
                        filename
                    )

                    send_max_audio(
                        file_bytes,
                        filename
                    )

        except Exception:
            logging.exception(
                "Error processing Telegram voice"
            )

    # -----------------------------
    # AUDIO
    # -----------------------------

    audio = message.get("audio")

    if audio:
        try:
            file_id = audio.get("file_id")

            if file_id:
                downloaded = get_telegram_file(file_id)

                if downloaded:
                    file_bytes, file_path = downloaded

                    filename = audio.get(
                        "file_name"
                    ) or os.path.basename(file_path)

                    logging.info(
                        "Telegram -> MAX audio: %s",
                        filename
                    )

                    send_max_audio(
                        file_bytes,
                        filename
                    )

        except Exception:
            logging.exception(
                "Error processing Telegram audio"
            )


# =========================================================
# TELEGRAM WEBHOOK
# =========================================================

@app.route("/telegram/webhook", methods=["POST"])
def telegram_webhook():

    logging.info("===== TELEGRAM WEBHOOK =====")

    try:
        update = request.get_json(
            silent=True
        )

        logging.info(
            "Telegram update: %s",
            str(update)[:5000]
        )

        if not update:
            return jsonify({
                "ok": True
            }), 200

        message = update.get("message")

        if message:
            handle_telegram_message(message)

        return jsonify({
            "ok": True
        }), 200

    except Exception:
        logging.exception(
            "Telegram webhook error"
        )

        # Telegram всё равно получает 200,
        # чтобы не зациклить повторные попытки
        return jsonify({
            "ok": True
        }), 200


# =========================================================
# MAX -> TELEGRAM
# =========================================================

def get_max_sender_name(message):
    sender = message.get("sender")

    if isinstance(sender, dict):

        name = sender.get("name")

        if name:
            return name

        first_name = sender.get(
            "first_name",
            ""
        )

        last_name = sender.get(
            "last_name",
            ""
        )

        full_name = " ".join(
            x for x in [first_name, last_name]
            if x
        ).strip()

        if full_name:
            return full_name

    return "Пользователь MAX"


def handle_max_message(event):
    logging.info(
        "MAX message event: %s",
        str(event)[:10000]
    )

    message = event.get("message", event)

    if not isinstance(message, dict):
        return

    sender_name = get_max_sender_name(message)

    # -----------------------------
    # ТЕКСТ
    # -----------------------------

    body = message.get("body")

    text = None

    if isinstance(body, dict):
        text = body.get("text")

    if not text:
        text = message.get("text")

    if text:
        telegram_text = (
            f"💬 {sender_name}:\n{text}"
        )

        logging.info(
            "MAX -> Telegram text: %s",
            telegram_text
        )

        send_telegram_text(
            telegram_text
        )

    # -----------------------------
    # ВЛОЖЕНИЯ
    # -----------------------------

    attachments = []

    if isinstance(body, dict):
        attachments = body.get(
            "attachments",
            []
        )

    if not attachments:
        attachments = message.get(
            "attachments",
            []
        )

    if attachments:
        logging.info(
            "MAX attachments: %s",
            str(attachments)[:10000]
        )

    # -----------------------------------------------------
    # ВАЖНО:
    # Сейчас для MAX -> Telegram мы сначала проверяем
    # наличие прямых URL в attachment.
    # Это позволяет обработать вложения, если MAX
    # присылает URL непосредственно в webhook.
    # -----------------------------------------------------

    for attachment in attachments:

        if not isinstance(attachment, dict):
            continue

        attachment_type = attachment.get(
            "type"
        )

        payload = attachment.get(
            "payload",
            {}
        )

        if not isinstance(payload, dict):
            payload = {}

        # Возможные места URL
        attachment_url = (
            payload.get("url")
            or attachment.get("url")
            or payload.get("download_url")
            or attachment.get("download_url")
        )

        # -----------------------------
        # IMAGE
        # -----------------------------

        if attachment_type == "image":

            if attachment_url:
                try:
                    response = requests.get(
                        attachment_url,
                        timeout=60
                    )

                    if response.ok:

                        send_telegram_photo(
                            response.content,
                            "image.jpg"
                        )

                except Exception:
                    logging.exception(
                        "MAX image download error"
                    )
            else:
                logging.info(
                    "MAX image has no direct URL"
                )

        # -----------------------------
        # AUDIO
        # -----------------------------

        elif attachment_type == "audio":

            if attachment_url:
                try:
                    response = requests.get(
                        attachment_url,
                        timeout=60
                    )

                    if response.ok:

                        send_telegram_voice(
                            response.content,
                            "voice.ogg"
                        )

                except Exception:
                    logging.exception(
                        "MAX audio download error"
                    )
            else:
                logging.info(
                    "MAX audio has no direct URL"
                )

        # -----------------------------
        # FILE
        # -----------------------------

        elif attachment_type == "file":

            if attachment_url:
                try:
                    response = requests.get(
                        attachment_url,
                        timeout=60
                    )

                    if response.ok:

                        filename = (
                            payload.get("filename")
                            or payload.get("name")
                            or "file"
                        )

                        send_telegram_document(
                            response.content,
                            filename
                        )

                except Exception:
                    logging.exception(
                        "MAX file download error"
                    )


# =========================================================
# TELEGRAM DOCUMENT
# =========================================================

def send_telegram_document(
    file_bytes,
    filename="file"
):
    if not TELEGRAM_CHAT_ID:
        logging.error(
            "TELEGRAM_CHAT_ID is not configured"
        )
        return False

    files = {
        "document": (
            filename,
            file_bytes
        )
    }

    result = telegram_api(
        "sendDocument",
        data={
            "chat_id": TELEGRAM_CHAT_ID
        },
        files=files
    )

    return bool(
        result and result.get("ok")
    )


# =========================================================
# MAX WEBHOOK
# =========================================================

@app.route("/max/webhook", methods=["POST"])
def max_webhook():

    logging.info("===== MAX WEBHOOK =====")

    try:

        # Проверка секрета
        if MAX_WEBHOOK_SECRET:

            received_secret = request.headers.get(
                "X-Max-Bot-Api-Secret"
            )

            if received_secret != MAX_WEBHOOK_SECRET:

                logging.warning(
                    "MAX webhook secret mismatch"
                )

                return jsonify({
                    "ok": False,
                    "error": "forbidden"
                }), 403

        event = request.get_json(
            silent=True
        )

        logging.info(
            "MAX event: %s",
            str(event)[:10000]
        )

        if not event:
            return jsonify({
                "ok": True
            }), 200

        event_type = event.get(
            "update_type"
        ) or event.get(
            "type"
        )

        logging.info(
            "MAX event type: %s",
            event_type
        )

        # Сообщение
        if event_type in (
            "message_created",
            "message"
        ):

            handle_max_message(event)

        return jsonify({
            "ok": True
        }), 200

    except Exception:
        logging.exception(
            "MAX webhook error"
        )

        return jsonify({
            "ok": True
        }), 200


# =========================================================
# START
# =========================================================

if __name__ == "__main__":

    port = int(
        os.getenv(
            "PORT",
            "10000"
        )
    )

    logging.info(
        "Starting server on port %s",
        port
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
