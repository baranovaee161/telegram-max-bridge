import os
import time
import logging
import requests

from flask import Flask, request, jsonify


# =========================================================
# APPLICATION
# =========================================================

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
# START LOG
# =========================================================

logging.info("========================================")
logging.info("=== TELEGRAM <-> MAX BRIDGE START ===")
logging.info("========================================")

logging.info(
    "TELEGRAM_TOKEN: %s",
    "SET" if TELEGRAM_TOKEN else "NOT SET"
)

logging.info(
    "MAX_TOKEN: %s",
    "SET" if MAX_TOKEN else "NOT SET"
)

logging.info(
    "TELEGRAM_CHAT_ID: %s",
    TELEGRAM_CHAT_ID
)

logging.info(
    "MAX_CHAT_ID: %s",
    MAX_CHAT_ID
)

logging.info(
    "MAX_WEBHOOK_SECRET: %s",
    "SET" if MAX_WEBHOOK_SECRET else "NOT SET"
)


# =========================================================
# BASIC ROUTES
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
            response.text[:1000]
        )

        if not response.ok:
            return None

        return response.json()

    except Exception:
        logging.exception("Telegram API error")
        return None


# =========================================================
# TELEGRAM SEND TEXT
# =========================================================

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


# =========================================================
# TELEGRAM SEND PHOTO
# =========================================================

def send_telegram_photo(
    photo_bytes,
    filename="photo.jpg",
    caption=None
):
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


# =========================================================
# TELEGRAM SEND VOICE
# =========================================================

def send_telegram_voice(
    audio_bytes,
    filename="voice.ogg"
):
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


# =========================================================
# TELEGRAM SEND DOCUMENT
# =========================================================

def send_telegram_document(
    file_bytes,
    filename="file"
):
    if not TELEGRAM_CHAT_ID:
        logging.error("TELEGRAM_CHAT_ID is not configured")
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

    return bool(result and result.get("ok"))


# =========================================================
# GET TELEGRAM FILE
# =========================================================

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

        response = requests.get(
            url,
            timeout=60
        )

        logging.info(
            "Telegram file download -> %s",
            response.status_code
        )

        if not response.ok:
            return None

        return response.content, file_path

    except Exception:
        logging.exception(
            "Telegram file download error"
        )

        return None


# =========================================================
# MAX API
# =========================================================

def max_headers():

    return {
        "Authorization": MAX_TOKEN
    }


def max_request(
    method,
    endpoint,
    **kwargs
):

    if not MAX_TOKEN:
        logging.error(
            "MAX_TOKEN is not configured"
        )
        return None

    url = f"{MAX_API}{endpoint}"

    headers = kwargs.pop(
        "headers",
        {}
    )

    headers.update(
        max_headers()
    )

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
            response.text[:2000]
        )

        if not response.ok:
            return None

        if not response.text:
            return {}

        return response.json()

    except Exception:
        logging.exception(
            "MAX API error"
        )

        return None


# =========================================================
# MAX SEND TEXT
# =========================================================

def send_max_text(text):

    if not MAX_CHAT_ID:
        logging.error(
            "MAX_CHAT_ID is not configured"
        )
        return False

    try:

        chat_id = int(MAX_CHAT_ID)

    except Exception:

        logging.error(
            "MAX_CHAT_ID is not an integer: %s",
            MAX_CHAT_ID
        )

        return False

    payload = {
        "text": text
    }

    result = max_request(
        "POST",
        "/messages",
        params={
            "chat_id": chat_id
        },
        json=payload
    )

    if result is None:
        logging.error(
            "MAX text message FAILED"
        )
        return False

    logging.info(
        "MAX text message SENT"
    )

    return True


# =========================================================
# MAX UPLOAD
# =========================================================

