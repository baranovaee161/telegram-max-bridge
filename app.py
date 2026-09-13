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

        return jsonify({
            "ok": response.ok,
            "status_code": response.status_code,
            "response": response.json()
            if response.headers.get("content-type", "").startswith("application/json")
            else response.text
        })

    except requests.exceptions.RequestException as e:

        logging.exception(
            "MAX SUBSCRIPTION ERROR"
        )

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
        part for part in [first_name, last_name] if part
    )

    if sender_name:
        return sender_name

    return "Пользователь"


def send_text_to_max(text, sender_name):

    url = (
        f"https://platform-api2.max.ru/messages"
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

        logging
