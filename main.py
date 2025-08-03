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
        try:
            json_data = request.get_data().decode('utf-8')
            update = telebot.types.Update.de_json(json_data)
            bot.process_new_updates([update])
            return '', 200
        except Exception as e:
            logger.error(f"❌ Webhook error: {e}")
            return 'Internal error', 500
    return 'Bad request', 400

# 🏠 Главная страница
@app.route('/')
def home():
    return {"status": "Bot is running", "time": datetime.now().isoformat()}

# 🔄 Установка webhook при старте
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

# 🎬 Команда /start
@bot.message_handler(commands=['start'])
def start(message):
    try:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        buttons = ["🏥 Стерилизация", "🏠 Пристройство", "🚨 Помощь"]
        markup.add(*buttons)
        
        bot.send_message(
            message.chat.id,
            "👋 Добро пожаловать в бота-помощника!",
            reply_markup=markup
        )
    except Exception as e:
        logger.error(f"❌ Ошибка в /start: {e}")

# 📊 Статус бота
@bot.message_handler(commands=['status'])
def status(message):
    webhook_info = bot.get_webhook_info()
    status_text = (
        f"🤖 Статус бота:\n"
        f"• Webhook: {webhook_info.url or 'не настроен'}\n"
        f"• Ожидающие сообщения: {webhook_info.pending_update_count}\n"
        f"• Последняя ошибка: {webhook_info.last_error_message or 'нет'}"
    )
    bot.send_message(message.chat.id, status_text)

# 🖼️ Отправка сообщения с изображением
def send_message_with_image(chat_id, text_key):
    text = texts.get(text_key, "Текст недоступен")
    image_url = IMAGES.get(text_key)
    
    try:
        if image_url:
            bot.send_photo(chat_id, image_url, caption=text)
        else:
            bot.send_message(chat_id, text)
    except Exception as e:
        logger.error(f"❌ Ошибка отправки сообщения: {e}")

# 🏥 Обработчик кнопки "Стерилизация"
@bot.message_handler(func=lambda m: m.text == "🏥 Стерилизация")
def handle_sterilization(message):
    send_message_with_image(message.chat.id, "paid_text")

# 🏠 Обработчик кнопки "Пристройство"
@bot.message_handler(func=lambda m: m.text == "🏠 Пристройство")
def handle_adoption(message):
    send_message_with_image(message.chat.id, "free_text")

# 🚀 Запуск приложения
if __name__ == '__main__':
    logger.info("🔄 Инициализация бота...")
    logger.info(f"📁 Загружено текстов: {len(texts)}")
    
    if WEBHOOK_URL:
        setup_webhook()
        app.run(host='0.0.0.0', port=PORT)
    else:
        logger.info("🚫 Режим webhook отключен, запуск polling...")
        bot.remove_webhook()
        bot.polling(none_stop=True)
