import os
import telebot
from telebot import types
from flask import Flask, request
from datetime import datetime
import time
import logging
import signal
from functools import lru_cache

# 🔧 Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 👤 Настройки админов (ЗАМЕНИТЕ НА ВАШИ TELEGRAM ID)
ADMIN_IDS = [123456789]  # Добавьте ваш реальный Telegram ID

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
    'paid_text': 'https://via.placeholder.com/400x300/FFD700/000000?text=💰+Платная+стерилизация',
    'free_text': 'https://via.placeholder.com/400x300/32CD32/FFFFFF?text=🆓+Бесплатная+стерилизация',
    'emergency_help': 'https://via.placeholder.com/400x300/FF6B6B/FFFFFF?text=🚨+Экстренная+помощь',
    'contacts': 'https://via.placeholder.com/400x300/4ECDC4/FFFFFF?text=📞+Контакты',
    'about_project': 'https://via.placeholder.com/400x300/45B7D1/FFFFFF?text=ℹ️+О+проекте',
    'adoption_info': 'https://via.placeholder.com/400x300/FFA07A/000000?text=📝+Пристройство'
}

# 🗂️ Загрузка всех текстов
texts = load_all_texts()

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

# 📡 Настройки для чтения канала
CHANNEL_USERNAME = 'Lapki_ruchki_Yalta_help'

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# 🔍 Отладочная информация
logger.info(f"🔍 TOKEN: {TOKEN[:10]}...{TOKEN[-5:]}")
logger.info(f"🔍 WEBHOOK_URL: {WEBHOOK_URL}")
logger.info(f"🔍 PORT: {PORT}")
logger.info(f"📁 Загружено файлов: {len(texts)}")

# 🖼️ Функция отправки сообщения с изображением
def send_message_with_image(chat_id, text, image_key):
    try:
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

# 🏠 Функция получения постов о пристройстве с кэшированием
@lru_cache(maxsize=1)
def get_adoption_posts():
    """Получает тестовые посты о пристройстве"""
    return [
        {
            'title': '🐱 Котенок из канала @Lapki_ruchki_Yalta_help',
            'description': 'Возраст: 2 месяца\nПол: мальчик\nОкрас: рыжий\nЗдоров, ищет дом\n\n📋 Для получения реальных данных нужно настроить Telegram API',
            'photo': 'https://via.placeholder.com/400x300/FFB6C1/800080?text=🐱+Котенок',
            'contact': '@Lapki_ruchki_Yalta_help',
            'date': datetime.now().strftime('%d.%m.%Y')
        },
        {
            'title': '😺 Кошечка ищет дом',
            'description': 'Возраст: 1 год\nПол: девочка\nОкрас: трехцветная\nСтерилизована, ласковая',
            'photo': 'https://via.placeholder.com/400x300/98FB98/006400?text=😺+Кошечка',
            'contact': '@Lapki_ruchki_Yalta_help',
            'date': datetime.now().strftime('%d.%m.%Y')
        },
        {
            'title': '🐈 Взрослый кот',
            'description': 'Возраст: 3 года\nПол: мальчик\nОкрас: серый полосатый\nСпокойный, подходит для квартиры',
            'photo': 'https://via.placeholder.com/400x300/87CEEB/000080?text=🐈+Кот',
            'contact': '@Lapki_ruchki_Yalta_help',
            'date': datetime.now().strftime('%d.%m.%Y')
        }
    ]

# 🌐 Webhook обработчик
@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    try:
        if request.headers.get('content-type') == 'application/json':
            json_string = request.get_data().decode('utf-8')
            update = telebot.types.Update.de_json(json_string)
            bot.process_new_updates([update])
            logger.info(f"✅ Обработано обновление от пользователя")
            return '', 200
        else:
            logger.warning(f"❌ Неправильный content-type: {request.headers.get('content-type')}")
            return 'Bad request', 400
    except Exception as e:
        logger.error(f"❌ Ошибка webhook: {e}")
        return 'Internal error', 500

