import argparse, json, logging, os, requests
from openai import OpenAI

from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackContext, filters
)

# ======================
# ENV SETUP
# ======================
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TELEGRAM_TOKEN:
    exit("🚨Error: TELEGRAM_TOKEN is not set.")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")

if not OPENAI_API_KEY:
    exit("🚨Error: OPENAI_API_KEY is not set.")

client = OpenAI(
    api_key=OPENAI_API_KEY,
    base_url=OPENAI_BASE_URL
)

SESSION_DATA = {}

# ======================
# CONFIG
# ======================
def load_configuration():
    with open('configuration.json', 'r') as file:
        return json.load(file)

CONFIGURATION = load_configuration()

VISION_MODELS = CONFIGURATION.get('vision_models', [])
VALID_MODELS = CONFIGURATION.get('valid_models', {})  # FIX CASE BUG

# ======================
# HELPERS
# ======================
def get_session_id(func):
    async def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        session_id = str(
            update.effective_chat.id
            if update.effective_chat.type in ['group', 'supergroup']
            else update.effective_user.id
        )
        return await func(update, context, session_id, *args, **kwargs)
    return wrapper


def initialize_session_data(func):
    async def wrapper(update: Update, context: CallbackContext, session_id, *args, **kwargs):
        if session_id not in SESSION_DATA:
            SESSION_DATA[session_id] = CONFIGURATION['default_session_values']
        return await func(update, context, session_id, *args, **kwargs)
    return wrapper


def relay_errors(func):
    async def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        try:
            return await func(update, context, *args, **kwargs)
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")
    return wrapper

# ======================
# CORE AI FUNCTION (FIXED)
# ======================
async def response_from_openai(model, messages, temperature, max_tokens):
    params = {
        "model": model,
        "messages": messages,
        "temperature": temperature
    }

    if max_tokens is not None:
        params["max_tokens"] = max_tokens

    response = client.chat.completions.create(**params)
    return response.choices[0].message.content

# ======================
# MESSAGE HANDLER
# ======================
@relay_errors
@get_session_id
@initialize_session_data
async def handle_message(update: Update, context: CallbackContext, session_id):
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING
    )

    session_data = SESSION_DATA[session_id]

    # text message
    user_message = update.message.text or "hello"

    session_data['chat_history'].append({
        "role": "user",
        "content": user_message
    })

    response = await response_from_openai(
        session_data['model'],
        session_data['chat_history'],
        session_data['temperature'],
        session_data['max_tokens']
    )

    session_data['chat_history'].append({
        "role": "assistant",
        "content": response
    })

    await update.message.reply_text(response)

# ======================
# COMMANDS
# ======================
async def command_start(update: Update, context: CallbackContext):
    await update.message.reply_text("Bot is running 🚀")

# ======================
# REGISTER
# ======================
def register_handlers(app):
    app.add_handler(CommandHandler("start", command_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# ======================
# MAIN
# ======================
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    register_handlers(app)

    print("Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
