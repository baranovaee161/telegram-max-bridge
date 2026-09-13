import os
import logging
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
MAX_TOKEN = os.getenv("MAX_TOKEN")

TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
MAX_CHAT_ID = os.getenv("MAX_CHAT_ID")

MAX_WEBHOOK_SECRET = os.getenv("MAX_WEBHOOK_SECRET")

# Сертификаты Минцифры для подключения к MAX API
MAX_CA_BUNDLE = "/etc/secrets/max_ca_bundle.pem"


@app.route("/")
def home():
    return "Telegram ↔ MAX bridge is running"


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


# Подключение MAX Webhook
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

        return jsonify({
            "ok": response.ok,
            "status_code": response.status_code,
            "response": response.json()
            if response.headers.get("content-type", "").startswith("application/json")
            else response.text
        })

    except requests.exceptions.RequestException as e:

        logging.exception("MAX SUBSCRIPTION ERROR")

        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500


# Получаем сообщения из Telegram
@app.route("/telegram/webhook", methods=["POST"])
def telegram_webhook():

    data = request.get_json(silent=True) or {}

    logging.info("TELEGRAM UPDATE: %s", data)

    message = data.get("message", {})
    text = message.get("text")

    if text and MAX_TOKEN and MAX_CHAT_ID:

        url = "https://platform-api2.max.ru/messages"

        headers = {
            "Authorization": MAX_TOKEN,
            "Content-Type": "application/json"
        }

        payload = {
            "chat_id": int(MAX_CHAT_ID),
            "text": "Telegram → " + text
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
                "MAX RESPONSE: %s",
                response.text
            )

        except requests.exceptions.RequestException:

            logging.exception("MAX MESSAGE ERROR")

    return jsonify({"ok": True})


# Получаем сообщения из MAX
@app.route("/max/webhook", methods=["POST"])
def max_webhook():

    # Проверяем секрет MAX
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

    # Получаем ID MAX-чата
    if update_type == "bot_added":

        chat_id = data.get("chat_id")

        logging.info(
            "MAX CHAT ID: %s",
            chat_id
        )

    # Получаем новое сообщение
    message = data.get("message", {})

    if not isinstance(message, dict):
        message = {}

    body = message.get("body", {})

    if not isinstance(body, dict):
        body = {}

    text = body.get("text")

    # Если сообщение пришло из MAX —
    # отправляем его в Telegram
    if text and TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:

        url = (
            f"https://api.telegram.org/"
            f"bot{TELEGRAM_TOKEN}/sendMessage"
        )

        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": "MAX → " + text
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
        os.environ.get("PORT", 10000)
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
