import os
import time
import json
import logging
import requests
import urllib3

from flask import Flask, request, jsonify


# =========================================================
# ЧТО НОВОГО В ЭТОЙ ВЕРСИИ (правки от Claude)
# =========================================================
#
# 1. ИСПРАВЛЕН REPLY Telegram -> MAX.
#    Раньше поле `link` при отправке в MAX API отправлялось как
#    {"type": "reply", "message": {"mid": ...}} — MAX не понимает
#    такой формат и молча его игнорирует. По официальной схеме
#    MAX (dev.max.ru/docs-api) правильный формат:
#        {"type": "reply", "mid": "..."}
#    Из-за этого свайп-ответ в Telegram долетал до MAX как обычное
#    сообщение, без привязки к исходному. Теперь исправлено и в
#    send_max_text(), и в send_max_attachment() — обе стороны
#    (MAX -> Telegram и Telegram -> MAX) должны работать одинаково.
#
# 2. ИСПРАВЛЕНО ЧТЕНИЕ СОБЫТИЯ message_removed (MAX -> Telegram).
#    По официальной схеме MAX update `message_removed` содержит
#    поля message_id / chat_id / user_id ПРЯМО В КОРНЕ события,
#    а не внутри message.body.mid. Раньше код перебирал
#    несуществующие пути и только случайно попадал в нужное поле
#    через fallback. Теперь читаем поле напрямую и дополнительно
#    сверяем chat_id, чтобы не среагировать на чужой чат.
#
# 3. УДАЛЕНИЕ Telegram -> MAX: ПРИНЦИПИАЛЬНО НЕВОЗМОЖНО через
#    Bot API. Telegram в принципе не уведомляет ботов о том, что
#    пользователь удалил своё сообщение (в отличие от MAX, который
#    шлёт update message_removed). Обойти это можно только заменив
#    Telegram-бота на пользовательскую сессию (Telethon/Pyrogram
#    с входом по номеру телефона вместо токена бота) — это другая
#    архитектура и другие риски по ToS Telegram, здесь НЕ реализовано.
#
# 4. АВАТАРКИ.
#    Ни Telegram, ни MAX Bot API не позволяют показать картинку
#    "рядом с именем" внутри одного сообщения от лица стороннего
#    человека — это рисует только сам клиент на основе профиля.
#    Поэтому сохранён прежний практический вариант: при первом
#    сообщении от человека за сессию бот один раз пересылает его
#    аватар отдельным фото-сообщением в другой чат. Важно: список
#    "кому уже отправляли" хранится в памяти процесса, поэтому после
#    каждого перезапуска сервера на Render аватар разошлётся заново
#    при следующем сообщении каждого пользователя — это ожидаемо.
#
# =========================================================


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
# АНКЕТА: ВОПРОСЫ И ХРАНИЛИЩЕ
# =========================================================

ANKETA_QUESTIONS = [
    {
        "id": 1,
        "key": "name",
        "text": "👤 Как вас зовут?"
    },
    {
        "id": 2,
        "key": "age",
        "text": "🎂 Сколько вам лет?"
    },
    {
        "id": 3,
        "key": "zodiac",
        "text": "♓ Какой ваш знак зодиака?"
    },
    {
        "id": 4,
        "key": "goal",
        "text": "🎯 Какая ваша цель прихода в этот чат?"
    },
    {
        "id": 5,
        "key": "children",
        "text": "👶 Есть ли у вас дети? (Да/Нет)"
    },
    {
        "id": 6,
        "key": "friendship",
        "text": "💭 Существует ли дружба между мужчиной и женщиной? (Ваше мнение)"
    }
]

# Хранилище пользователей, заполняющих анкету
users_anketa = {}


# =========================================================
# МОСТ: СВЯЗКА ID СООБЩЕНИЙ (для reply и удаления)
# =========================================================

# tg_message_id -> max_message_id
tg_to_max_id = {}

# max_message_id -> tg_message_id
max_to_tg_id = {}


