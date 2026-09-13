import os
import logging
import requests

from flask import Flask, request, jsonify


# ============================================================
# APP
# ============================================================

app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

logger = logging.getLogger(__name__)


# ============================================================
# ENVIRONMENT VARIABLES
# ============================================================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
MAX_TOKEN = os.getenv("MAX_TOKEN")

TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

MAX_CHAT_ID = os.getenv("MAX_CHAT_ID") or "-78865734747587"

MAX_WEBHOOK_SECRET = os.getenv("MAX_WEBHOOK_SECRET")

# URL твоего приложения.
# Например:
# https://telegram-max-bridge.onrender.com
APP_URL = os.getenv("APP_URL")

# Сертификат Минцифры, который используется для MAX API.
MAX_CA_BUNDLE = os.getenv(
    "MAX_CA_BUNDLE",
    "/etc/secrets/max_ca_bundle.pem"
)


# ============================================================
# CONSTANTS
# ============================================================

TELEGRAM_API = (
    "https://api.telegram.org/bot"
    + str(TELEGRAM_TOKEN or "")
)

MAX_API = "https://platform-api2.max.ru"


# ============================================================
# BASIC ROUTES
# ============================================================

@app.route("/", methods=["GET"])
def home():
    return "Telegram MAX bridge is running", 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "telegram_token": bool(TELEGRAM_TOKEN),
        "max_token": bool(MAX_TOKEN),
        "telegram_chat_id": TELEGRAM_CHAT_ID,
        "max_chat_id": MAX_CHAT_ID,
        "max_webhook_secret": bool(MAX_WEBHOOK_SECRET),
        "app_url": APP_URL
    }), 200


# ============================================================
# HELPERS
# ============================================================

def max_headers():
    return {
        "Authorization": MAX_TOKEN,
        "Content-Type": "application/json"
    }


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
    ).strip()

    if name:
        return name

    return "Пользователь"


def get_max_sender_name(sender):
    if not isinstance(sender, dict):
        return "Пользователь"

    username = sender.get("username")
    first_name = sender.get("first_name", "")
    last_name = sender.get("last_name", "")
    name = sender.get("name")

    if username:
        return "@" + username

    if name:
        return name

    full_name = " ".join(
        x for x in [first_name, last_name]
        if x
    ).strip()

    if full_name:
        return full_name

    return "Пользователь"


def safe_json(response):
    try:
        return response.json()
    except Exception:
        return None


# ============================================================
# TELEGRAM API
# ============================================================

def telegram_request(method, params=None, files=None, timeout=30):
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM TOKEN IS MISSING")
        return None

    url = TELEGRAM_API + "/" + method

    try:
        response = requests.post(
            url,
            params=params,
            files=files,
            timeout=timeout
        )

        logger.info(
            "TELEGRAM API %s STATUS: %s",
            method,
            response.status_code
        )

        logger.info(
            "TELEGRAM API %s RESPONSE: %s",
            method,
            response.text[:2000]
        )

        return response

    except Exception:
        logger.exception(
            "TELEGRAM API ERROR: %s",
            method
        )

        return None


def send_text_to_telegram(text):
    if not TELEGRAM_TOKEN:
        logger.error("CANNOT SEND TO TELEGRAM: TOKEN MISSING")
        return False

    if not TELEGRAM_CHAT_ID:
        logger.error("CANNOT SEND TO TELEGRAM: CHAT ID MISSING")
        return False

    if not text:
        text = "Пустое сообщение"

    # Telegram имеет лимит около 4096 символов.
    # Разбиваем длинные сообщения.
    chunks = [
        text[i:i + 4000]
        for i in range(0, len(text), 4000)
    ]

    success = True

    for chunk in chunks:
        response = telegram_request(
            "sendMessage",
            params={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": chunk
            }
        )

        if not response or not response.ok:
            success = False

    return success


