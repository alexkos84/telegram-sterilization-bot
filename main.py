import os
import time
import logging
from datetime import datetime
from functools import lru_cache

import telebot
from telebot import types
from flask import Flask, request

# 🔧 Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Конфигурация
TOKEN = os.environ.get('TOKEN')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')  # Без https:// в начале
PORT = int(os.environ.get('PORT', 8080))
ADMIN_IDS = [123456789]  # Замените на ваш Telegram ID

# Инициализация
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# 🗂️ Загрузка текстовых файлов
@lru_cache(maxsize=2)
def load_text(filename):
    try:
        with open(f"assets/{filename}", "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки {filename}: {e}")
        return f"Текст {filename} недоступен"

texts = {
    "paid_text": load_text("paid_text.html"),
    "free_text": load_text("free_text.html")
}

# 🖼️ Изображения для кнопок
IMAGES = {
    'paid_text': 'https://via.placeholder.com/400x300/FFD700/000000?text=💰+Платная+стерилизация',
    'free_text': 'https://via.placeholder.com/400x300/32CD32/FFFFFF?text=🆓+Бесплатная+стерилизация'
}

# 🌐 Webhook обработчик
@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    return 'Bad request', 400

# 🏠 Главная страница
@app.route('/')
def home():
    return {"status": "Bot is running", "time": datetime.now().isoformat()}

# 🔄 Установка webhook
def setup_webhook():
    if not WEBHOOK_URL:
        logger.warning("❌ WEBHOOK_URL не задан!")
        return False
    
    try:
        bot.remove_webhook()
        time.sleep(1)
        webhook_url = f"https://{WEBHOOK_URL}/{TOKEN}"
        bot.set_webhook(url=webhook_url)
        logger.info(f"✅ Webhook установлен: {webhook_url}")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка webhook: {e}")
        return False

# 🎬 Команда /start с интерактивными кнопками
@bot.message_handler(commands=['start'])
def start(message):
    try:
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn1 = types.InlineKeyboardButton("Бесплатная стерилизация", callback_data="free")
        btn2 = types.InlineKeyboardButton("Платная стерилизация", callback_data="paid")
        btn3 = types.InlineKeyboardButton("О проекте", callback_data="about")
        markup.add(btn1, btn2, btn3)
        
        bot.send_message(
            message.chat.id,
            "👋 Добро пожаловать в бота-помощника для кошек! Выберите опцию:",
            reply_markup=markup
        )
        logger.info(f"👤 Пользователь {message.from_user.id} запустил бота")
    except Exception as e:
        logger.error(f"❌ Ошибка в /start: {e}")
        bot.reply_to(message, "⚠️ Произошла ошибка. Попробуйте позже.")

# 🔘 Обработчик инлайн-кнопок
@bot.callback_query_handler(func=lambda call: True)
def handle_buttons(call):
    try:
        chat_id = call.message.chat.id
        if call.data == "free":
            bot.send_photo(
                chat_id,
                IMAGES['free_text'],
                caption=texts['free_text'],
                parse_mode="HTML"
            )
        elif call.data == "paid":
            bot.send_photo(
                chat_id,
                IMAGES['paid_text'],
                caption=texts['paid_text'],
                parse_mode="HTML"
            )
        elif call.data == "about":
            bot.send_message(chat_id, "🐾 Проект помощи бездомным кошкам Ялты")
        
        bot.answer_callback_query(call.id)
    except Exception as e:
        logger.error(f"❌ Ошибка обработки кнопки: {e}")
        bot.answer_callback_query(call.id, text="⚠️ Ошибка!", show_alert=True)

# 🚀 Запуск приложения
if __name__ == '__main__':
    logger.info("🔄 Инициализация бота...")
    logger.info(f"📁 Загружено текстов: {len(texts)}")
    
    if WEBHOOK_URL and setup_webhook():
        app.run(host='0.0.0.0', port=PORT)
    else:
        logger.warning("🚫 Режим webhook отключен, запуск polling...")
        bot.remove_webhook()
        bot.polling(none_stop=True)
