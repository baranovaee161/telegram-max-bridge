import os
import time
import logging
import requests
import urllib3

from flask import Flask, request, jsonify


# =========================================================
# SSL
# =========================================================

urllib3.disable_warnings(
    urllib3.exceptions.InsecureRequestWarning
)


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

PUBLIC_URL = (
    os.getenv("TELEGRAM_WEBHOOK_URL")
    or os.getenv("RENDER_EXTERNAL_URL")
    or ""
).rstrip("/")

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

logging.info(
    "PUBLIC_URL: %s",
    PUBLIC_URL if PUBLIC_URL else "NOT SET"
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
        "max_chat_id": MAX_CHAT_ID,
        "public_url": PUBLIC_URL
    }), 200


# =========================================================
# TELEGRAM API
# =========================================================

def telegram_api(
    method,
    data=None,
    files=None
):

    if not TELEGRAM_TOKEN:

        logging.error(
            "TELEGRAM_TOKEN is not configured"
        )

        return None

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_TOKEN}/{method}"
    )

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
            response.text[:2000]
        )

        if not response.ok:

            return None

        return response.json()

    except Exception:

        logging.exception(
            "Telegram API error"
        )

        return None


# =========================================================
# TELEGRAM WEBHOOK INFO
# =========================================================

def get_telegram_webhook_info():

    if not TELEGRAM_TOKEN:

        logging.error(
            "Cannot check Telegram webhook: token missing"
        )

        return None

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_TOKEN}/getWebhookInfo"
    )

    try:

        response = requests.get(
            url,
            timeout=30
        )

        logging.info(
            "Telegram getWebhookInfo -> %s %s",
            response.status_code,
            response.text[:5000]
        )

        if not response.ok:

            return None

        return response.json()

    except Exception:

        logging.exception(
            "Telegram getWebhookInfo error"
        )

        return None


# =========================================================
# SET TELEGRAM WEBHOOK
# =========================================================

def setup_telegram_webhook():

    if not TELEGRAM_TOKEN:

        logging.error(
            "Telegram webhook NOT configured: "
            "TELEGRAM_TOKEN missing"
        )

        return False

    if not PUBLIC_URL:

        logging.warning(
            "PUBLIC_URL is not configured."
        )

        logging.warning(
            "Telegram webhook cannot be registered."
        )

        logging.warning(
            "Set TELEGRAM_WEBHOOK_URL or use "
            "RENDER_EXTERNAL_URL."
        )

        get_telegram_webhook_info()

        return False

    webhook_url = (
        f"{PUBLIC_URL}/telegram/webhook"
    )

    logging.info(
        "Setting Telegram webhook: %s",
        webhook_url
    )

    try:

        response = requests.post(
            f"https://api.telegram.org/"
            f"bot{TELEGRAM_TOKEN}/setWebhook",
            data={
                "url": webhook_url,
                "drop_pending_updates": False
            },
            timeout=30
        )

        logging.info(
            "Telegram setWebhook -> %s %s",
            response.status_code,
            response.text[:5000]
        )

        if not response.ok:

            return False

        result = response.json()

        if not result.get("ok"):

            logging.error(
                "Telegram setWebhook failed: %s",
                result
            )

            return False

        logging.info(
            "Telegram webhook successfully configured"
        )

        time.sleep(1)

        get_telegram_webhook_info()

        return True

    except Exception:

        logging.exception(
            "Telegram webhook setup error"
        )

        return False


# =========================================================
# TELEGRAM SEND TEXT
# =========================================================

def send_telegram_text(text):

    if not TELEGRAM_CHAT_ID:

        logging.error(
            "TELEGRAM_CHAT_ID is not configured"
        )

        return False

    result = telegram_api(
        "sendMessage",
        data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text
        }
    )

    return bool(
        result and result.get("ok")
    )


# =========================================================
# TELEGRAM SEND PHOTO
# =========================================================

def send_telegram_photo(
    photo_bytes,
    filename="photo.jpg",
    caption=None
):

    if not TELEGRAM_CHAT_ID:

        logging.error(
            "TELEGRAM_CHAT_ID is not configured"
        )

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

    return bool(
        result and result.get("ok")
    )


# =========================================================
# TELEGRAM SEND VOICE
# =========================================================

def send_telegram_voice(
    audio_bytes,
    filename="voice.ogg"
):

    if not TELEGRAM_CHAT_ID:

        logging.error(
            "TELEGRAM_CHAT_ID is not configured"
        )

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

    return bool(
        result and result.get("ok")
    )