def send_photo_to_telegram(file_bytes, filename="image.jpg", content_type="image/jpeg", caption=None):
    if not TELEGRAM_TOKEN:
        logger.error("CANNOT SEND PHOTO TO TELEGRAM: TOKEN MISSING")
        return False

    if not TELEGRAM_CHAT_ID:
        logger.error("CANNOT SEND PHOTO TO TELEGRAM: CHAT ID MISSING")
        return False

    files = {
        "photo": (
            filename,
            file_bytes,
            content_type or "image/jpeg"
        )
    }

    data = {
        "chat_id": TELEGRAM_CHAT_ID
    }

    if caption:
        data["caption"] = caption[:1024]

    response = telegram_request(
        "sendPhoto",
        params=data,
        files=files,
        timeout=60
    )

    return bool(response and response.ok)


def send_document_to_telegram(
    file_bytes,
    filename="file",
    content_type="application/octet-stream",
    caption=None
):
    if not TELEGRAM_TOKEN:
        logger.error("CANNOT SEND DOCUMENT TO TELEGRAM: TOKEN MISSING")
        return False

    if not TELEGRAM_CHAT_ID:
        logger.error("CANNOT SEND DOCUMENT TO TELEGRAM: CHAT ID MISSING")
        return False

    files = {
        "document": (
            filename,
            file_bytes,
            content_type or "application/octet-stream"
        )
    }

    data = {
        "chat_id": TELEGRAM_CHAT_ID
    }

    if caption:
        data["caption"] = caption[:1024]

    response = telegram_request(
        "sendDocument",
        params=data,
        files=files,
        timeout=60
    )

    return bool(response and response.ok)


def send_audio_to_telegram(
    file_bytes,
    filename="audio.ogg",
    content_type="audio/ogg",
    caption=None
):
    if not TELEGRAM_TOKEN:
        logger.error("CANNOT SEND AUDIO TO TELEGRAM: TOKEN MISSING")
        return False

    if not TELEGRAM_CHAT_ID:
        logger.error("CANNOT SEND AUDIO TO TELEGRAM: CHAT ID MISSING")
        return False

    files = {
        "audio": (
            filename,
            file_bytes,
            content_type or "audio/ogg"
        )
    }

    data = {
        "chat_id": TELEGRAM_CHAT_ID
    }

    if caption:
        data["caption"] = caption[:1024]

    response = telegram_request(
        "sendAudio",
        params=data,
        files=files,
        timeout=60
    )

    return bool(response and response.ok)


# ============================================================
# DOWNLOAD FILE FROM TELEGRAM
# ============================================================

