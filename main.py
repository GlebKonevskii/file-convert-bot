import os
import logging
from datetime import datetime, timedelta
from telegram import Update, InputFile
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
import requests
from PyPDF2 import PdfReader

# === НАСТРОЙКИ ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME")

# Хранилище лимитов
user_limits = {}

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Проверка подписки
def is_subscribed(user_id: int) -> bool:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getChatMember"
    params = {"chat_id": CHANNEL_ID, "user_id": user_id}
    try:
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        status = data.get("result", {}).get("status", "")
        return status in ["member", "administrator", "creator"]
    except Exception as e:
        logger.error(f"Ошибка проверки: {e}")
        return False

def get_daily_reset():
    now = datetime.utcnow()
    return now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)

def start(update: Update, context: CallbackContext):
    user = update.effective_user
    if not is_subscribed(user.id):
        update.message.reply_text(
            f"🔒 Подпишись на канал, чтобы использовать бота:\n"
            f"https://t.me/{CHANNEL_USERNAME}"
        )
        return
    update.message.reply_text(
        "✨ Отправь PDF-файл — я извлеку текст!\n\n"
        "Лимит: 10 конвертаций в день."
    )

def check_limit(user_id: int) -> bool:
    now = datetime.utcnow()
    if user_id not in user_limits:
        user_limits[user_id] = {"count": 0, "reset_time": get_daily_reset()}
    user_data = user_limits[user_id]
    if now >= user_data["reset_time"]:
        user_data["count"] = 0
        user_data["reset_time"] = get_daily_reset()
    return user_data["count"] < 10

def increment_limit(user_id: int):
    if user_id in user_limits:
        user_limits[user_id]["count"] += 1

# Обработка файлов
def handle_file(update: Update, context: CallbackContext):
    user = update.effective_user
    if not is_subscribed(user.id):
        update.message.reply_text(
            f"Подпишись на канал: https://t.me/{CHANNEL_USERNAME}"
        )
        return

    if not check_limit(user.id):
        update.message.reply_text(
            "🚫 Достигнут лимит: 10 конвертаций в день.\n"
            "Завтра будет новый лимит!\n\n"
            f"Следи за обновлениями: https://t.me/{CHANNEL_USERNAME}"
        )
        return

    file = None
    if update.message.document:
        file = update.message.document
        mime_type = file.mime_type or ""
        if not mime_type == "application/pdf":
            update.message.reply_text("Отправь PDF-файл.")
            return
    else:
        update.message.reply_text("Отправь PDF-файл.")
        return

    if not file:
        return

    try:
        # Скачиваем
        file_obj = context.bot.get_file(file.file_id)
        file_path = f"/tmp/temp_{user.id}_{file.file_unique_id}"
        file_obj.download(file_path)

        output_path = file_path.replace(".pdf", ".txt")
        caption = "✅ PDF → TXT"

        # Извлекаем текст
        reader = PdfReader(file_path)
        text = ""
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n\n"

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(text)

        # Отправляем
        with open(output_path, "rb") as f:
            update.message.reply_document(document=f, caption=caption)

        # Убираем временные файлы
        os.remove(file_path)
        os.remove(output_path)
        increment_limit(user_id)

    except Exception as e:
        logger.error(f"Ошибка: {e}")
        update.message.reply_text("❌ Ошибка при извлечении текста. Попробуй другой PDF.")
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)
        if 'output_path' in locals() and os.path.exists(output_path):
            os.remove(output_path)

# Запуск
def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.document, handle_file))

    logger.info("Бот запущен!")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