def upload_to_max(
    file_bytes,
    file_type,
    filename
):
    """
    Загружает файл в MAX.

    file_type:
        image
        audio
        video
        file
    """

    if not MAX_TOKEN:
        logging.error(
            "MAX_TOKEN is not configured"
        )
        return None

    try:

        # -------------------------------------------------
        # 1. Получаем URL загрузки
        # -------------------------------------------------

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
            response.text[:2000]
        )

        if not response.ok:
            return None

        upload_data = response.json()

        upload_url = upload_data.get(
            "url"
        )

        initial_token = upload_data.get(
            "token"
        )

        if not upload_url:
            logging.error(
                "MAX upload URL missing: %s",
                upload_data
            )
            return None

        # -------------------------------------------------
        # 2. Загружаем файл
        # -------------------------------------------------

        upload_response = requests.post(
            upload_url,
            files={
                "data": (
                    filename,
                    file_bytes
                )
            },
            timeout=120
        )

        logging.info(
            "MAX file upload -> %s %s",
            upload_response.status_code,
            upload_response.text[:2000]
        )

        if not upload_response.ok:
            return None

        upload_result = upload_response.json()

        token = (
            upload_result.get("token")
            or initial_token
        )

        if not token:
            logging.error(
                "MAX upload token missing: %s",
                upload_result
            )
            return None

        logging.info(
            "MAX upload token received"
        )

        return token

    except Exception:

        logging.exception(
            "MAX upload error"
        )

        return None


# =========================================================
# MAX SEND ATTACHMENT
# =========================================================

def send_max_attachment(
    file_bytes,
    file_type,
    filename,
    attachment_type
):

    token = upload_to_max(
        file_bytes,
        file_type,
        filename
    )

    if not token:
        return False

    try:

        chat_id = int(MAX_CHAT_ID)

    except Exception:

        logging.error(
            "Invalid MAX_CHAT_ID: %s",
            MAX_CHAT_ID
        )

        return False

    payload = {
        "attachments": [
            {
                "type": attachment_type,
                "payload": {
                    "token": token
                }
            }
        ]
    }

    # -----------------------------------------------------
    # MAX иногда ещё обрабатывает файл после upload.
    # Делаем несколько попыток.
    # -----------------------------------------------------

    delays = [
        1,
        2,
        4,
        6
    ]

    for attempt, delay in enumerate(
        delays,
        start=1
    ):

        if attempt > 1:
            time.sleep(delay)

        logging.info(
            "MAX attachment send attempt %s",
            attempt
        )

        result = max_request(
            "POST",
            "/messages",
            params={
                "chat_id": chat_id
            },
            json=payload
        )

        if result is not None:

            logging.info(
                "MAX attachment SENT successfully"
            )

            return True

        logging.warning(
            "MAX attachment attempt %s failed",
            attempt
        )

    logging.error(
        "MAX attachment FAILED after all attempts"
    )

    return False


# =========================================================
# MAX SEND IMAGE
# =========================================================

def send_max_image(
    image_bytes,
    filename="photo.jpg"
):

    return send_max_attachment(
        image_bytes,
        "image",
        filename,
        "image"
    )


# =========================================================
# MAX SEND AUDIO
# =========================================================

def send_max_audio(
    audio_bytes,
    filename="voice.ogg"
):

    return send_max_attachment(
        audio_bytes,
        "audio",
        filename,
        "audio"
    )


# =========================================================
# MAX SEND FILE
# =========================================================

def send_max_file(
    file_bytes,
    filename="file"
):

    return send_max_attachment(
        file_bytes,
        "file",
        filename,
        "file"
    )


# =========================================================
# TELEGRAM SENDER NAME
# =========================================================

def telegram_sender_name(message):

    sender = message.get(
        "from",
        {}
    )

    if not isinstance(sender, dict):
        return "Пользователь Telegram"

    username = sender.get(
        "username"
    )

    first_name = sender.get(
        "first_name",
        ""
    )

    last_name = sender.get(
        "last_name",
        ""
    )

    full_name = " ".join(
        x
        for x in [
            first_name,
            last_name
        ]
        if x
    ).strip()

    # -----------------------------------------------------
    # ВАЖНО:
    # Сначала username.
    # -----------------------------------------------------

    if username:
        return f"@{username}"

    if full_name:
        return full_name

    user_id = sender.get(
        "id"
    )

    if user_id:
        return f"Telegram ID {user_id}"

    return "Пользователь Telegram"