def remember_message_pair(tg_id, max_id):
    """Запоминает пару ID сообщений в обе стороны."""

    if tg_id is not None and max_id is not None:

        tg_to_max_id[tg_id] = max_id
        max_to_tg_id[max_id] = tg_id

        logging.info(
            "Message pair linked: telegram=%s <-> max=%s",
            tg_id,
            max_id
        )


def extract_max_message_id(result):
    """Достаёт ID (mid) отправленного сообщения из ответа MAX API."""

    if not isinstance(result, dict):

        return None

    message = result.get("message", result)

    if not isinstance(message, dict):

        return None

    body = message.get("body", {})

    if isinstance(body, dict) and body.get("mid"):

        return body.get("mid")

    return message.get("mid")


def extract_telegram_message_id(result):
    """Достаёт message_id отправленного сообщения из ответа Telegram API."""

    if not isinstance(result, dict):

        return None

    return result.get("result", {}).get("message_id")


# Кэш: кому уже отправляли аватарку, чтобы не слать её
# на каждое сообщение, а только один раз за время работы сервера.

avatar_sent_telegram_users = set()
avatar_sent_max_users = set()


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
    files=None,
    reply_markup=None
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

    if data is None:
        data = {}

    if reply_markup:
        data["reply_markup"] = reply_markup

    try:

        response = requests.post(
            url,
            data=data,
            files=files,
            timeout=60,
            json=data if reply_markup else None
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


def telegram_reply_parameters_json(reply_to_message_id):
    """
    Для запросов с файлами (multipart/form-data) объектные поля
    нужно передавать JSON-строкой, а не питоновским словарём.
    """

    if not reply_to_message_id:

        return None

    return json.dumps({
        "message_id": reply_to_message_id,
        "allow_sending_without_reply": True
    })


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
# TELEGRAM SEND TEXT WITH BUTTONS
# =========================================================

def send_telegram_text_with_buttons(
    chat_id,
    text,
    buttons=None,
    reply_to_message_id=None
):

    if not TELEGRAM_TOKEN:

        logging.error(
            "TELEGRAM_TOKEN is not configured"
        )

        return None

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_TOKEN}/sendMessage"
    )

    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }

    if buttons:
        data["reply_markup"] = buttons

    if reply_to_message_id:
        data["reply_parameters"] = {
            "message_id": reply_to_message_id,
            "allow_sending_without_reply": True
        }

    try:

        response = requests.post(
            url,
            json=data,
            timeout=60
        )

        logging.info(
            "Telegram sendMessage -> %s",
            response.status_code
        )

        if not response.ok:

            return None

        result = response.json()

        if not result.get("ok"):

            return None

        # Возвращаем полный ответ — из него можно достать
        # result["result"]["message_id"] для связки сообщений.
        return result

    except Exception:

        logging.exception(
            "Telegram sendMessage error"
        )

        return None


# =========================================================
# TELEGRAM SEND TEXT
# =========================================================

def send_telegram_text(text, reply_to_message_id=None):

    if not TELEGRAM_CHAT_ID:

        logging.error(
            "TELEGRAM_CHAT_ID is not configured"
        )

        return None

    return send_telegram_text_with_buttons(
        TELEGRAM_CHAT_ID,
        text,
        None,
        reply_to_message_id=reply_to_message_id
    )


# =========================================================
# TELEGRAM SEND PHOTO
# =========================================================

def send_telegram_photo(
    photo_bytes,
    filename="photo.jpg",
    caption=None,
    reply_to_message_id=None
):

    if not TELEGRAM_CHAT_ID:

        logging.error(
            "TELEGRAM_CHAT_ID is not configured"
        )

        return None

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

    reply_json = telegram_reply_parameters_json(
        reply_to_message_id
    )

    if reply_json:

        data["reply_parameters"] = reply_json

    result = telegram_api(
        "sendPhoto",
        data=data,
        files=files
    )

    if not result or not result.get("ok"):

        return None

    return result


# =========================================================
# TELEGRAM SEND VOICE
# =========================================================

