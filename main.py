import argparse
import json
import logging
import os
import requests

from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackContext,
    filters
)

# ======================
# ENV
# ======================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")

if not TELEGRAM_TOKEN:
    exit("🚨 TELEGRAM_TOKEN is not set")
if not OPENAI_API_KEY:
    exit("🚨 OPENAI_API_KEY is not set")
if not OPENAI_BASE_URL:
    exit("🚨 OPENAI_BASE_URL is not set")

# ======================
# SESSION
# ======================
SESSION_DATA = {}

# ======================
# CONFIG
# ======================
def load_configuration():
    with open("configuration.json", "r") as f:
        return json.load(f)

CONFIG = load_configuration()

VISION_MODELS = CONFIG.get("vision_models", [])
VALID_MODELS = CONFIG.get("valid_models", CONFIG.get("VALID_MODELS", {}))

# ======================
# HELPERS
# ======================
def get_session_id(func):
    async def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        session_id = str(
            update.effective_chat.id
            if update.effective_chat.type in ["group", "supergroup"]
            else update.effective_user.id
        )
        return await func(update, context, session_id, *args, **kwargs)
    return wrapper


def initialize_session(func):
    async def wrapper(update: Update, context: CallbackContext, session_id, *args, **kwargs):
        if session_id not in SESSION_DATA:
            SESSION_DATA[session_id] = CONFIG["default_session_values"].copy()
        return await func(update, context, session_id, *args, **kwargs)
    return wrapper


def error_handler(func):
    async def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        try:
            return await func(update, context, *args, **kwargs)
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")
    return wrapper

# ======================
# LITELLM CALL (FIXED)
# ======================
def call_llm(model, messages, temperature, max_tokens):

    url = f"{OPENAI_BASE_URL}/chat/completions"

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature
    }

    if max_tokens:
        payload["max_tokens"] = max_tokens

    r = requests.post(url, json=payload, headers=headers, timeout=120)

    if r.status_code != 200:
        raise Exception(r.text)

    return r.json()["choices"][0]["message"]["content"]

# ======================
# MESSAGE HANDLER
# ======================
@error_handler
@get_session_id
@initialize_session
async def handle_message(update: Update, context: CallbackContext, session_id):

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING
    )

    session = SESSION_DATA[session_id]

    user_text = update.message.text or "hello"

    session["chat_history"].append({
        "role": "user",
        "content": user_text
    })

    response = call_llm(
        session["model"],
        session["chat_history"],
        session["temperature"],
        session["max_tokens"]
    )

    session["chat_history"].append({
        "role": "assistant",
        "content": response
    })

    await update.message.reply_text(response)

# ======================
# COMMANDS
# ======================
async def start(update: Update, context: CallbackContext):
    await update.message.reply_text("🚀 Bot is running!")

# ======================
# REGISTER HANDLERS
# ======================
def register(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# ======================
# MAIN
# ======================
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    register(app)

    print("Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
