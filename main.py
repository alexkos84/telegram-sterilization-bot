import os
import telebot
from telebot import types
from flask import Flask, request
from datetime import datetime
import time
import logging

# 📄 Загрузка текста из HTML-файлов
def load_text(filename):
    try:
        path = os.path.join("assets", filename)
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logging.error(f"❌ Файл {filename} не найден!")
        return f"Контент из {filename} недоступен"
    except Exception as e:
        logging.error(f"❌ Ошибка загрузки {filename}: {e}")
        return "Ошибка загрузки контента"

paid_text = load_text("paid_text.html")
free_text = load_text("free_text.html")

# 🔧 Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ⚙️ Конфигурация
TOKEN = os.environ.get('TOKEN')
if not TOKEN:
    logger.error("❌ Ошибка: Переменная TOKEN не найдена!")
    exit(1)

PORT = int(os.environ.get('PORT', 8080))

# 🔧 Улучшенное определение webhook URL для Railway
WEBHOOK_URL = (
    os.environ.get('RAILWAY_STATIC_URL') or 
    os.environ.get('RAILWAY_PUBLIC_DOMAIN') or
    os.environ.get('WEBHOOK_URL')
)

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# 🌐 Webhook обработчик
@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    try:
        if request.headers.get('content-type') == 'application/json':
            json_string = request.get_data().decode('utf-8')
            update = telebot.types.Update.de_json(json_string)
            bot.process_new_updates([update])
            return '', 200
        return 'Bad request', 400
    except Exception as e:
        logger.error(f"❌ Ошибка webhook: {e}")
        return 'Internal error', 500

@app.route('/')
def home():
    return {
        "status": "🤖 Bot is running!",
        "time": datetime.now().strftime('%H:%M:%S'),
        "date": datetime.now().strftime('%d.%m.%Y')
    }

@app.route('/health')
def health():
    return {
        "status": "ok", 
        "time": datetime.now().isoformat(),
        "bot_info": "Telegram Bot Active"
    }

# 🎬 Стартовая команда
@bot.message_handler(commands=['start'])
def start(message):
    try:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
        markup.add("💰 Платная", "🆓 Бесплатная")
        
        welcome_text = (
            "👋 Добро пожаловать!\n\n"
            "Выберите тип стерилизации, чтобы получить подробную информацию:"
        )
        
        bot.send_message(
            message.chat.id, 
            welcome_text, 
            reply_markup=markup,
            parse_mode="HTML"
        )
        
        logger.info(f"👤 Новый пользователь: {message.from_user.id}")
        
    except Exception as e:
        logger.error(f"❌ Ошибка в команде /start: {e}")
        bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте еще раз.")

# 📊 Статус бота
@bot.message_handler(commands=['status'])
def status(message):
    try:
        current_time = datetime.now().strftime('%d.%m.%Y %H:%M:%S')
        status_text = (
            "🤖 <b>Статус бота</b>\n\n"
            f"✅ Бот активен\n"
            f"⏰ Время: <code>{current_time}</code>\n"
            f"🆔 Ваш ID: <code>{message.from_user.id}</code>"
        )
        bot.send_message(message.chat.id, status_text, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"❌ Ошибка в команде /status: {e}")
        bot.send_message(message.chat.id, "Ошибка получения статуса")

# 🎯 Обработка кнопок
@bot.message_handler(func=lambda message: True)
def handle_buttons(message):
    try:
        if message.text == "💰 Платная":
            bot.send_message(
                message.chat.id, 
                paid_text, 
                parse_mode="HTML", 
                disable_web_page_preview=True
            )
            logger.info(f"📤 Отправлена платная информация пользователю {message.from_user.id}")
            
        elif message.text == "🆓 Бесплатная":
            bot.send_message(
                message.chat.id, 
                free_text, 
                parse_mode="HTML", 
                disable_web_page_preview=True
            )
            logger.info(f"📤 Отправлена бесплатная информация пользователю {message.from_user.id}")
            
        else:
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.add("💰 Платная", "🆓 Бесплатная")
            
            help_text = (
                "❓ Пожалуйста, выберите одну из кнопок ниже:\n\n"
                "💰 <b>Платная</b> - подробная информация о платной стерилизации\n"
                "🆓 <b>Бесплатная</b> - информация о бесплатной стерилизации\n\n"
                "Или используйте команды:\n"
                "/start - начать сначала\n"
                "/status - статус бота"
            )
            
            bot.send_message(
                message.chat.id, 
                help_text, 
                reply_markup=markup,
                parse_mode="HTML"
            )
            
    except Exception as e:
        logger.error(f"❌ Ошибка обработки сообщения: {e}")
        bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте еще раз.")

# 🔄 Установка webhook
def setup_webhook():
    try:
        # Удаляем старый webhook
        bot.remove_webhook()
        time.sleep(2)
        
        if not WEBHOOK_URL:
            logger.error("❌ WEBHOOK_URL не установлен!")
            logger.info("💡 Убедитесь, что переменные окружения настроены правильно")
            return False
        
        # Формируем полный URL
        full_url = f"https://{WEBHOOK_URL}/{TOKEN}"
        logger.info(f"🔄 Устанавливаю webhook на: {full_url}")
        
        # Устанавливаем webhook
        result = bot.set_webhook(
            url=full_url,
            max_connections=10,
            allowed_updates=["message", "callback_query"]
        )
        
        if result:
            logger.info("✅ Webhook успешно установлен!")
            return True
        else:
            logger.error("❌ Не удалось установить webhook")
            return False
            
    except Exception as e:
        logger.error(f"❌ Ошибка установки webhook: {e}")
        return False

# 🚀 Запуск приложения
if __name__ == "__main__":
    logger.info("🚀 Запуск Telegram бота...")
    
    if setup_webhook():
        logger.info(f"🌐 Запуск Flask сервера на порту {PORT}")
        logger.info(f"🔗 Webhook URL: https://{WEBHOOK_URL}/{TOKEN}")
        
        # Запуск Flask приложения
        app.run(
            host='0.0.0.0', 
            port=PORT,
            debug=False  # Отключаем debug режим для продакшена
        )
    else:
        logger.error("🚨 Не удалось настроить webhook!")
        logger.info("🔧 Проверьте переменные окружения и попробуйте снова")
