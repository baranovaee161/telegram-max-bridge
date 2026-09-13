import os
import logging

from flask import Flask, request, jsonify

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
MAX_TOKEN = os.getenv("MAX_TOKEN")

@app.route("/")
def home():
    return "Telegram ↔ MAX bridge is running!"

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/telegram/webhook", methods=["POST"])
def telegram_webhook():
    data = request.get_json(silent=True)

    if data:
        logging.info("Telegram message received: %s", data)

    return jsonify({"ok": True})


@app.route("/max/webhook", methods=["POST"])
def max_webhook():
    data = request.get_json(silent=True)

    if data:
        logging.info("MAX message received: %s", data)

    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