# =========================================================
# TELEGRAM -> MAX
# =========================================================

def handle_telegram_message(message):

    if not isinstance(
        message,
        dict
    ):
        return

    sender_name = telegram_sender_name(
        message
    )

    logging.info(
        "Telegram sender: %s",
        sender_name
    )

    # =====================================================
    # TEXT
    # =====================================================

    text = message.get(
        "text"
    )

    if text:

        max_text = (
            f"👤 {sender_name}\n"
            f"{text}"
        )

        logging.info(
            "Telegram -> MAX TEXT: %s",
            max_text
        )

        send_max_text(
            max_text
        )

    # =====================================================
    # PHOTO
    # =====================================================

    photo = message.get(
        "photo"
    )

    if photo:

        try:

            largest_photo = photo[-1]

            file_id = largest_photo.get(
                "file_id"
            )

            if file_id:

                downloaded = get_telegram_file(
                    file_id
                )

                if downloaded:

                    file_bytes, file_path = downloaded

                    filename = os.path.basename(
                        file_path
                    )

                    logging.info(
                        "Telegram -> MAX PHOTO: %s",
                        filename
                    )

                    # Сначала подпись с автором
                    send_max_text(
                        f"📷 {sender_name} отправил(а) фото:"
                    )

                    send_max_image(
                        file_bytes,
                        filename
                    )

        except Exception:

            logging.exception(
                "Error processing Telegram photo"
            )

    # =====================================================
    # VOICE
    # =====================================================

    voice = message.get(
        "voice"
    )

    if voice:

        try:

            file_id = voice.get(
                "file_id"
            )

            if file_id:

                downloaded = get_telegram_file(
                    file_id
                )

                if downloaded:

                    file_bytes, file_path = downloaded

                    filename = os.path.basename(
                        file_path
                    )

                    logging.info(
                        "Telegram -> MAX VOICE: %s",
                        filename
                    )

                    send_max_text(
                        f"🎤 {sender_name} отправил(а) голосовое:"
                    )

                    send_max_audio(
                        file_bytes,
                        filename
                    )

        except Exception:

            logging.exception(
                "Error processing Telegram voice"
            )

    # =====================================================
    # AUDIO
    # =====================================================

    audio = message.get(
        "audio"
    )

    if audio:

        try:

            file_id = audio.get(
                "file_id"
            )

            if file_id:

                downloaded = get_telegram_file(
                    file_id
                )

                if downloaded:

                    file_bytes, file_path = downloaded

                    filename = (
                        audio.get(
                            "file_name"
                        )
                        or os.path.basename(
                            file_path
                        )
                    )

                    logging.info(
                        "Telegram -> MAX AUDIO: %s",
                        filename
                    )

                    send_max_text(
                        f"🎵 {sender_name} отправил(а) аудио:"
                    )

                    send_max_audio(
                        file_bytes,
                        filename
                    )

        except Exception:

            logging.exception(
                "Error processing Telegram audio"
            )

    # =====================================================
    # DOCUMENT
    # =====================================================

    document = message.get(
        "document"
    )

    if document:

        try:

            file_id = document.get(
                "file_id"
            )

            if file_id:

                downloaded = get_telegram_file(
                    file_id
                )

                if downloaded:

                    file_bytes, file_path = downloaded

                    filename = (
                        document.get(
                            "file_name"
                        )
                        or os.path.basename(
                            file_path
                        )
                        or "file"
                    )

                    logging.info(
                        "Telegram -> MAX DOCUMENT: %s",
                        filename
                    )

                    send_max_text(
                        f"📎 {sender_name} отправил(а) файл:"
                    )

                    send_max_file(
                        file_bytes,
                        filename
                    )

        except Exception:

            logging.exception(
                "Error processing Telegram document"
            )


# =========================================================
# TELEGRAM WEBHOOK
# =========================================================