def send_telegram_voice(
    audio_bytes,
    filename="voice.ogg",
    reply_to_message_id=None
):

    if not TELEGRAM_CHAT_ID:

        logging.error(
            "TELEGRAM_CHAT_ID is not configured"
        )

        return None

    files = {
        "voice": (
            filename,
            audio_bytes,
            "audio/ogg"
        )
    }

    data = {
        "chat_id": TELEGRAM_CHAT_ID
    }

    reply_json = telegram_reply_parameters_json(
        reply_to_message_id
    )

    if reply_json:

        data["reply_parameters"] = reply_json

    result = telegram_api(
        "sendVoice",
        data=data,
        files=files
    )

    if not result or not result.get("ok"):

        return None

    return result


# =========================================================
# TELEGRAM SEND DOCUMENT
# =========================================================

def send_telegram_document(
    file_bytes,
    filename="file",
    reply_to_message_id=None
):

    if not TELEGRAM_CHAT_ID:

        logging.error(
            "TELEGRAM_CHAT_ID is not configured"
        )

        return None

    files = {
        "document": (
            filename,
            file_bytes
        )
    }

    data = {
        "chat_id": TELEGRAM_CHAT_ID
    }

    reply_json = telegram_reply_parameters_json(
        reply_to_message_id
    )

    if reply_json:

        data["reply_parameters"] = reply_json

    result = telegram_api(
        "sendDocument",
        data=data,
        files=files
    )

    if not result or not result.get("ok"):

        return None

    return result


# =========================================================
# TELEGRAM SEND VIDEO
# =========================================================

def send_telegram_video(
    video_bytes,
    filename="video.mp4",
    caption=None,
    reply_to_message_id=None
):

    if not TELEGRAM_CHAT_ID:

        logging.error(
            "TELEGRAM_CHAT_ID is not configured"
        )

        return None

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

    reply_json = telegram_reply_parameters_json(
        reply_to_message_id
    )

    if reply_json:

        data["reply_parameters"] = reply_json

    result = telegram_api(
        "sendVideo",
        data=data,
        files=files
    )

    if not result or not result.get("ok"):

        return None

    return result


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
# TELEGRAM: АВАТАР ПОЛЬЗОВАТЕЛЯ
# =========================================================

def get_telegram_avatar_bytes(user_id):
    """Скачивает самую большую версию аватара пользователя Telegram."""

    if not user_id:

        return None

    result = telegram_api(
        "getUserProfilePhotos",
        data={
            "user_id": user_id,
            "limit": 1
        }
    )

    if not result or not result.get("ok"):

        return None

    photos = result.get(
        "result",
        {}
    ).get(
        "photos",
        []
    )

    if not photos:

        logging.info(
            "Telegram user %s has no profile photo",
            user_id
        )

        return None

    # Первый набор фото, последний (самый крупный) размер
    largest = photos[0][-1]

    file_id = largest.get("file_id")

    if not file_id:

        return None

    downloaded = get_telegram_file(file_id)

    if not downloaded:

        return None

    file_bytes, _ = downloaded

    return file_bytes


def maybe_relay_telegram_avatar_to_max(user_id, sender_name):
    """Раз в сессию пересылает аватар Telegram-пользователя в MAX."""

    if not user_id or user_id in avatar_sent_telegram_users:

        return

    avatar_sent_telegram_users.add(user_id)

    try:

        avatar_bytes = get_telegram_avatar_bytes(user_id)

        if avatar_bytes:

            send_max_image(
                avatar_bytes,
                "avatar.jpg"
            )

            logging.info(
                "Relayed Telegram avatar of %s to MAX",
                sender_name
            )

    except Exception:

        logging.exception(
            "Error relaying Telegram avatar to MAX"
        )


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

