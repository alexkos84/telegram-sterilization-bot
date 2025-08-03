import os
import time
import logging
from datetime import datetime
from functools import lru_cache

import telebot
from telebot import types
from flask import Flask, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

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
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

# 🗂️ Загрузка текстовых файлов (с кэшированием)
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

# 🌐 Webhook обработчик (исправленный)
@app.route(f'/{TOKEN}', methods=['POST'])
@limiter.limit("5 per second")
def webhook():
    if request.headers.get('content-type') == 'application/json':
        try:
            json_string = request.get_data().decode('utf-8')
            update = telebot.types.Update.de_json(json_string)
            
            # Обрабатываем как callback_query если есть
            if update.callback_query:
                bot.process_new_updates([update])
                return '', 200
                
            # Обрабатываем обычные сообщения
            if update.message:
                bot.process_new_updates([update])
                return '', 200
                
            logger.warning("Неизвестный тип обновления")
            return 'Bad request', 400
            
        except Exception as e:
            logger.error(f"❌ Webhook error: {e}")
            return 'Internal error', 500
    return 'Bad request', 400

# 🏠 Главная страница
@app.route('/')
def home():
    return {
        "status": "Bot is running",
        "time": datetime.now().isoformat(),
        "webhook": f"https://{WEBHOOK_URL}/{TOKEN}" if WEBHOOK_URL else "None"
    }

# 📊 Статистика
@app.route('/stats')
def stats():
    webhook_info = bot.get_webhook_info()
    return {
        "webhook_url": webhook_info.url,
        "pending_updates": webhook_info.pending_update_count,
        "last_error": webhook_info.last_error_message or "None"
    }

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
        markup = types.InlineKeyboardMarkup()
        markup.row(
            types.InlineKeyboardButton("Бесплатная стерилизация", callback_data="free"),
            types.InlineKeyboardButton("Платная стерилизация", callback_data="paid")
        )
        markup.row(types.InlineKeyboardButton("О проекте", callback_data="about"))
        
        bot.send_message(
            message.chat.id,
            "👋 Добро пожаловать в бота-помощника для кошек! Выберите опцию:",
            reply_markup=markup
        )
        logger.info(f"👤 Пользователь {message.from_user.id} запустил бота")
    except Exception as e:
        logger.error(f"❌ Ошибка в /start: {e}")
        bot.reply_to(message, "⚠️ Произошла ошибка. Попробуйте позже.")

# 🔘 Обработчик инлайн-кнопок (улучшенный)
@bot.callback_query_handler(func=lambda call: True)
def handle_buttons(call):
    try:
        logger.info(f"Нажата кнопка: {call.data}")
        
        if call.data == "free":
            send_message_with_image(call.message.chat.id, "free_text")
        elif call.data == "paid":
            send_message_with_image(call.message.chat.id, "paid_text")
        elif call.data == "about":
            bot.send_message(call.message.chat.id, "🐾 Проект помощи бездомным кошкам Ялты")
        
        # Обязательно отвечаем на callback
        bot.answer_callback_query(call.id, text="✅ Готово")
        
    except Exception as e:
        logger.error(f"❌ Ошибка обработки кнопки {call.data}: {e}")
        bot.answer_callback_query(call.id, text="⚠️ Ошибка. Попробуйте позже.", show_alert=True)

# 🖼️ Отправка сообщения с изображением
def send_message_with_image(chat_id, text_key):
    try:
        text = texts.get(text_key, "Текст временно недоступен")
        image_url = IMAGES.get(text_key)
        
        if image_url:
            bot.send_photo(chat_id, image_url, caption=text, parse_mode="HTML")
        else:
            bot.send_message(chat_id, text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки {text_key}: {e}")
        raise

# 🔧 Команда для админов
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "❌ Доступ запрещен")
        return
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Переустановить вебхук", callback_data="reset_webhook"))
    
    bot.send_message(
        message.chat.id,
        "⚙️ Панель администратора:",
        reply_markup=markup
    )

# 🚀 Запуск приложения
if __name__ == '__main__':
    logger.info("🔄 Инициализация бота...")
    logger.info(f"📁 Загружено текстов: {len(texts)}")
    
    # Тестовая отправка уведомления админу
    for admin_id in ADMIN_IDS:
        try:
            bot.send_message(admin_id, "🤖 Бот запущен!")
        except Exception as e:
            logger.error(f"❌ Не удалось уведомить админа {admin_id}: {e}")
    
    if WEBHOOK_URL and setup_webhook():
        app.run(host='0.0.0.0', port=PORT)
    else:
        logger.warning("🚫 Режим webhook отключен, запуск polling...")
        bot.remove_webhook()
        bot.polling(none_stop=True)