@app.route(
    "/telegram/webhook",
    methods=["POST"]
)
def telegram_webhook():

    logging.info(
        "===== TELEGRAM WEBHOOK ====="
    )

    try:

        update = request.get_json(
            silent=True
        )

        logging.info(
            "Telegram update: %s",
            str(update)[:10000]
        )

        if not update:

            return jsonify({
                "ok": True
            }), 200

        message = update.get(
            "message"
        )

        if message:

            handle_telegram_message(
                message
            )

        return jsonify({
            "ok": True
        }), 200

    except Exception:

        logging.exception(
            "Telegram webhook error"
        )

        return jsonify({
            "ok": True
        }), 200


# =========================================================
# MAX SENDER NAME
# =========================================================

def get_max_sender_name(message):

    sender = message.get(
        "sender"
    )

    if not isinstance(
        sender,
        dict
    ):

        return "Пользователь MAX"

    username = sender.get(
        "username"
    )

    first_name = sender.get(
        "first_name",
        ""
    )

    last_name = sender.get(
        "last_name",
        ""
    )

    name = sender.get(
        "name"
    )

    user_id = sender.get(
        "user_id"
    )

    # -----------------------------------------------------
    # Сначала username
    # -----------------------------------------------------

    if username:

        if str(username).startswith("@"):
            return str(username)

        return f"@{username}"

    # -----------------------------------------------------
    # Потом имя
    # -----------------------------------------------------

    full_name = " ".join(
        x
        for x in [
            first_name,
            last_name
        ]
        if x
    ).strip()

    if full_name:
        return full_name

    # -----------------------------------------------------
    # Старое поле name
    # -----------------------------------------------------

    if name:
        return name

    # -----------------------------------------------------
    # ID
    # -----------------------------------------------------

    if user_id:
        return f"MAX ID {user_id}"

    return "Пользователь MAX"


# =========================================================
# MAX -> TELEGRAM
# =========================================================

