import os
import telebot
from telebot import types
from flask import Flask, request
from datetime import datetime
import time
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Конфигурация
TOKEN = os.environ.get('TOKEN')
if not TOKEN:
    logger.error("❌ Ошибка: Переменная TOKEN не найдена!")
    exit(1)

PORT = int(os.environ.get('PORT', 8080))
WEBHOOK_URL = "telegram-sterilization-bot-production.up.railway.app"  # Ваш реальный домен
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# Тексты сообщений
paid_text = (
    "💰✨ <b>ПЛАТНАЯ СТЕРИЛИЗАЦИЯ</b> ✨💰\n\n"
    # ... (ваш текст о платной стерилизации)
)

free_text = (
    "🎉 <b>БЕСПЛАТНАЯ СТЕРИЛИЗАЦИЯ</b> 🎉\n"
    # ... (ваш текст о бесплатной стерилизации)
)

# Webhook обработчик
@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    try:
        if request.headers.get('content-type') == 'application/json':
            logger.info(f"📥 Входящее сообщение: {request.get_data().decode('utf-8')}")
            json_string = request.get_data().decode('utf-8')
            update = telebot.types.Update.de_json(json_string)
            bot.process_new_updates([update])
            return ''
        return 'Bad request', 403
    except Exception as e:
        logger.error(f"❌ Ошибка обработки webhook: {e}")
        return 'Server error', 500

@app.route('/')
def home():
    return f"🤖 Bot is running! Time: {datetime.now().strftime('%H:%M:%S')}"

@app.route('/health')
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}

@bot.message_handler(commands=['start'])
def start(message):
    try:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("💰 Платная", "🆓 Бесплатная")
        bot.send_message(message.chat.id, "Выберите тип стерилизации:", reply_markup=markup)
        logger.info(f"👤 Пользователь {message.from_user.id} нажал /start")
    except Exception as e:
        logger.error(f"❌ Ошибка в обработчике /start: {e}")

@bot.message_handler(commands=['status', 'test'])
def status(message):
    try:
        current_time = datetime.now().strftime('%d.%m.%Y %H:%M:%S')
        bot.send_message(message.chat.id, f"🤖 Бот работает!\n⏰ Время: {current_time}\n🔗 Webhook: {WEBHOOK_URL}")
    except Exception as e:
        logger.error(f"❌ Ошибка в обработчике статуса: {e}")

@bot.message_handler(func=lambda message: True)
def handle_buttons(message):
    try:
        if message.text == "💰 Платная":
            bot.send_message(message.chat.id, paid_text, parse_mode="HTML", disable_web_page_preview=True)
        elif message.text == "🆓 Бесплатная":
            bot.send_message(message.chat.id, free_text, parse_mode="HTML", disable_web_page_preview=True)
        else:
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.add("💰 Платная", "🆓 Бесплатная")
            bot.send_message(message.chat.id, "Пожалуйста, выберите одну из кнопок ниже:", reply_markup=markup)
    except Exception as e:
        logger.error(f"❌ Ошибка обработки кнопки: {e}")

def setup_webhook():
    try:
        # Удаляем старый webhook
        bot.remove_webhook()
        time.sleep(2)
        
        if not WEBHOOK_URL:
            raise ValueError("WEBHOOK_URL не установлен")
            
        full_url = f"https://{WEBHOOK_URL}/{TOKEN}"
        logger.info(f"🔄 Устанавливаю webhook на: {full_url}")
        
        bot.set_webhook(
            url=full_url,
            max_connections=10,
            allowed_updates=["message", "callback_query"]
        )
        
        # Проверка
        webhook_info = bot.get_webhook_info()
        logger.info(f"ℹ️ Webhook info: {webhook_info.url} | Статус: {'активен' if webhook_info.is_running else 'неактивен'}")
        
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка webhook: {str(e)}")
        return False

if __name__ == "__main__":
    logger.info("🚀 Запуск бота...")
    
    if not setup_webhook():
        logger.warning("🔄 Webhook не настроен, пытаюсь запустить polling...")
        bot.polling(none_stop=True)
    else:
        logger.info(f"🌐 Запуск Flask на порту {PORT}")
        app.run(host='0.0.0.0', port=PORT)
