import os
import json
import requests
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackContext,
    filters
)

# ======================
# ENV CHECK (STRICT)
# ======================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "").rstrip("/")

if not TELEGRAM_TOKEN:
    raise Exception("TELEGRAM_TOKEN not set")

if not OPENAI_API_KEY.startswith("sk-"):
    raise Exception(f"Invalid OPENAI_API_KEY loaded: {OPENAI_API_KEY}")

if not OPENAI_BASE_URL:
    raise Exception("OPENAI_BASE_URL not set")

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
# LITELLM CALL (FIXED + SAFE)
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

    try:
        r = requests.post(url, json=payload, headers=headers, timeout=120)

        if not r.ok:
            # DEBUG FULL ERROR
            raise Exception(f"{r.status_code} | {r.text}")

        return r.json()["choices"][0]["message"]["content"]

    except requests.exceptions.RequestException as e:
        raise Exception(f"Request failed: {e}")

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

    # 🔥 IMPORTANT: inject system prompt
    messages = [
        {
            "role": "system",
            "content": session.get("system_prompt", "You are a helpful assistant.")
        }
    ] + session["chat_history"]

    response = call_llm(
        session["model"],
        messages,
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
    await update.message.reply_text("🚀 Bot is running with LiteLLM OK!")

# ======================
# REGISTER
# ======================
def register(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# ======================
# MAIN
# ======================
def main():
    print("ENV CHECK:")
    print("BASE_URL:", OPENAI_BASE_URL)
    print("API_KEY:", OPENAI_API_KEY[:10], "...")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    register(app)

    print("Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
