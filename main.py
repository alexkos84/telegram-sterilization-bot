import os
import telebot
from telebot import types
from flask import Flask, request
from datetime import datetime
import time
import logging

# 🔧 Настройка логирования (перенесено вверх)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 📄 Динамическая загрузка текста из HTML-файлов
def load_text(filename):
    try:
        path = os.path.join("assets", filename)
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.error(f"❌ Файл {filename} не найден!")
        return f"Контент из {filename} недоступен"
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки {filename}: {e}")
        return "Ошибка загрузки контента"

def load_all_texts():
    texts = {}
    assets_dir = "assets"
    
    if not os.path.exists(assets_dir):
        logger.warning(f"📁 Папка {assets_dir} не найдена!")
        return texts
    
    try:
        for filename in os.listdir(assets_dir):
            if filename.endswith('.html'):
                key = filename.replace('.html', '')
                texts[key] = load_text(filename)
                logger.info(f"✅ Загружен файл: {filename} -> {key}")
        return texts
    except Exception as e:
        logger.error(f"❌ Ошибка загрузки файлов: {e}")
        return texts

# 🖼️ Конфигурация изображений
IMAGES = {
    'paid_text': 'https://example.com/paid_sterilization.jpg',  # Замените на реальную ссылку
    'free_text': 'https://example.com/free_sterilization.jpg'   # Замените на реальную ссылку
}

# Альтернативно - локальные файлы в папке assets/images/
LOCAL_IMAGES = {
    'paid_text': os.path.join('assets', 'images', 'paid.jpg'),
    'free_text': os.path.join('assets', 'images', 'free.jpg')
}

# 🗂️ Загрузка всех текстов
texts = load_all_texts()
paid_text = texts.get('paid_text', 'Платная информация недоступна')
free_text = texts.get('free_text', 'Бесплатная информация недоступна')

# ⚙️ Конфигурация
TOKEN = os.environ.get('TOKEN')
if not TOKEN:
    logger.error("❌ Ошибка: Переменная TOKEN не найдена!")
    exit(1)

PORT = int(os.environ.get('PORT', 8080))
WEBHOOK_URL = (
    os.environ.get('RAILWAY_STATIC_URL') or 
    os.environ.get('RAILWAY_PUBLIC_DOMAIN') or
    os.environ.get('WEBHOOK_URL')
)

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# 🖼️ Функция отправки сообщения с изображением
def send_message_with_image(chat_id, text, image_key, use_local=False):
    try:
        if use_local:
            # Отправка локального файла
            image_path = LOCAL_IMAGES.get(image_key)
            if image_path and os.path.exists(image_path):
                with open(image_path, 'rb') as photo:
                    bot.send_photo(
                        chat_id,
                        photo,
                        caption=text,
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )
                return True
        else:
            # Отправка по URL
            image_url = IMAGES.get(image_key)
            if image_url:
                bot.send_photo(
                    chat_id,
                    image_url,
                    caption=text,
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
                return True
        
        # Если изображение не найдено - отправляем только текст
        bot.send_message(
            chat_id,
            text,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        return False
        
    except Exception as e:
        logger.error(f"❌ Ошибка отправки изображения: {e}")
        # Fallback - отправляем только текст
        bot.send_message(
            chat_id,
            text,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        return False

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
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("💰 Платная", "🆓 Бесплатная")
        bot.send_message(
            message.chat.id, 
            "👋 Добро пожаловать!\n\nВыберите тип стерилизации:",
            reply_markup=markup,
            parse_mode="HTML"
        )
        logger.info(f"👤 Новый пользователь: {message.from_user.id}")
    except Exception as e:
        logger.error(f"❌ Ошибка в /start: {e}")
        bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте еще раз.")

# 📊 Статус бота
@bot.message_handler(commands=['status'])
def status(message):
    try:
        now = datetime.now().strftime('%d.%m.%Y %H:%M:%S')
        bot.send_message(
            message.chat.id,
            f"🤖 <b>Статус бота</b>\n\n✅ Бот активен\n⏰ Время: <code>{now}</code>\n🆔 Ваш ID: <code>{message.from_user.id}</code>",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"❌ Ошибка в /status: {e}")
        bot.send_message(message.chat.id, "Ошибка получения статуса.")

# 🎯 Обработка кнопок
@bot.message_handler(func=lambda m: True)
def handle_buttons(message):
    try:
        button_mapping = {
            "💰 Платная": "paid_text",
            "🆓 Бесплатная": "free_text"
        }
        
        if message.text in button_mapping:
            content_key = button_mapping[message.text]
            content = texts.get(content_key, "Контент недоступен")
            
            # Отправляем сообщение с изображением
            # Измените use_local=True если хотите использовать локальные файлы
            send_message_with_image(message.chat.id, content, content_key, use_local=False)
            
        else:
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.add("💰 Платная", "🆓 Бесплатная")
            bot.send_message(
                message.chat.id,
                "❓ Выберите одну из кнопок ниже:\n\n💰 Платная\n🆓 Бесплатная\n\nили используйте команды: /start, /status",
                reply_markup=markup,
                parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"❌ Ошибка обработки кнопок: {e}")
        bot.send_message(message.chat.id, "Ошибка. Попробуйте позже.")

# 🔄 Установка webhook
def setup_webhook():
    try:
        bot.remove_webhook()
        time.sleep(2)
        if not WEBHOOK_URL:
            logger.error("❌ WEBHOOK_URL не задан!")
            return False
        full_url = f"https://{WEBHOOK_URL}/{TOKEN}"
        result = bot.set_webhook(url=full_url, max_connections=10)
        if result:
            logger.info(f"✅ Webhook установлен: {full_url}")
            return True
        else:
            logger.error("❌ Не удалось установить webhook")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка установки webhook: {e}")
        return False

# 🚀 Запуск сервера
if __name__ == "__main__":
    logger.info("🚀 Запуск Telegram бота...")
    if setup_webhook():
        app.run(host='0.0.0.0', port=PORT)
    else:
        logger.error("🚨 Webhook не настроен. Проверь конфигурацию.")
