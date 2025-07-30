import os
import telebot
from telebot import types
from flask import Flask, request
from datetime import datetime
import time
import logging

# Загрузка текстов из файлов
def load_text(filename):
    path = os.path.join("assets", filename)
    with open(path, encoding="utf-8") as f:
        return f.read()

paid_text = load_text("paid_text.html")
free_text = load_text("free_text.html")

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
WEBHOOK_URL = os.environ.get('RAILWAY_PUBLIC_DOMAIN')  # Автоматически на Railway

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# Ваши тексты (paid_text и free_text остаются без изменений)

# Webhook обработчик
@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''
    return 'Bad request', 403

@app.route('/')
def home():
    return f"🤖 Bot is running! Time: {datetime.now().strftime('%H:%M:%S')}"

@app.route('/health')
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}

@bot.message_handler(commands=['start'])
def start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("💰 Платная", "🆓 Бесплатная")
    bot.send_message(message.chat.id, "Выберите тип стерилизации:", reply_markup=markup)

@bot.message_handler(commands=['status'])
def status(message):
    current_time = datetime.now().strftime('%d.%m.%Y %H:%M:%S')
    bot.send_message(message.chat.id, f"🤖 Бот работает!\n⏰ Время: {current_time}")

@bot.message_handler(func=lambda message: True)
def handle_buttons(message):
    if message.text == "💰 Платная":
        bot.send_message(message.chat.id, paid_text, parse_mode="HTML", disable_web_page_preview=True)
    elif message.text == "🆓 Бесплатная":
        bot.send_message(message.chat.id, free_text, parse_mode="HTML", disable_web_page_preview=True)
    else:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("💰 Платная", "🆓 Бесплатная")
        bot.send_message(message.chat.id, "Пожалуйста, выберите одну из кнопок ниже:", reply_markup=markup)

def setup_webhook():
    try:
        # Удаляем старый webhook
        bot.remove_webhook()
        time.sleep(2)
        
        if not WEBHOOK_URL:
            logger.error("❌ WEBHOOK_URL не установлен!")
            return False
            
        full_url = f"https://{WEBHOOK_URL}/{TOKEN}"
        logger.info(f"🔄 Устанавливаю webhook на: {full_url}")
        
        bot.set_webhook(
            url=full_url,
            max_connections=10,
            allowed_updates=["message", "callback_query"]
        )
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка webhook: {e}")
        return False

if __name__ == "__main__":
    if setup_webhook():
        logger.info(f"🌐 Запуск Flask на порту {PORT}")
        app.run(host='0.0.0.0', port=PORT)
    else:
        logger.error("🚨 Не удалось настроить webhook!")
