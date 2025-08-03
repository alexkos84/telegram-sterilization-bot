import os
import telebot
from telebot import types
from flask import Flask, request
import logging
from datetime import datetime
import time

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Конфигурация
TOKEN = os.getenv('TOKEN')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')
PORT = int(os.getenv('PORT', 8080))
ADMIN_IDS = [int(id) for id in os.getenv('ADMIN_IDS', '').split(',') if id]

# Инициализация
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

class ContentManager:
    def __init__(self):
        self.base_dir = "assets"
        self.texts_dir = os.path.join(self.base_dir, "texts")
        self.images_dir = os.path.join(self.base_dir, "images")
        self._ensure_dirs_exist()
        
    def _ensure_dirs_exist(self):
        os.makedirs(self.texts_dir, exist_ok=True)
        os.makedirs(self.images_dir, exist_ok=True)
    
    def load_html(self, filename):
        """Загружает HTML-контент из файла"""
        try:
            path = os.path.join(self.texts_dir, f"{filename}.html")
            with open(path, encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error loading HTML {filename}: {e}")
            return f"<b>⚠️ Content '{filename}' not available</b>"
    
    def get_image_path(self, image_name):
        """Возвращает путь к изображению"""
        path = os.path.join(self.images_dir, f"{image_name}.jpg")
        return path if os.path.exists(path) else None

content = ContentManager()

# Webhook обработчик
@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        update = telebot.types.Update.de_json(request.get_data().decode('utf-8'))
        bot.process_new_updates([update])
        return '', 200
    return 'Bad request', 400

@app.route('/')
def home():
    return {"status": "Bot is running", "time": datetime.now().isoformat()}

def setup_webhook():
    if not WEBHOOK_URL:
        logger.error("WEBHOOK_URL not set!")
        return False
    
    try:
        bot.remove_webhook()
        time.sleep(1)
        webhook_url = f"https://{WEBHOOK_URL}/{TOKEN}"
        bot.set_webhook(url=webhook_url)
        logger.info(f"Webhook set to: {webhook_url}")
        return True
    except Exception as e:
        logger.error(f"Webhook setup error: {e}")
        return False

# ====================
# ОСНОВНЫЕ КОМАНДЫ
# ====================

@bot.message_handler(commands=['start'])
def start(message):
    try:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        buttons = [
            "🏥 Стерилизация", 
            "🏠 Пристройство",
            "🚨 Помощь", 
            "📞 Контакты",
            "ℹ️ О проекте"
        ]
        markup.add(*buttons)
        
        html_content = content.load_html('welcome')
        bot.send_message(
            message.chat.id,
            html_content,
            reply_markup=markup,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Start command error: {e}")

# ====================
# ОБРАБОТЧИКИ КНОПОК
# ====================

@bot.message_handler(func=lambda m: m.text == "🏥 Стерилизация")
def sterilization_menu(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("💰 Платная", "🆓 Бесплатная", "🔙 Назад")
    
    html_content = content.load_html('sterilization_menu')
    bot.send_message(
        message.chat.id,
        html_content,
        reply_markup=markup,
        parse_mode="HTML"
    )

@bot.message_handler(func=lambda m: m.text in ["💰 Платная", "🆓 Бесплатная"])
def sterilization_info(message):
    content_type = "paid" if message.text == "💰 Платная" else "free"
    html_content = content.load_html(f'sterilization_{content_type}')
    image_path = content.get_image_path(content_type)
    
    try:
        if image_path:
            with open(image_path, 'rb') as photo:
                bot.send_photo(
                    message.chat.id,
                    photo,
                    caption=html_content,
                    parse_mode="HTML"
                )
        else:
            bot.send_message(
                message.chat.id,
                html_content,
                parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"Error sending {content_type} info: {e}")

@bot.message_handler(func=lambda m: m.text == "🏠 Пристройство")
def adoption_menu(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("👶 Котята", "🐱 Взрослые", "📝 Подать заявку", "🔙 Назад")
    
    html_content = content.load_html('adoption_menu')
    bot.send_message(
        message.chat.id,
        html_content,
        reply_markup=markup,
        parse_mode="HTML"
    )

@bot.message_handler(func=lambda m: m.text == "🚨 Помощь")
def emergency_help(message):
    html_content = content.load_html('emergency_help')
    bot.send_message(
        message.chat.id,
        html_content,
        parse_mode="HTML",
        disable_web_page_preview=True
    )

@bot.message_handler(func=lambda m: m.text == "🔙 Назад")
def back_to_main(message):
    start(message)

# ====================
# ЗАПУСК СЕРВЕРА
# ====================

if __name__ == '__main__':
    logger.info("Starting bot...")
    
    # Проверка структуры папок
    required_dirs = [
        content.texts_dir,
        content.images_dir
    ]
    
    for directory in required_dirs:
        if not os.path.exists(directory):
            logger.warning(f"Directory {directory} does not exist! Creating...")
            os.makedirs(directory)
    
    # Проверка обязательных HTML-файлов
    required_html = [
        'welcome',
        'sterilization_menu',
        'sterilization_paid',
        'sterilization_free',
        'adoption_menu',
        'emergency_help'
    ]
    
    for html_file in required_html:
        path = os.path.join(content.texts_dir, f"{html_file}.html")
        if not os.path.exists(path):
            logger.error(f"Required HTML file missing: {path}")
            with open(path, 'w', encoding='utf-8') as f:
                f.write(f"<b>Placeholder for {html_file}</b>")
    
    if WEBHOOK_URL and setup_webhook():
        app.run(host='0.0.0.0', port=PORT)
    else:
        logger.warning("Using polling mode")
        bot.polling(none_stop=True)
