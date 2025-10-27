import os
import logging
from telegram import Update
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
import requests

# === НАСТРОЙКИ ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")  # Добавь в Render Secrets

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

# Поиск фильма
def search_movie(query: str) -> str:
    try:
        url = f"https://api.themoviedb.org/3/search/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "query": query,
            "language": "ru"
        }
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        
        if data["results"]:
            movie = data["results"][0]
            title = movie["title"]
            year = movie["release_date"][:4] if movie["release_date"] else "Н/Д"
            rating = movie["vote_average"]
            overview = movie["overview"][:200] + "..." if len(movie["overview"]) > 200 else movie["overview"]
            genres = ", ".join([str(g) for g in movie.get("genre_ids", [])])  # Упрощённо
            
            return f"🎬 *{title} ({year})*\n⭐ Рейтинг: {rating}/10\n\n{overview}"
        else:
            return "❌ Фильм не найден. Попробуй другое название."
    except Exception as e:
        logger.error(f"Ошибка TMDb: {e}")
        return "❌ Не удалось получить данные. Попробуй позже."

# Команда /start
def start(update: Update, context: CallbackContext):
    user = update.effective_user
    if not is_subscribed(user.id):
        update.message.reply_text(
            f"🔒 Подпишись на канал, чтобы искать фильмы:\n"
            f"https://t.me/{CHANNEL_USERNAME}"
        )
        return
    update.message.reply_text(
        "🎥 Бот поиска фильмов\n\n"
        "Примеры:\n"
        "/фильм Матрица\n"
        "/фильм Интерстеллар\n"
        "/фильм Гарри Поттер\n\n"
        "Премиум-функции (только для подписчиков):\n"
        "/топ — ТОП-10 фильмов\n"
        "/жанр комедия — подборка"
    )

# Обработка команды /фильм
def handle_movie(update: Update, context: CallbackContext):
    user = update.effective_user
    if not is_subscribed(user.id):
        update.message.reply_text(f"Подпишись: https://t.me/{CHANNEL_USERNAME}")
        return

    query = " ".join(context.args)
    if not query:
        update.message.reply_text("Укажи название фильма: /фильм Матрица")
        return

    result = search_movie(query)
    update.message.reply_text(result, parse_mode="Markdown")

# ТОП-10 фильмов (премиум)
def top_movies(update: Update, context: CallbackContext):
    user = update.effective_user
    if not is_subscribed(user.id):
        update.message.reply_text(f"Подпишись: https://t.me/{CHANNEL_USERNAME}")
        return

    try:
        url = "https://api.themoviedb.org/3/movie/popular"
        params = {"api_key": TMDB_API_KEY, "language": "ru", "page": 1}
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        
        text = "🏆 ТОП-10 популярных фильмов:\n\n"
        for i, movie in enumerate(data["results"][:10], 1):
            title = movie["title"]
            year = movie["release_date"][:4] if movie["release_date"] else ""
            text += f"{i}. {title} ({year})\n"
        
        update.message.reply_text(text)
    except Exception as e:
        logger.error(f"Ошибка ТОПа: {e}")
        update.message.reply_text("❌ Ошибка при загрузке ТОПа.")

# Запуск
def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("фильм", handle_movie))
    dp.add_handler(CommandHandler("топ", top_movies))
    logger.info("Бот запущен!")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