def handle_max_message(event):

    logging.info(
        "MAX message event: %s",
        str(event)[:15000]
    )

    message = event.get(
        "message",
        event
    )

    if not isinstance(
        message,
        dict
    ):
        return

    sender_name = get_max_sender_name(
        message
    )

    logging.info(
        "MAX sender: %s",
        sender_name
    )

    # =====================================================
    # BODY
    # =====================================================

    body = message.get(
        "body"
    )

    if not isinstance(
        body,
        dict
    ):
        body = {}

    # =====================================================
    # TEXT
    # =====================================================

    text = body.get(
        "text"
    )

    if not text:
        text = message.get(
            "text"
        )

    if text:

        telegram_text = (
            f"👤 {sender_name}\n"
            f"{text}"
        )

        logging.info(
            "MAX -> Telegram TEXT: %s",
            telegram_text
        )

        send_telegram_text(
            telegram_text
        )

    # =====================================================
    # ATTACHMENTS
    # =====================================================

    attachments = body.get(
        "attachments",
        []
    )

    if not attachments:

        attachments = message.get(
            "attachments",
            []
        )

    if not isinstance(
        attachments,
        list
    ):
        attachments = []

    logging.info(
        "MAX attachments count: %s",
        len(attachments)
    )

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

        logging.info(
            "MAX attachment type=%s payload=%s",
            attachment_type,
            str(payload)[:5000]
        )

        # -------------------------------------------------
        # URL
        # -------------------------------------------------

        attachment_url = (
            payload.get("url")
            or attachment.get("url")
            or payload.get("download_url")
            or attachment.get("download_url")
        )

        # -------------------------------------------------
        # IMAGE
        # -------------------------------------------------

        if attachment_type == "image":

            if attachment_url:

                try:

                    response = requests.get(
                        attachment_url,
                        timeout=60
                    )

                    logging.info(
                        "MAX image download -> %s",
                        response.status_code
                    )

                    if response.ok:

                        send_telegram_photo(
                            response.content,
                            "image.jpg",
                            caption=(
                                f"👤 {sender_name}"
                            )
                        )

                except Exception:

                    logging.exception(
                        "MAX image download error"
                    )

            else:

                logging.warning(
                    "MAX image has no direct URL"
                )

        # -------------------------------------------------
        # AUDIO
        # -------------------------------------------------

        elif attachment_type == "audio":

            if attachment_url:

                try:

                    response = requests.get(
                        attachment_url,
                        timeout=60
                    )

                    logging.info(
                        "MAX audio download -> %s",
                        response.status_code
                    )

                    if response.ok:

                        send_telegram_voice(
                            response.content,
                            "voice.ogg"
                        )

                        send_telegram_text(
                            f"👤 {sender_name}"
                        )

                except Exception:

                    logging.exception(
                        "MAX audio download error"
                    )

            else:

                logging.warning(
                    "MAX audio has no direct URL"
                )

        # -------------------------------------------------
        # FILE
        # -------------------------------------------------

        elif attachment_type == "file":

            if attachment_url:

                try:

                    response = requests.get(
                        attachment_url,
                        timeout=60
                    )

                    logging.info(
                        "MAX file download -> %s",
                        response.status_code
                    )

                    if response.ok:

                        filename = (
                            payload.get(
                                "filename"
                            )
                            or payload.get(
                                "name"
                            )
                            or "file"
                        )

                        send_telegram_text(
                            f"📎 {sender_name} отправил(а) файл:"
                        )

                        send_telegram_document(
                            response.content,
                            filename
                        )

                except Exception:

                    logging.exception(
                        "MAX file download error"
                    )

            else:

                logging.warning(
                    "MAX file has no direct URL"
                )

        # -------------------------------------------------
        # VIDEO
        # -------------------------------------------------

        elif attachment_type == "video":

            if attachment_url:

                try:

                    response = requests.get(
                        attachment_url,
                        timeout=120
                    )

                    logging.info(
                        "MAX video download -> %s",
                        response.status_code
                    )

                    if response.ok:

                        # Telegram можно отправлять видео
                        # через sendVideo.
                        send_telegram_video(
                            response.content,
                            "video.mp4",
                            caption=(
                                f"👤 {sender_name}"
                            )
                        )

                except Exception:

                    logging.exception(
                        "MAX video download error"
                    )

            else:

                logging.warning(
                    "MAX video has no direct URL"
                )


# =========================================================
# TELEGRAM SEND VIDEO
# =========================================================

def send_telegram_video(
    video_bytes,
    filename="video.mp4",
    caption=None
):

    if not TELEGRAM_CHAT_ID:
        logging.error(
            "TELEGRAM_CHAT_ID is not configured"
        )
        return False

    files = {
        "video": (
            filename,
            video_bytes,
            "video/mp4"
        )
    }

    data = {
        "chat_id": TELEGRAM_CHAT_ID
    }

    if caption:
        data["caption"] = caption

    result = telegram_api(
        "sendVideo",
        data=data,
        files=files
    )

    return bool(
        result and result.get("ok")
    )


# =========================================================
# MAX WEBHOOK
# =========================================================

@app.route(
    "/max/webhook",
    methods=["POST"]
)
def max_webhook():

    logging.info(
        "===== MAX WEBHOOK ====="
    )

    try:

        # -------------------------------------------------
        # Проверяем секрет
        # -------------------------------------------------

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

        # -------------------------------------------------
        # Получаем event
        # -------------------------------------------------

        event = request.get_json(
            silent=True
        )

        logging.info(
            "MAX event: %s",
            str(event)[:15000]
        )

        if not event:

            return jsonify({
                "ok": True
            }), 200

        event_type = (
            event.get(
                "update_type"
            )
            or event.get(
                "type"
            )
        )

        logging.info(
            "MAX event type: %s",
            event_type
        )

        # -------------------------------------------------
        # MESSAGE
        # -------------------------------------------------

        if event_type in (
            "message_created",
            "message"
        ):

            handle_max_message(
                event
            )

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
# START SERVER
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