def send_max_text(text, reply_to_mid=None):

    if not MAX_CHAT_ID:

        logging.error(
            "MAX_CHAT_ID is not configured"
        )

        return None

    try:

        chat_id = int(
            MAX_CHAT_ID
        )

    except Exception:

        logging.error(
            "MAX_CHAT_ID is not an integer: %s",
            MAX_CHAT_ID
        )

        return None

    payload = {
        "text": text
    }

    if reply_to_mid:

        # -----------------------------------------------------
        # ВАЖНО (правка):
        # По официальной схеме MAX (NewMessageLink) поле mid
        # лежит ПРЯМО внутри link, а не во вложенном объекте
        # "message". Старый вариант {"link": {"type": "reply",
        # "message": {"mid": ...}}} MAX не распознаёт и молча
        # игнорирует — из-за этого reply Telegram -> MAX не работал.
        # -----------------------------------------------------

        payload["link"] = {
            "type": "reply",
            "mid": reply_to_mid
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

        return None

    logging.info(
        "MAX text message SENT"
    )

    return result


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
    attachment_type,
    reply_to_mid=None
):

    token = upload_to_max(
        file_bytes,
        file_type,
        filename
    )

    if not token:

        return None

    try:

        chat_id = int(
            MAX_CHAT_ID
        )

    except Exception:

        logging.error(
            "Invalid MAX_CHAT_ID: %s",
            MAX_CHAT_ID
        )

        return None

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

    if reply_to_mid:

        # Тот же формат link, что и в send_max_text() — mid
        # напрямую внутри link, без вложенного "message".

        payload["link"] = {
            "type": "reply",
            "mid": reply_to_mid
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

            return result

        logging.warning(
            "MAX attachment attempt %s failed",
            attempt
        )

    logging.error(
        "MAX attachment FAILED after all attempts"
    )

    return None


# =========================================================
# MAX SEND IMAGE
# =========================================================

def send_max_image(
    image_bytes,
    filename="photo.jpg",
    reply_to_mid=None
):

    return send_max_attachment(
        image_bytes,
        "image",
        filename,
        "image",
        reply_to_mid=reply_to_mid
    )


# =========================================================
# MAX SEND AUDIO
# =========================================================

def send_max_audio(
    audio_bytes,
    filename="voice.ogg",
    reply_to_mid=None
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
        "audio",
        reply_to_mid=reply_to_mid
    )


# =========================================================
# MAX SEND FILE
# =========================================================

def send_max_file(
    file_bytes,
    filename="file",
    reply_to_mid=None
):

    return send_max_attachment(
        file_bytes,
        "file",
        filename,
        "file",
        reply_to_mid=reply_to_mid
    )


# =========================================================
# MAX DELETE MESSAGE
# =========================================================
#
# По официальной документации MAX:
#   DELETE /messages?message_id={mid}
#   Заголовок Authorization: {access_token}
#
# Сейчас в этом мосте она не вызывается (см. пункт 3 в шапке
# файла — Telegram не сообщает об удалении своих сообщений),
# но оставлена на будущее — например, если вы захотите удалять
# сообщение в MAX вручную командой, или подключите пользовательскую
# сессию Telegram, которая такие события всё-таки получает.
# =========================================================

def delete_max_message(mid):

    if not mid:

        return None

    return max_request(
        "DELETE",
        "/messages",
        params={
            "message_id": mid
        }
    )


# =========================================================
# MAX: АВАТАР ПОЛЬЗОВАТЕЛЯ
# =========================================================

def maybe_relay_max_avatar_to_telegram(sender):
    """
    Раз в сессию пересылает аватар MAX-пользователя в Telegram,
    если у отправителя есть поле avatar_url / full_avatar_url.
    """

    if not isinstance(sender, dict):

        return

    user_id = (
        sender.get("user_id")
        or sender.get("id")
    )

    avatar_url = (
        sender.get("avatar_url")
        or sender.get("full_avatar_url")
    )

    if not user_id or not avatar_url:

        return

    if user_id in avatar_sent_max_users:

        return

    avatar_sent_max_users.add(user_id)

    try:

        response = requests.get(
            avatar_url,
            timeout=30
        )

        if response.ok:

            send_telegram_photo(
                response.content,
                "avatar.jpg"
            )

            logging.info(
                "Relayed MAX avatar of user %s to Telegram",
                user_id
            )

        else:

            logging.warning(
                "MAX avatar download failed -> %s",
                response.status_code
            )

    except Exception:

        logging.exception(
            "Error relaying MAX avatar to Telegram"
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
# АНКЕТА: ОТПРАВКА ПЕРВОГО ВОПРОСА
# =========================================================

def start_anketa(user_id):

    logging.info(
        "Starting anketa for user %s",
        user_id
    )

    users_anketa[user_id] = {
        "current_question": 0,
        "data": {}
    }

    first_question = ANKETA_QUESTIONS[0]["text"]

    send_telegram_text_with_buttons(
        user_id,
        f"👋 Добро пожаловать!\n\nДавайте заполним анкету.\n\n{first_question}",
        None
    )


# =========================================================
# АНКЕТА: ОБРАБОТКА ОТВЕТА
# =========================================================

def process_anketa_answer(user_id, answer_text):

    if user_id not in users_anketa:
        return

    user_state = users_anketa[user_id]
    current_q_index = user_state["current_question"]

    if current_q_index >= len(ANKETA_QUESTIONS):
        return

    # Сохраняем ответ
    question_key = ANKETA_QUESTIONS[current_q_index]["key"]
    user_state["data"][question_key] = answer_text

    logging.info(
        "User %s answered Q%s: %s",
        user_id,
        current_q_index + 1,
        answer_text
    )

    # Переходим к следующему вопросу
    current_q_index += 1
    user_state["current_question"] = current_q_index

    if current_q_index < len(ANKETA_QUESTIONS):

        # Есть ещё вопросы
        next_question = ANKETA_QUESTIONS[current_q_index]["text"]

        send_telegram_text_with_buttons(
            user_id,
            next_question,
            None
        )

    else:

        # Все вопросы ответены - показываем итог
        show_anketa_summary(user_id)


# =========================================================
# АНКЕТА: ПОКАЗ ИТОГОВ И ПОДТВЕРЖДЕНИЯ
# =========================================================

def show_anketa_summary(user_id):

    if user_id not in users_anketa:
        return

    user_data = users_anketa[user_id]["data"]

    summary = (
        "✅ <b>Спасибо! Вот ваша анкета:</b>\n\n"
        f"👤 <b>Имя:</b> {user_data.get('name', 'N/A')}\n"
        f"🎂 <b>Возраст:</b> {user_data.get('age', 'N/A')}\n"
        f"♓ <b>Знак зодиака:</b> {user_data.get('zodiac', 'N/A')}\n"
        f"🎯 <b>Цель:</b> {user_data.get('goal', 'N/A')}\n"
        f"👶 <b>Дети:</b> {user_data.get('children', 'N/A')}\n"
        f"💭 <b>Дружба М-Ж:</b> {user_data.get('friendship', 'N/A')}\n\n"
        "<b>📋 Всё верно?</b>"
    )

    buttons = {
        "inline_keyboard": [
            [
                {
                    "text": "✅ Да, всё правильно",
                    "callback_data": f"anketa_confirm_yes_{user_id}"
                },
                {
                    "text": "❌ Нет, переделать",
                    "callback_data": f"anketa_confirm_no_{user_id}"
                }
            ]
        ]
    }

    send_telegram_text_with_buttons(
        user_id,
        summary,
        buttons
    )


# =========================================================
# АНКЕТА: ОТПРАВКА В ЧАТ
# =========================================================

def send_anketa_to_telegram_chat(user_id):

    if user_id not in users_anketa:
        return

    user_data = users_anketa[user_id]["data"]

    anketa_message = (
        "🆕 <b>Новый участник присоединился!</b>\n\n"
        f"👤 <b>Имя:</b> {user_data.get('name', 'N/A')}\n"
        f"🎂 <b>Возраст:</b> {user_data.get('age', 'N/A')}\n"
        f"♓ <b>Знак зодиака:</b> {user_data.get('zodiac', 'N/A')}\n"
        f"🎯 <b>Цель прихода:</b> {user_data.get('goal', 'N/A')}\n"
        f"👶 <b>Дети:</b> {user_data.get('children', 'N/A')}\n"
        f"💭 <b>О дружбе М-Ж:</b> {user_data.get('friendship', 'N/A')}\n\n"
        "Добро пожаловать в наше сообщество! 🎉"
    )

    send_telegram_text_with_buttons(
        TELEGRAM_CHAT_ID,
        anketa_message,
        None
    )


# =========================================================
# АНКЕТА: ОТПРАВКА В MAX ЧАТ
# =========================================================

def send_anketa_to_max_chat(user_id):

    if user_id not in users_anketa:
        return

    user_data = users_anketa[user_id]["data"]

    anketa_text = (
        "🆕 Новый участник присоединился!\n\n"
        f"👤 Имя: {user_data.get('name', 'N/A')}\n"
        f"🎂 Возраст: {user_data.get('age', 'N/A')}\n"
        f"♓ Знак зодиака: {user_data.get('zodiac', 'N/A')}\n"
        f"🎯 Цель прихода: {user_data.get('goal', 'N/A')}\n"
        f"👶 Дети: {user_data.get('children', 'N/A')}\n"
        f"💭 О дружбе М-Ж: {user_data.get('friendship', 'N/A')}\n\n"
        "Добро пожаловать в наше сообщество! 🎉"
    )

    send_max_text(anketa_text)


# =========================================================
# TELEGRAM -> MAX (обычные сообщения)
# =========================================================

def handle_telegram_message(message):

    if not isinstance(
        message,
        dict
    ):

        return

    user_id = message.get("from", {}).get("id")

    # Проверяем, не заполняет ли пользователь анкету
    if user_id in users_anketa:

        text = message.get("text")

        if text and not text.startswith("/"):

            process_anketa_answer(user_id, text)

            return

    sender_name = telegram_sender_name(
        message
    )

    tg_message_id = message.get("message_id")

    # -----------------------------------------------------
    # Если это ответ на сообщение — ищем, какому сообщению
    # в MAX он соответствует.
    # -----------------------------------------------------

    reply_to_message = message.get("reply_to_message")

    reply_to_tg_id = (
        reply_to_message.get("message_id")
        if isinstance(reply_to_message, dict)
        else None
    )

    reply_to_max_mid = (
        tg_to_max_id.get(reply_to_tg_id)
        if reply_to_tg_id
        else None
    )

    if reply_to_tg_id:

        logging.info(
            "Telegram reply detected: tg_msg=%s -> max_mid=%s",
            reply_to_tg_id,
            reply_to_max_mid
        )

    # -----------------------------------------------------
    # Аватар (один раз на пользователя за сессию)
    # -----------------------------------------------------

    maybe_relay_telegram_avatar_to_max(
        user_id,
        sender_name
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

        result = send_max_text(
            max_text,
            reply_to_mid=reply_to_max_mid
        )

        remember_message_pair(
            tg_message_id,
            extract_max_message_id(result)
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

                    result = send_max_image(
                        file_bytes,
                        filename,
                        reply_to_mid=reply_to_max_mid
                    )

                    remember_message_pair(
                        tg_message_id,
                        extract_max_message_id(result)
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

                    result = send_max_audio(
                        file_bytes,
                        filename,
                        reply_to_mid=reply_to_max_mid
                    )

                    remember_message_pair(
                        tg_message_id,
                        extract_max_message_id(result)
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

                    result = send_max_audio(
                        file_bytes,
                        filename,
                        reply_to_mid=reply_to_max_mid
                    )

                    remember_message_pair(
                        tg_message_id,
                        extract_max_message_id(result)
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

                    result = send_max_file(
                        file_bytes,
                        filename,
                        reply_to_mid=reply_to_max_mid
                    )

                    remember_message_pair(
                        tg_message_id,
                        extract_max_message_id(result)
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
        # CALLBACK QUERY (нажатие на кнопку)
        # -------------------------------------------------

        callback_query = update.get(
            "callback_query"
        )

        if callback_query:

            user_id = callback_query.get(
                "from",
                {}
            ).get("id")

            callback_data = callback_query.get(
                "data"
            )

            logging.info(
                "Telegram callback_query: user=%s data=%s",
                user_id,
                callback_data
            )

            # Подтверждение анкеты "Да"
            if callback_data == f"anketa_confirm_yes_{user_id}":

                send_telegram_text_with_buttons(
                    user_id,
                    "🎉 Отлично! Вот ссылка на чат:\n\n"
                    "👇 Нажмите кнопку ниже, чтобы вступить:",
                    {
                        "inline_keyboard": [
                            [
                                {
                                    "text": "🔗 Вступить в чат",
                                    "url": "https://t.me/dmdznakomstva"  
                                }
                            ]
                        ]
                    }
                )

                # Отправляем анкету в оба чата
                send_anketa_to_telegram_chat(user_id)
                send_anketa_to_max_chat(user_id)

                # Удаляем пользователя из процесса заполнения
                del users_anketa[user_id]

            # Подтверждение анкеты "Нет"
            elif callback_data == f"anketa_confirm_no_{user_id}":

                send_telegram_text_with_buttons(
                    user_id,
                    "Хорошо! Давайте начнём сначала.\n\n"
                    f"{ANKETA_QUESTIONS[0]['text']}",
                    None
                )

                # Перезапускаем анкету
                users_anketa[user_id] = {
                    "current_question": 0,
                    "data": {}
                }

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

            text = message.get("text")

            # Проверяем команду /start
            if text == "/start":

                user_id = message.get(
                    "from",
                    {}
                ).get("id")

                start_anketa(user_id)

            else:

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

        # -------------------------------------------------
        # NB: Telegram Bot API НЕ присылает update, когда
        # пользователь удаляет своё сообщение — поэтому здесь
        # намеренно нет обработчика "удалённого сообщения".
        # Это ограничение самого Telegram, не этого кода.
        # -------------------------------------------------

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

    sender = message.get("sender")

    logging.info(
        "MAX sender: %s",
        sender_name
    )

    # =====================================================
    # ID этого сообщения (для связки/удаления) и реплай
    # =====================================================

    body = message.get(
        "body"
    )

    if not isinstance(
        body,
        dict
    ):

        body = {}

    max_message_id = (
        body.get("mid")
        or message.get("mid")
    )

    link = (
        message.get("link")
        or body.get("link")
    )

    reply_to_max_mid = None

    if isinstance(link, dict) and link.get("type") == "reply":

        # У входящих сообщений MAX присылает mid ссылки либо
        # прямо в link.mid, либо (в некоторых версиях схемы)
        # во вложенном link.message.mid — проверяем оба варианта.

        reply_to_max_mid = (
            link.get("mid")
            or link.get(
                "message",
                {}
            ).get("mid")
        )

    reply_to_tg_id = (
        max_to_tg_id.get(reply_to_max_mid)
        if reply_to_max_mid
        else None
    )

    if reply_to_max_mid:

        logging.info(
            "MAX reply detected: max_mid=%s -> tg_msg=%s",
            reply_to_max_mid,
            reply_to_tg_id
        )

    # -----------------------------------------------------
    # Аватар (один раз на пользователя за сессию)
    # -----------------------------------------------------

    maybe_relay_max_avatar_to_telegram(sender)

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

        result = send_telegram_text(
            telegram_text,
            reply_to_message_id=reply_to_tg_id
        )

        remember_message_pair(
            extract_telegram_message_id(result),
            max_message_id
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

                        tg_result = send_telegram_photo(
                            response.content,
                            "image.jpg",
                            caption=(
                                f"👤 {sender_name}"
                            ),
                            reply_to_message_id=reply_to_tg_id
                        )

                        remember_message_pair(
                            extract_telegram_message_id(tg_result),
                            max_message_id
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

                        tg_result = send_telegram_voice(
                            response.content,
                            "voice.ogg",
                            reply_to_message_id=reply_to_tg_id
                        )

                        send_telegram_text(
                            f"👤 {sender_name}"
                        )

                        remember_message_pair(
                            extract_telegram_message_id(tg_result),
                            max_message_id
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

                        tg_result = send_telegram_document(
                            response.content,
                            filename,
                            reply_to_message_id=reply_to_tg_id
                        )

                        remember_message_pair(
                            extract_telegram_message_id(tg_result),
                            max_message_id
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

                        tg_result = send_telegram_video(
                            response.content,
                            "video.mp4",
                            caption=(
                                f"👤 {sender_name}"
                            ),
                            reply_to_message_id=reply_to_tg_id
                        )

                        remember_message_pair(
                            extract_telegram_message_id(tg_result),
                            max_message_id
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
# MAX -> TELEGRAM: УДАЛЕНИЕ СООБЩЕНИЯ
# =========================================================
#
# Правка: по официальной схеме апдейта message_removed поля
# лежат ПРЯМО В КОРНЕ события:
#   { "update_type": "message_removed",
#     "message_id": "mid...", "chat_id": ..., "user_id": ... }
# Раньше код сначала пытался достать mid из несуществующих
# message.body.mid / message.mid и только потом (случайно)
# попадал в верный event.get("message_id") через fallback.
# Теперь читаем поле напрямую и сверяем chat_id для надёжности.
# =========================================================

def handle_max_message_deleted(event):

    logging.info(
        "MAX deletion event: %s",
        str(event)[:5000]
    )

    removed_mid = event.get("message_id")

    event_chat_id = event.get("chat_id")

    if not removed_mid:

        logging.warning(
            "MAX deletion event without message_id: %s",
            str(event)[:2000]
        )

        return

    # Если MAX прислал chat_id, на всякий случай сверяем его
    # с нашим MAX_CHAT_ID, чтобы не среагировать на чужой чат.

    if event_chat_id is not None and MAX_CHAT_ID:

        try:

            if int(event_chat_id) != int(MAX_CHAT_ID):

                logging.info(
                    "MAX deletion event from another chat (%s), ignoring",
                    event_chat_id
                )

                return

        except Exception:

            pass

    tg_id = max_to_tg_id.get(removed_mid)

    if not tg_id:

        logging.info(
            "No linked Telegram message found for "
            "deleted MAX message %s",
            removed_mid
        )

        return

    telegram_api(
        "deleteMessage",
        data={
            "chat_id": TELEGRAM_CHAT_ID,
            "message_id": tg_id
        }
    )

    logging.info(
        "Deleted linked Telegram message %s "
        "(MAX message %s was removed)",
        tg_id,
        removed_mid
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

        elif event_type in (
            "message_removed",
            "message_deleted"
        ):

            handle_max_message_deleted(
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
# ВЕБ-ФОРМА АНКЕТЫ
# =========================================================

@app.route("/anketa", methods=["GET"])
def anketa_page():
    """Страница с веб-формой анкеты"""

    try:
        with open('templates/anketa.html', 'r', encoding='utf-8') as f:
            html_content = f.read()
        return html_content
    except Exception:
        logging.exception("Error loading anketa page")
        return "Error loading form", 500


@app.route("/submit-anketa", methods=["POST"])
def submit_anketa():
    """
    Обработка отправленной анкеты из веб-формы.
    """

    try:
        data = request.get_json(silent=True) or {}

        logging.info("Web anketa submitted: %s", data)

        platform = data.get("platform") or "telegram"

        anketa_data = {
            "name": data.get("name"),
            "age": data.get("age"),
            "zodiac": data.get("zodiac"),
            "goal": data.get("goal"),
            "children": data.get("children"),
            "friendship": data.get("friendship")
        }

        # Единый чистый текст без эмодзи и HTML-тегов —
        # одинаково хорошо смотрится и в Telegram, и в Max.
        anketa_message = (
            "Новый участник присоединился!\n\n"
            f"Имя: {anketa_data['name']}\n"
            f"Возраст: {anketa_data['age']}\n"
            f"Знак зодиака: {anketa_data['zodiac']}\n"
            f"Цель прихода: {anketa_data['goal']}\n"
            f"Дети: {anketa_data['children']}\n"
            f"О дружбе М-Ж: {anketa_data['friendship']}\n\n"
            "Добро пожаловать в наше сообщество!"
        )

        # Отправляем в ОБА чата всегда
        send_telegram_text_with_buttons(
            TELEGRAM_CHAT_ID,
            anketa_message,
            None
        )

        send_max_text(anketa_message)

        # Ссылка "Вступить" ведёт туда, что выбрал человек
        if platform == "max":
            chat_url = "https://max.ru/join/7R4ChrPwFUBLS_Xp_zc-M43YkTLHHNOF2wPMfx5uuNg"
        else:
            chat_url = "https://t.me/dmdznakomstva"

        return jsonify({
            "success": True,
            "chat_url": chat_url
        }), 200

    except Exception as e:

        logging.exception("Error submitting anketa")

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


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