# =========================================================
# TELEGRAM SEND DOCUMENT
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

    file_path = (
        result["result"].get(
            "file_path"
        )
    )

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

    url = (
        f"{MAX_API}{endpoint}"
    )

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
            verify=False,
            **kwargs
        )

        logging.info(
            "MAX API %s %s -> %s %s",
            method,
            endpoint,
            response.status_code,
            response.text[:3000]
        )

        if not response.ok:

            logging.error(
                "MAX API returned HTTP %s",
                response.status_code
            )

            return None

        if not response.text:

            return {}

        try:

            return response.json()

        except Exception:

            logging.warning(
                "MAX API response is not JSON"
            )

            return {}

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

        chat_id = int(
            MAX_CHAT_ID
        )

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
# NORMALIZE MAX FILENAME
# =========================================================

def normalize_max_filename(
    filename,
    file_type
):

    if not filename:

        if file_type == "audio":
            return "audio.ogg"

        if file_type == "image":
            return "image.jpg"

        if file_type == "video":
            return "video.mp4"

        return "file"

    filename = os.path.basename(
        filename
    )

    lower_name = filename.lower()

    # -----------------------------------------------------
    # Telegram voice часто приходит как .oga.
    #
    # Сам файл при этом является OGG/Opus.
    # MAX может отклонять расширение .oga.
    # Передаём его как .ogg.
    # -----------------------------------------------------

    if file_type == "audio":

        if lower_name.endswith(".oga"):

            filename = (
                filename[:-4]
                + ".ogg"
            )

        elif not (
            lower_name.endswith(".ogg")
            or lower_name.endswith(".mp3")
            or lower_name.endswith(".wav")
            or lower_name.endswith(".m4a")
            or lower_name.endswith(".aac")
            or lower_name.endswith(".opus")
        ):

            filename += ".ogg"

    # -----------------------------------------------------
    # IMAGE
    # -----------------------------------------------------

    if file_type == "image":

        if not (
            lower_name.endswith(".jpg")
            or lower_name.endswith(".jpeg")
            or lower_name.endswith(".png")
            or lower_name.endswith(".gif")
            or lower_name.endswith(".bmp")
            or lower_name.endswith(".tiff")
            or lower_name.endswith(".heic")
        ):

            filename += ".jpg"

    # -----------------------------------------------------
    # VIDEO
    # -----------------------------------------------------

    if file_type == "video":

        if not (
            lower_name.endswith(".mp4")
            or lower_name.endswith(".mov")
            or lower_name.endswith(".mkv")
            or lower_name.endswith(".webm")
        ):

            filename += ".mp4"

    return filename


# =========================================================
# MAX UPLOAD
# =========================================================

