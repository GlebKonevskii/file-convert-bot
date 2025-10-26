import os
import logging
from datetime import datetime, timedelta
from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import requests
from pdf2docx import Converter
from docx2pdf import convert as docx_to_pdf
from PIL import Image
from moviepy.editor import VideoFileClip

# === НАСТРОЙКИ ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME")

# Хранилище лимитов (в памяти — для MVP)
user_limits = {}

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Проверка подписки
async def is_subscribed(user_id: int) -> bool:
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

# Сброс лимита в 00:00 UTC
def get_daily_reset():
    now = datetime.utcnow()
    return now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not await is_subscribed(user.id):
        await update.message.reply_text(
            f"🔒 Подпишись на канал, чтобы использовать бота:\n"
            f"https://t.me/{CHANNEL_USERNAME}"
        )
        return
    await update.message.reply_text(
        "✨ Привет! Я — бот-конвертер.\n\n"
        "Поддерживаю:\n"
        "• PDF ↔ DOCX\n"
        "• JPG ↔ PNG\n"
        "• MP4 → MP3\n\n"
        "Отправь файл — и я преобразую его!\n"
        "Лимит: 10 конвертаций в день."
    )

# Проверка лимита
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
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not await is_subscribed(user.id):
        await update.message.reply_text(
            f"Подпишись на канал: https://t.me/{CHANNEL_USERNAME}"
        )
        return

    if not check_limit(user.id):
        await update.message.reply_text(
            "🚫 Достигнут лимит: 10 конвертаций в день.\n"
            "Завтра будет новый лимит!\n\n"
            f"Следи за обновлениями: https://t.me/{CHANNEL_USERNAME}"
        )
        return

    # Определяем файл
    file = None
    mime_type = ""
    if update.message.document:
        file = update.message.document
        mime_type = file.mime_type or ""
    elif update.message.photo:
        file = update.message.photo[-1]
        mime_type = "image/jpeg"
    elif update.message.video:
        file = update.message.video
        mime_type = file.mime_type or "video/mp4"
    else:
        await update.message.reply_text("Отправь файл (документ, фото или видео).")
        return

    if not file:
        return

    try:
        # Скачиваем
        file_obj = await context.bot.get_file(file.file_id)
        file_path = f"/tmp/temp_{user.id}_{file.file_unique_id}"
        await file_obj.download_to_drive(file_path)

        output_path = None
        caption = ""

        # Конвертация
        if mime_type == "application/pdf":
            output_path = file_path.replace(".pdf", ".docx")
            cv = Converter(file_path)
            cv.convert(output_path, start=0, end=None)
            cv.close()
            caption = "✅ PDF → DOCX"

        elif file_path.endswith(".docx"):
            output_path = file_path.replace(".docx", ".pdf")
            docx_to_pdf(file_path, output_path)
            caption = "✅ DOCX → PDF"

        elif mime_type.startswith("image/") or file_path.lower().endswith(('.jpg', '.jpeg', '.png')):
            img = Image.open(file_path)
            if file_path.lower().endswith(('.jpg', '.jpeg')):
                output_path = file_path.replace(".jpg", ".png").replace(".jpeg", ".png")
                img.save(output_path, "PNG")
                caption = "✅ JPG → PNG"
            else:
                output_path = file_path.replace(".png", ".jpg")
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                img.save(output_path, "JPEG")
                caption = "✅ PNG → JPG"

        elif mime_type.startswith("video/") or file_path.lower().endswith(".mp4"):
            output_path = file_path.replace(".mp4", ".mp3")
            video = VideoFileClip(file_path)
            video.audio.write_audiofile(output_path, logger=None)
            video.close()
            caption = "✅ MP4 → MP3"

        else:
            await update.message.reply_text("❌ Неподдерживаемый формат.")
            os.remove(file_path)
            return

        # Отправка
        with open(output_path, "rb") as f:
            await update.message.reply_document(document=InputFile(f), caption=caption)

        # Уборка
        os.remove(file_path)
        os.remove(output_path)
        increment_limit(user.id)

    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text("❌ Ошибка конвертации. Попробуй другой файл.")
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)
        if 'output_path' in locals() and os.path.exists(output_path):
            os.remove(output_path)

# Запуск
def main():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(
        filters.Document.ALL | filters.PHOTO | filters.VIDEO, handle_file
    ))
    logger.info("Бот запущен!")
    application.run_polling()

if __name__ == "__main__":
    main()