@app.route('/')
def home():
    return {
        "status": "🤖 Bot is running!",
        "time": datetime.now().strftime('%H:%M:%S'),
        "date": datetime.now().strftime('%d.%m.%Y'),
        "bot": "@CatYalta_bot",
        "webhook": f"https://{WEBHOOK_URL}/{TOKEN}" if WEBHOOK_URL else "Not configured",
        "loaded_files": list(texts.keys()),
        "webhook_endpoint": f"/{TOKEN}"
    }

@app.route('/health')
def health():
    return {
        "status": "ok", 
        "time": datetime.now().isoformat(),
        "bot_info": "Telegram Bot Active",
        "webhook_configured": bool(WEBHOOK_URL)
    }

# Дополнительный endpoint для проверки
@app.route('/webhook-test')
def webhook_test():
    try:
        webhook_info = bot.get_webhook_info()
        return {
            "webhook_url": webhook_info.url,
            "pending_updates": webhook_info.pending_update_count,
            "last_error": webhook_info.last_error_message,
            "last_error_date": webhook_info.last_error_date
        }
    except Exception as e:
        return {"error": str(e)}, 500

# 🎬 Стартовая команда
@bot.message_handler(commands=['start'])
def start(message):
    try:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add("🏥 Стерилизация", "🏠 Пристройство")
        markup.add("🚨 Экстренная помощь", "📞 Контакты")
        markup.add("ℹ️ О проекте")
        bot.send_message(
            message.chat.id, 
            "👋 <b>Добро пожаловать в помощник по уличным кошкам!</b>\n\n🐾 Выберите нужный раздел:",
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
        webhook_status = "✅ Настроен" if WEBHOOK_URL else "❌ Не настроен"
        
        # Получаем информацию о webhook
        webhook_info = bot.get_webhook_info()
        
        status_text = f"""🤖 <b>Статус бота @CatYalta_bot</b>

✅ Бот активен
⏰ Время: <code>{now}</code>
🆔 Ваш ID: <code>{message.from_user.id}</code>
🌐 Webhook: {webhook_status}

📊 <b>Информация о webhook:</b>
🔗 URL: <code>{webhook_info.url or 'не установлен'}</code>
📬 Ожидающие обновления: <code>{webhook_info.pending_update_count}</code>
📁 Загружено файлов: <code>{len(texts)}</code>"""

        if webhook_info.last_error_date:
            error_date = datetime.fromtimestamp(webhook_info.last_error_date)
            status_text += f"\n⚠️ Последняя ошибка: <code>{webhook_info.last_error_message}</code>"
            status_text += f"\n📅 Время ошибки: <code>{error_date.strftime('%d.%m.%Y %H:%M:%S')}</code>"

        bot.send_message(message.chat.id, status_text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"❌ Ошибка в /status: {e}")
        bot.send_message(message.chat.id, "Ошибка получения статуса.")

# 🔧 Команда для отладки (только для админов)
@bot.message_handler(commands=['debug'])
def debug_info(message):
    try:
        if message.from_user.id not in ADMIN_IDS:
            bot.send_message(message.chat.id, "❌ Недостаточно прав")
            return
            
        debug_text = f"""🔧 <b>Отладочная информация</b>

🌐 <b>Webhook:</b>
• URL: <code>{WEBHOOK_URL or 'НЕ УСТАНОВЛЕН'}</code>
• Полный URL: <code>https://{WEBHOOK_URL}/{TOKEN[:10]}...</code>

📁 <b>Загруженные файлы:</b>"""
        
        for key in texts.keys():
            debug_text += f"\n• {key}.html: ✅"
            
        if not texts:
            debug_text += "\n❌ Файлы не загружены"
            
        bot.send_message(message.chat.id, debug_text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"❌ Ошибка в /debug: {e}")
        bot.send_message(message.chat.id, "Ошибка отладки.")