def upload_to_max(
    file_bytes,
    file_type,
    filename
):

    if not MAX_TOKEN:

        logging.error(
            "MAX_TOKEN is not configured"
        )

        return None

    # -----------------------------------------------------
    # Нормализуем имя файла
    # -----------------------------------------------------

    original_filename = filename

    filename = normalize_max_filename(
        filename,
        file_type
    )

    logging.info(
        "MAX upload filename: %s -> %s",
        original_filename,
        filename
    )

    try:

        # -------------------------------------------------
        # STEP 1
        # Получаем URL загрузки
        # -------------------------------------------------

        response = requests.post(
            f"{MAX_API}/uploads",
            headers=max_headers(),
            params={
                "type": file_type
            },
            timeout=60,
            verify=False
        )

        logging.info(
            "MAX upload initialization -> %s %s",
            response.status_code,
            response.text[:3000]
        )

        if not response.ok:

            logging.error(
                "MAX upload initialization FAILED"
            )

            return None

        upload_data = response.json()

        upload_url = (
            upload_data.get("url")
        )

        initial_token = (
            upload_data.get("token")
        )

        if not upload_url:

            logging.error(
                "MAX upload URL missing: %s",
                upload_data
            )

            return None

        logging.info(
            "MAX upload URL received"
        )

        # -------------------------------------------------
        # STEP 2
        # Загружаем сам файл.
        #
        # ВАЖНО:
        # Не задаём Content-Type вручную.
        # requests сам создаёт правильный
        # multipart/form-data boundary.
        # -------------------------------------------------

        mime_type = "application/octet-stream"

        if file_type == "audio":

            mime_type = "audio/ogg"

        elif file_type == "image":

            mime_type = "image/jpeg"

            lower_filename = filename.lower()

            if lower_filename.endswith(".png"):
                mime_type = "image/png"

            elif lower_filename.endswith(".gif"):
                mime_type = "image/gif"

            elif lower_filename.endswith(".webp"):
                mime_type = "image/webp"

        elif file_type == "video":

            mime_type = "video/mp4"

        upload_response = requests.post(
            upload_url,

            files={
                "data": (
                    filename,
                    file_bytes,
                    mime_type
                )
            },

            timeout=120,

            verify=False
        )

        logging.info(
            "MAX file upload -> %s %s",
            upload_response.status_code,
            upload_response.text[:5000]
        )

        if not upload_response.ok:

            logging.error(
                "MAX file upload FAILED"
            )

            return None

        # -------------------------------------------------
        # STEP 3
        # Получаем token
        # -------------------------------------------------

        try:

            upload_result = (
                upload_response.json()
            )

        except Exception:

            logging.error(
                "MAX file upload returned "
                "non-JSON response: %s",
                upload_response.text[:5000]
            )

            return None

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

        chat_id = int(
            MAX_CHAT_ID
        )

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
    # MAX может ещё обрабатывать файл после upload.
    # Поэтому делаем несколько попыток.
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

    # -----------------------------------------------------
    # Telegram voice .oga -> MAX .ogg
    # -----------------------------------------------------

    filename = normalize_max_filename(
        filename,
        "audio"
    )

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

    if not isinstance(
        sender,
        dict
    ):

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
        "========================================"
    )

    logging.info(
        "TELEGRAM -> MAX"
    )

    logging.info(
        "Telegram sender: %s",
        sender_name
    )

    logging.info(
        "Telegram message keys: %s",
        list(message.keys())
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

            file_id = (
                largest_photo.get(
                    "file_id"
                )
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

                    send_max_text(
                        f"📷 {sender_name} "
                        f"отправил(а) фото:"
                    )

                    send_max_image(
                        file_bytes,
                        filename
                    )

                else:

                    logging.error(
                        "Telegram photo download FAILED"
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

                    # -----------------------------------------
                    # ВАЖНО:
                    # Telegram обычно даёт file_XX.oga.
                    # Для MAX принудительно используем .ogg.
                    # -----------------------------------------

                    if filename.lower().endswith(".oga"):

                        filename = (
                            filename[:-4]
                            + ".ogg"
                        )

                    logging.info(
                        "Telegram -> MAX VOICE: %s",
                        filename
                    )

                    send_max_text(
                        f"🎤 {sender_name} "
                        f"отправил(а) голосовое:"
                    )

                    send_max_audio(
                        file_bytes,
                        filename
                    )

                else:

                    logging.error(
                        "Telegram voice download FAILED"
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
                        f"🎵 {sender_name} "
                        f"отправил(а) аудио:"
                    )

                    send_max_audio(
                        file_bytes,
                        filename
                    )

                else:

                    logging.error(
                        "Telegram audio download FAILED"
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

            file_id = (
                document.get(
                    "file_id"
                )
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
                        f"📎 {sender_name} "
                        f"отправил(а) файл:"
                    )

                    send_max_file(
                        file_bytes,
                        filename
                    )

                else:

                    logging.error(
                        "Telegram document download FAILED"
                    )

        except Exception:

            logging.exception(
                "Error processing Telegram document"
            )

    logging.info(
        "========================================"
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
        "========================================"
    )

    logging.info(
        "===== TELEGRAM WEBHOOK RECEIVED ====="
    )

    try:

        update = request.get_json(
            silent=True
        )

        logging.info(
            "Telegram update: %s",
            str(update)[:15000]
        )

        if not update:

            logging.warning(
                "Telegram webhook received EMPTY update"
            )

            return jsonify({
                "ok": True
            }), 200

        # -------------------------------------------------
        # ОБЫЧНОЕ СООБЩЕНИЕ
        # -------------------------------------------------

        message = update.get(
            "message"
        )

        if message:

            handle_telegram_message(
                message
            )

        # -------------------------------------------------
        # CHANNEL POST
        # -------------------------------------------------

        channel_post = update.get(
            "channel_post"
        )

        if channel_post:

            logging.info(
                "Telegram channel_post received"
            )

            handle_telegram_message(
                channel_post
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

    if username:

        if str(username).startswith("@"):

            return str(username)

        return f"@{username}"

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

    if name:

        return name

    if user_id:

        return f"MAX ID {user_id}"

    return "Пользователь MAX"


# =========================================================
# MAX -> TELEGRAM
#
# ЭТУ ЧАСТЬ НЕ ТРОГАЕМ ПО ЛОГИКЕ.
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
                            f"📎 {sender_name} "
                            f"отправил(а) файл:"
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

    # -----------------------------------------------------
    # Telegram webhook
    # -----------------------------------------------------

    setup_telegram_webhook()

    # -----------------------------------------------------
    # START FLASK
    # -----------------------------------------------------

    app.run(
        host="0.0.0.0",
        port=port
                )
