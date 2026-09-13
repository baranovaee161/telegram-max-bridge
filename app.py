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


@app.route("/")
def home():
    return "Telegram ↔ MAX bridge is running"


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


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

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=20
        )

        logging.info("MAX RESPONSE: %s", response.text)

    return jsonify({"ok": True})


# Получаем сообщения из MAX
@app.route("/max/webhook", methods=["POST"])
def max_webhook():
    data = request.get_json(silent=True) or {}

    logging.info("MAX UPDATE: %s", data)

    update_type = data.get("update_type")

    # Показываем информацию о событии в логах
    if update_type == "bot_added":
        logging.info(
            "MAX CHAT ID: %s",
            data.get("chat_id")
        )

    message = data.get("message", {})
    body = message.get("body", {})

    text = body.get("text")

    if text and TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": "MAX → " + text
        }

        response = requests.post(
            url,
            json=payload,
            timeout=20
        )

        logging.info("TELEGRAM RESPONSE: %s", response.text)

    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