def download_telegram_file(file_id):
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM TOKEN IS MISSING")
        return None, None

    get_file_url = (
        TELEGRAM_API
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

        logger.info(
            "TELEGRAM getFile STATUS: %s",
            response.status_code
        )

        logger.info(
            "TELEGRAM getFile RESPONSE: %s",
            response.text[:2000]
        )

        if not response.ok:
            return None, None

        data = safe_json(response)

        if not data or not data.get("ok"):
            return None, None

        file_path = (
            data.get("result", {})
            .get("file_path")
        )

        if not file_path:
            logger.error("TELEGRAM FILE PATH NOT FOUND")
            return None, None

        download_url = (
            TELEGRAM_API
            + "/"
            + file_path
        )

        file_response = requests.get(
            download_url,
            timeout=60
        )

        logger.info(
            "TELEGRAM FILE DOWNLOAD STATUS: %s",
            file_response.status_code
        )

        if not file_response.ok:
            logger.error(
                "TELEGRAM FILE DOWNLOAD FAILED: %s",
                file_response.text[:1000]
            )
            return None, None

        return file_response.content, file_path

    except Exception:
        logger.exception(
            "TELEGRAM FILE DOWNLOAD ERROR"
        )

        return None, None


# ============================================================
# MAX API
# ============================================================

def send_text_to_max(text, sender_name):
    if not MAX_TOKEN or not MAX_CHAT_ID:
        logger.error(
            "MAX TEXT NOT SENT: missing credentials"
        )
        return False

    url = (
        MAX_API
        + "/messages"
        + "?chat_id="
        + str(int(MAX_CHAT_ID))
    )

    message_text = (
        "Telegram → MAX\n"
        "👤 "
        + sender_name
        + "\n"
        + (text or "")
    )

    # MAX text limit = 4000 characters.
    chunks = [
        message_text[i:i + 3900]
        for i in range(0, len(message_text), 3900)
    ]

    success = True

    for chunk in chunks:
        payload = {
            "text": chunk
        }

        try:
            response = requests.post(
                url,
                headers=max_headers(),
                json=payload,
                timeout=30,
                verify=MAX_CA_BUNDLE
            )

            logger.info(
                "MAX TEXT RESPONSE STATUS: %s",
                response.status_code
            )

            logger.info(
                "MAX TEXT RESPONSE: %s",
                response.text[:3000]
            )

            if not response.ok:
                success = False

        except Exception:
            logger.exception(
                "MAX TEXT ERROR"
            )
            success = False

    return success


# ============================================================
# MAX MEDIA UPLOAD
# ============================================================

def upload_file_to_max(
    file_bytes,
    content_type,
    media_type,
    filename
):
    """
    media_type:
        image
        audio
        video
        file
    """

    if not MAX_TOKEN:
        logger.error(
            "MAX UPLOAD FAILED: MAX_TOKEN missing"
        )
        return None

    if not file_bytes:
        logger.error(
            "MAX UPLOAD FAILED: empty file"
        )
        return None

    upload_init_url = (
        MAX_API
        + "/uploads"
        + "?type="
        + media_type
    )

    try:
        # STEP 1:
        # Получаем URL для загрузки.
        init_response = requests.post(
            upload_init_url,
            headers={
                "Authorization": MAX_TOKEN
            },
            timeout=30,
            verify=MAX_CA_BUNDLE
        )

        logger.info(
            "MAX %s UPLOAD INIT STATUS: %s",
            media_type.upper(),
            init_response.status_code
        )

        logger.info(
            "MAX %s UPLOAD INIT RESPONSE: %s",
            media_type.upper(),
            init_response.text[:3000]
        )

        if not init_response.ok:
            logger.error(
                "MAX %s UPLOAD INIT FAILED",
                media_type.upper()
            )
            return None

        init_data = safe_json(init_response)

        if not isinstance(init_data, dict):
            logger.error(
                "MAX UPLOAD INIT RESPONSE IS NOT JSON"
            )
            return None

        upload_url = init_data.get("url")

        # Иногда token может уже прийти здесь.
        token = init_data.get("token")

        if not upload_url:
            logger.error(
                "MAX UPLOAD URL NOT FOUND: %s",
                init_data
            )
            return None

        # STEP 2:
        # Загружаем сам файл.
        files = {
            "data": (
                filename,
                file_bytes,
                content_type or "application/octet-stream"
            )
        }

        upload_response = requests.post(
            upload_url,
            files=files,
            timeout=120
        )

        logger.info(
            "MAX %s FILE UPLOAD STATUS: %s",
            media_type.upper(),
            upload_response.status_code
        )

        logger.info(
            "MAX %s FILE UPLOAD RESPONSE: %s",
            media_type.upper(),
            upload_response.text[:3000]
        )

        if not upload_response.ok:
            logger.error(
                "MAX %s FILE UPLOAD FAILED",
                media_type.upper()
            )
            return None

        upload_data = safe_json(upload_response)

        if isinstance(upload_data, dict):
            token = (
                upload_data.get("token")
                or token
            )

        if not token:
            logger.error(
                "MAX %s TOKEN NOT FOUND",
                media_type.upper()
            )
            return None

        logger.info(
            "MAX %s TOKEN RECEIVED",
            media_type.upper()
        )

        return token

    except Exception:
        logger.exception(
            "MAX %s UPLOAD ERROR",
            media_type.upper()
        )

        return None


# ============================================================
# SEND MEDIA TO MAX
# ============================================================

def send_media_to_max(
    file_bytes,
    content_type,
    media_type,
    filename,
    caption,
    sender_name
):
    if not MAX_TOKEN or not MAX_CHAT_ID:
        logger.error(
            "MAX MEDIA NOT SENT: credentials missing"
        )
        return False

    logger.info(
        "STARTING MAX %s SEND: %s bytes",
        media_type.upper(),
        len(file_bytes)
    )

    token = upload_file_to_max(
        file_bytes=file_bytes,
        content_type=content_type,
        media_type=media_type,
        filename=filename
    )

    if not token:
        logger.error(
            "MAX MEDIA TOKEN NOT RECEIVED"
        )
        return False

    message_url = (
        MAX_API
        + "/messages"
        + "?chat_id="
        + str(int(MAX_CHAT_ID))
    )

    message_text = (
        "Telegram → MAX\n"
        "👤 "
        + sender_name
    )

    if caption:
        message_text += "\n" + caption

    payload = {
        "text": message_text,
        "attachments": [
            {
                "type": media_type,
                "payload": {
                    "token": token
                }
            }
        ]
    }

    try:
        response = requests.post(
            message_url,
            headers=max_headers(),
            json=payload,
            timeout=30,
            verify=MAX_CA_BUNDLE
        )

        logger.info(
            "MAX %s MESSAGE STATUS: %s",
            media_type.upper(),
            response.status_code
        )

        logger.info(
            "MAX %s MESSAGE RESPONSE: %s",
            media_type.upper(),
            response.text[:3000]
        )

        return response.ok

    except Exception:
        logger.exception(
            "MAX %s MESSAGE ERROR",
            media_type.upper()
        )

        return False


# ============================================================
# TELEGRAM WEBHOOK
# ============================================================

@app.route("/telegram-webhook", methods=["POST"])
def telegram_webhook():
    try:
        update = request.get_json(
            silent=True
        )

        logger.info(
            "========== TELEGRAM WEBHOOK =========="
        )

        logger.info(
            "TELEGRAM UPDATE: %s",
            update
        )

        if not isinstance(update, dict):
            return jsonify({
                "ok": False,
                "error": "invalid json"
            }), 400

        message = update.get("message")

        if not isinstance(message, dict):
            logger.info(
                "TELEGRAM UPDATE HAS NO MESSAGE"
            )
            return jsonify({
                "ok": True
            }), 200

        sender_name = get_telegram_sender_name(
            message
        )

        # ----------------------------------------------------
        # TEXT
        # ----------------------------------------------------

        text = message.get("text")

        if text:
            logger.info(
                "TELEGRAM TEXT FROM %s: %s",
                sender_name,
                text
            )

            send_text_to_max(
                text=text,
                sender_name=sender_name
            )

            return jsonify({
                "ok": True
            }), 200

        # ----------------------------------------------------
        # PHOTO
        # ----------------------------------------------------

        if message.get("photo"):
            photos = message.get("photo")

            if isinstance(photos, list) and photos:
                photo = photos[-1]

                file_id = photo.get("file_id")

                if file_id:
                    logger.info(
                        "TELEGRAM PHOTO FROM %s",
                        sender_name
                    )

                    file_bytes, file_path = (
                        download_telegram_file(
                            file_id
                        )
                    )

                    if file_bytes:
                        caption = (
                            message.get("caption")
                        )

                        send_media_to_max(
                            file_bytes=file_bytes,
                            content_type="image/jpeg",
                            media_type="image",
                            filename="telegram_photo.jpg",
                            caption=caption,
                            sender_name=sender_name
                        )

            return jsonify({
                "ok": True
            }), 200

        # ----------------------------------------------------
        # VOICE
        # ----------------------------------------------------

        if message.get("voice"):
            voice = message.get("voice")

            file_id = voice.get("file_id")

            if file_id:
                logger.info(
                    "TELEGRAM VOICE FROM %s",
                    sender_name
                )

                file_bytes, file_path = (
                    download_telegram_file(
                        file_id
                    )
                )

                if file_bytes:
                    send_media_to_max(
                        file_bytes=file_bytes,
                        content_type="audio/ogg",
                        media_type="audio",
                        filename="telegram_voice.ogg",
                        caption=None,
                        sender_name=sender_name
                    )

            return jsonify({
                "ok": True
            }), 200

        # ----------------------------------------------------
        # AUDIO
        # ----------------------------------------------------

        if message.get("audio"):
            audio = message.get("audio")

            file_id = audio.get("file_id")

            if file_id:
                logger.info(
                    "TELEGRAM AUDIO FROM %s",
                    sender_name
                )

                file_bytes, file_path = (
                    download_telegram_file(
                        file_id
                    )
                )

                if file_bytes:
                    filename = (
                        audio.get("file_name")
                        or "telegram_audio"
                    )

                    content_type = (
                        audio.get("mime_type")
                        or "audio/mpeg"
                    )

                    send_media_to_max(
                        file_bytes=file_bytes,
                        content_type=content_type,
                        media_type="audio",
                        filename=filename,
                        caption=None,
                        sender_name=sender_name
                    )

            return jsonify({
                "ok": True
            }), 200

        # ----------------------------------------------------
        # DOCUMENT
        # ----------------------------------------------------

        if message.get("document"):
            document = message.get("document")

            file_id = document.get("file_id")

            if file_id:
                logger.info(
                    "TELEGRAM DOCUMENT FROM %s",
                    sender_name
                )

                file_bytes, file_path = (
                    download_telegram_file(
                        file_id
                    )
                )

                if file_bytes:
                    filename = (
                        document.get("file_name")
                        or "telegram_file"
                    )

                    content_type = (
                        document.get("mime_type")
                        or "application/octet-stream"
                    )

                    send_media_to_max(
                        file_bytes=file_bytes,
                        content_type=content_type,
                        media_type="file",
                        filename=filename,
                        caption=message.get("caption"),
                        sender_name=sender_name
                    )

            return jsonify({
                "ok": True
            }), 200

        logger.info(
            "TELEGRAM MESSAGE TYPE NOT SUPPORTED"
        )

        return jsonify({
            "ok": True
        }), 200

    except Exception:
        logger.exception(
            "TELEGRAM WEBHOOK INTERNAL ERROR"
        )

        # Очень важно:
        # Telegram должен получить 200,
        # иначе он будет повторно присылать update.
        return jsonify({
            "ok": False
        }), 200


# ============================================================
# MAX WEBHOOK
# ============================================================

@app.route("/max-webhook", methods=["POST"])
def max_webhook():
    logger.info(
        "========== MAX WEBHOOK =========="
    )

    # --------------------------------------------------------
    # SECRET CHECK
    # --------------------------------------------------------

    if MAX_WEBHOOK_SECRET:
        received_secret = request.headers.get(
            "X-Max-Bot-Api-Secret"
        )

        if received_secret != MAX_WEBHOOK_SECRET:
            logger.error(
                "MAX WEBHOOK SECRET MISMATCH"
            )

            return jsonify({
                "ok": False,
                "error": "unauthorized"
            }), 401

    try:
        update = request.get_json(
            silent=True
        )

        logger.info(
            "MAX UPDATE: %s",
            update
        )

        if not isinstance(update, dict):
            logger.error(
                "MAX WEBHOOK INVALID JSON"
            )

            return jsonify({
                "ok": False
            }), 400

        update_type = update.get(
            "update_type"
        )

        logger.info(
            "MAX UPDATE TYPE: %s",
            update_type
        )

        # ----------------------------------------------------
        # ONLY NEW MESSAGES
        # ----------------------------------------------------

        if update_type != "message_created":
            logger.info(
                "MAX EVENT IGNORED: %s",
                update_type
            )

            return jsonify({
                "ok": True
            }), 200

        message = update.get("message")

        if not isinstance(message, dict):
            logger.info(
                "MAX UPDATE HAS NO MESSAGE OBJECT"
            )

            return jsonify({
                "ok": True
            }), 200

        sender = message.get("sender", {})

        sender_name = get_max_sender_name(
            sender
        )

        body = message.get("body") or {}

        text = body.get("text")

        # ----------------------------------------------------
        # TEXT
        # ----------------------------------------------------

        if text:
            telegram_text = (
                "MAX → Telegram\n"
                "👤 "
                + sender_name
                + "\n"
                + text
            )

            logger.info(
                "MAX TEXT FROM %s: %s",
                sender_name,
                text
            )

            send_text_to_telegram(
                telegram_text
            )

        # ----------------------------------------------------
        # ATTACHMENTS
        # ----------------------------------------------------

        attachments = body.get(
            "attachments"
        )

        if not isinstance(attachments, list):
            attachments = []

        logger.info(
            "MAX ATTACHMENTS COUNT: %s",
            len(attachments)
        )

        for attachment in attachments:

            if not isinstance(attachment, dict):
                continue

            attachment_type = attachment.get(
                "type"
            )

            payload = attachment.get(
                "payload"
            ) or {}

            logger.info(
                "MAX ATTACHMENT TYPE: %s",
                attachment_type
            )

            # ------------------------------------------------
            # IMAGE
            # ------------------------------------------------

            if attachment_type == "image":
                image_url = (
                    payload.get("url")
                    or payload.get("download_url")
                    or payload.get("file_url")
                )

                if image_url:
                    try:
                        image_response = requests.get(
                            image_url,
                            timeout=60
                        )

                        if image_response.ok:
                            send_photo_to_telegram(
                                file_bytes=image_response.content,
                                filename="max_image.jpg",
                                content_type=(
                                    image_response.headers.get(
                                        "Content-Type"
                                    )
                                    or "image/jpeg"
                                ),
                                caption=(
                                    "MAX → Telegram\n"
                                    "👤 "
                                    + sender_name
                                )
                            )

                        else:
                            logger.error(
                                "MAX IMAGE DOWNLOAD FAILED: %s",
                                image_response.status_code
                            )

                    except Exception:
                        logger.exception(
                            "MAX IMAGE DOWNLOAD ERROR"
                        )

                else:
                    logger.warning(
                        "MAX IMAGE HAS NO DOWNLOADABLE URL"
                    )

            # ------------------------------------------------
            # AUDIO
            # ------------------------------------------------

            elif attachment_type == "audio":
                audio_url = (
                    payload.get("url")
                    or payload.get("download_url")
                    or payload.get("file_url")
                )

                if audio_url:
                    try:
                        audio_response = requests.get(
                            audio_url,
                            timeout=120
                        )

                        if audio_response.ok:
                            send_audio_to_telegram(
                                file_bytes=audio_response.content,
                                filename="max_audio",
                                content_type=(
                                    audio_response.headers.get(
                                        "Content-Type"
                                    )
                                    or "audio/mpeg"
                                ),
                                caption=(
                                    "MAX → Telegram\n"
                                    "👤 "
                                    + sender_name
                                )
                            )

                    except Exception:
                        logger.exception(
                            "MAX AUDIO DOWNLOAD ERROR"
                        )

                else:
                    logger.warning(
                        "MAX AUDIO HAS NO DOWNLOADABLE URL"
                    )

            # ------------------------------------------------
            # FILE
            # ------------------------------------------------

            elif attachment_type == "file":
                file_url = (
                    payload.get("url")
                    or payload.get("download_url")
                    or payload.get("file_url")
                )

                if file_url:
                    try:
                        file_response = requests.get(
                            file_url,
                            timeout=120
                        )

                        if file_response.ok:
                            send_document_to_telegram(
                                file_bytes=file_response.content,
                                filename="max_file",
                                content_type=(
                                    file_response.headers.get(
                                        "Content-Type"
                                    )
                                    or "application/octet-stream"
                                ),
                                caption=(
                                    "MAX → Telegram\n"
                                    "👤 "
                                    + sender_name
                                )
                            )

                    except Exception:
                        logger.exception(
                            "MAX FILE DOWNLOAD ERROR"
                        )

                else:
                    logger.warning(
                        "MAX FILE HAS NO DOWNLOADABLE URL"
                    )

            else:
                logger.info(
                    "MAX ATTACHMENT TYPE NOT FORWARDED: %s",
                    attachment_type
                )

        return jsonify({
            "ok": True
        }), 200

    except Exception:
        logger.exception(
            "MAX WEBHOOK INTERNAL ERROR"
        )

        # MAX требует HTTP 200 в течение 30 секунд.
        return jsonify({
            "ok": False
        }), 200


# ============================================================
# SET MAX WEBHOOK
# ============================================================

@app.route("/setup-max-webhook", methods=["GET"])
def setup_max_webhook():
    """
    Открываешь эту страницу один раз после деплоя.

    Она создаёт подписку MAX на:
    message_created
    bot_started
    """

    if not MAX_TOKEN:
        return jsonify({
            "ok": False,
            "error": "MAX_TOKEN is missing"
        }), 500

    if not APP_URL:
        return jsonify({
            "ok": False,
            "error": "APP_URL is missing"
        }), 500

    webhook_url = (
        APP_URL.rstrip("/")
        + "/max-webhook"
    )

    payload = {
        "url": webhook_url,
        "update_types": [
            "message_created",
            "bot_started"
        ]
    }

    if MAX_WEBHOOK_SECRET:
        payload["secret"] = MAX_WEBHOOK_SECRET

    try:
        response = requests.post(
            MAX_API + "/subscriptions",
            headers=max_headers(),
            json=payload,
            timeout=30,
            verify=MAX_CA_BUNDLE
        )

        logger.info(
            "MAX WEBHOOK SETUP STATUS: %s",
            response.status_code
        )

        logger.info(
            "MAX WEBHOOK SETUP RESPONSE: %s",
            response.text[:3000]
        )

        return jsonify({
            "status_code": response.status_code,
            "response": safe_json(response)
                if safe_json(response) is not None
                else response.text,
            "webhook_url": webhook_url
        }), response.status_code

    except Exception as exc:
        logger.exception(
            "MAX WEBHOOK SETUP ERROR"
        )

        return jsonify({
            "ok": False,
            "error": str(exc)
        }), 500


# ============================================================
# SHOW MAX WEBHOOK SUBSCRIPTIONS
# ============================================================

@app.route("/max-webhook-info", methods=["GET"])
def max_webhook_info():

    if not MAX_TOKEN:
        return jsonify({
            "ok": False,
            "error": "MAX_TOKEN is missing"
        }), 500

    try:
        response = requests.get(
            MAX_API + "/subscriptions",
            headers={
                "Authorization": MAX_TOKEN
            },
            timeout=30,
            verify=MAX_CA_BUNDLE
        )

        logger.info(
            "MAX SUBSCRIPTIONS STATUS: %s",
            response.status_code
        )

        logger.info(
            "MAX SUBSCRIPTIONS RESPONSE: %s",
            response.text[:5000]
        )

        data = safe_json(response)

        return jsonify(
            data
            if data is not None
            else {
                "response": response.text
            }
        ), response.status_code

    except Exception as exc:
        logger.exception(
            "MAX SUBSCRIPTIONS ERROR"
        )

        return jsonify({
            "ok": False,
            "error": str(exc)
        }), 500


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    port = int(
        os.getenv(
            "PORT",
            "10000"
        )
    )

    logger.info(
        "========================================"
    )

    logger.info(
        "TELEGRAM MAX BRIDGE STARTING"
    )

    logger.info(
        "PORT: %s",
        port
    )

    logger.info(
        "TELEGRAM TOKEN: %s",
        "OK" if TELEGRAM_TOKEN else "MISSING"
    )

    logger.info(
        "MAX TOKEN: %s",
        "OK" if MAX_TOKEN else "MISSING"
    )

    logger.info(
        "TELEGRAM CHAT ID: %s",
        TELEGRAM_CHAT_ID
    )

    logger.info(
        "MAX CHAT ID: %s",
        MAX_CHAT_ID
    )

    logger.info(
        "APP URL: %s",
        APP_URL
    )

    logger.info(
        "MAX WEBHOOK SECRET: %s",
        "OK" if MAX_WEBHOOK_SECRET else "MISSING"
    )

    logger.info(
        "MAX CA BUNDLE: %s",
        MAX_CA_BUNDLE
    )

    logger.info(
        "========================================"
    )

    app.run(
        host="0.0.0.0",
        port=port
            )
