import os
import telebot
from telebot import types
from flask import Flask, request
from datetime import datetime
import time
import logging
import requests
import json

# 🔧 Настройка логирования
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
    'paid_text': 'https://via.placeholder.com/400x300/FFD700/000000?text=💰+Платная+стерилизация',
    'free_text': 'https://via.placeholder.com/400x300/32CD32/FFFFFF?text=🆓+Бесплатная+стерилизация'
}

# Локальные файлы (если нужно)
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

# 📡 Настройки для чтения канала (опционально)
CHANNEL_USERNAME = 'Lapki_ruchki_Yalta_help'

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# 🔍 Отладочная информация
logger.info(f"🔍 TOKEN: {TOKEN[:10]}...{TOKEN[-5:]}")
logger.info(f"🔍 WEBHOOK_URL: {WEBHOOK_URL}")
logger.info(f"🔍 PORT: {PORT}")

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

# 🏠 Функция получения постов о пристройстве
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
        "date": datetime.now().strftime('%d.%m.%Y'),
        "bot": "@CatYalta_bot",
        "webhook": f"https://{WEBHOOK_URL}/{TOKEN}" if WEBHOOK_URL else "Not configured"
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
        bot.send_message(
            message.chat.id,
            f"🤖 <b>Статус бота @CatYalta_bot</b>\n\n✅ Бот активен\n⏰ Время: <code>{now}</code>\n🆔 Ваш ID: <code>{message.from_user.id}</code>\n🌐 Webhook: {webhook_status}",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"❌ Ошибка в /status: {e}")
        bot.send_message(message.chat.id, "Ошибка получения статуса.")

# 🎯 Обработка кнопок
@bot.message_handler(func=lambda m: True)
def handle_buttons(message):
    try:
        # Основные разделы
        if message.text == "🏥 Стерилизация":
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.add("💰 Платная", "🆓 Бесплатная")
            markup.add("🔙 Назад")
            bot.send_message(
                message.chat.id,
                "🏥 <b>Стерилизация кошек в Ялте</b>\n\nВыберите тип:",
                reply_markup=markup,
                parse_mode="HTML"
            )
            
        elif message.text == "🏠 Пристройство":
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.add("👶 Котята ищут дом", "🐱 Взрослые кошки")
            markup.add("📝 Подать объявление", "🔙 Назад")
            bot.send_message(
                message.chat.id,
                "🏠 <b>Пристройство кошек</b>\n\nВыберите категорию:",
                reply_markup=markup,
                parse_mode="HTML"
            )
            
        elif message.text == "🚨 Экстренная помощь":
            emergency_text = """🚨 <b>ЭКСТРЕННАЯ ПОМОЩЬ</b>

🏥 <b>Круглосуточные клиники в Ялте:</b>
📞 Ветклиника "Айболит": <a href="tel:+79781449070">+7 978 144-90-70</a>
📍 г. Ялта, ул. Васильева, 7

🆘 <b>При отравлении:</b>
1️⃣ Не давайте воду и еду
2️⃣ Немедленно к врачу
3️⃣ Если есть рвота - сохранить образец

🩹 <b>При травмах:</b>
1️⃣ Не трогать животное без необходимости
2️⃣ Осторожно поместить в переноску
3️⃣ Доставить к ветеринару

📱 <b>Волонтеры онлайн:</b>
Telegram: @Lapki_ruchki_Yalta_help"""
            
            bot.send_message(
                message.chat.id,
                emergency_text,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
            
        elif message.text == "📞 Контакты":
            contacts_text = """📞 <b>ВАЖНЫЕ КОНТАКТЫ</b>

👥 <b>Координаторы волонтеров:</b>
🔹 Екатерина (стерилизация): <a href="tel:+79781449070">+7 978 144-90-70</a>
🔹 Анна (пристройство): <a href="tel:+79780000001">+7 978 000-00-01</a>

🏥 <b>Партнерские клиники:</b>
🔹 "Айболит": <a href="tel:+79781449070">+7 978 144-90-70</a>
📍 г. Ялта, ул. Васильева, 7

📱 <b>Социальные сети:</b>
🔹 Telegram канал: @Lapki_ruchki_Yalta_help
🔹 Основной чат волонтеров

💡 <b>Время работы:</b>
Заявки на стерилизацию: 8:00-9:00 (кроме четверга)"""
            
            bot.send_message(
                message.chat.id,
                contacts_text,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
            
        elif message.text == "ℹ️ О проекте":
            about_text = """ℹ️ <b>О ПРОЕКТЕ "ПОМОЩЬ УЛИЧНЫМ КОШКАМ ЯЛТЫ"</b>

🎯 <b>Наша миссия:</b>
Помощь бездомным кошкам в Ялте и окрестностях

📊 <b>Что мы делаем:</b>
🔹 Бесплатная стерилизация
🔹 Пристройство котят и кошек
🔹 Лечение больных животных
🔹 Кормление и уход

👥 <b>Как помочь:</b>
🔹 Стать волонтером
🔹 Финансовая поддержка
🔹 Репост объявлений
🔹 Временная передержка

🤝 <b>Присоединяйтесь:</b>
@Lapki_ruchki_Yalta_help - наш канал
Мы всегда рады новым волонтерам!"""
            
            bot.send_message(
                message.chat.id,
                about_text,
                parse_mode="HTML",
                disable_web_page_preview=True
            )

        # Стерилизация (существующие кнопки)
        elif message.text in ["💰 Платная", "🆓 Бесплатная"]:
            button_mapping = {
                "💰 Платная": "paid_text",
                "🆓 Бесплатная": "free_text"
            }
            content_key = button_mapping[message.text]
            content = texts.get(content_key, "Контент недоступен")
            send_message_with_image(message.chat.id, content, content_key, use_local=False)
            
        # Пристройство
        elif message.text == "👶 Котята ищут дом":
            bot.send_message(
                message.chat.id,
                "👶 <b>Котята ищут дом из канала @Lapki_ruchki_Yalta_help:</b>\n\n⏳ Загружаем данные...",
                parse_mode="HTML"
            )
            
            posts = get_adoption_posts()
            
            if posts:
                bot.send_message(
                    message.chat.id,
                    f"📱 <b>Найдено {len(posts)} объявлений:</b>",
                    parse_mode="HTML"
                )
                
                for i, post in enumerate(posts[:3], 1):
                    try:
                        caption = f"<b>{post['title']}</b>\n\n{post['description']}\n\n📅 {post['date']}\n📞 Связаться: {post['contact']}"
                        
                        if post.get('photo'):
                            bot.send_photo(
                                message.chat.id,
                                post['photo'],
                                caption=caption,
                                parse_mode="HTML"
                            )
                        else:
                            bot.send_message(
                                message.chat.id,
                                caption,
                                parse_mode="HTML"
                            )
                    except Exception as e:
                        logger.error(f"❌ Ошибка отправки поста {i}: {e}")
                        
                # Ссылка на полный канал
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton(
                    "📱 Смотреть все объявления в канале",
                    url=f"https://t.me/{CHANNEL_USERNAME}"
                ))
                bot.send_message(
                    message.chat.id,
                    "👆 <b>Это только примеры</b>\n\nВсе актуальные объявления смотрите в канале:",
                    reply_markup=markup,
                    parse_mode="HTML"
                )
            else:
                bot.send_message(
                    message.chat.id,
                    f"😔 Пока нет новых объявлений\n\n📱 Проверьте канал: @{CHANNEL_USERNAME}",
                    parse_mode="HTML"
                )
                
        elif message.text == "🐱 Взрослые кошки":
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(
                "📱 Перейти в канал",
                url=f"https://t.me/{CHANNEL_USERNAME}"
            ))
            bot.send_message(
                message.chat.id,
                "🐱 <b>Взрослые кошки ищут дом</b>\n\nВсе объявления о пристройстве взрослых кошек смотрите в нашем канале:",
                reply_markup=markup,
                parse_mode="HTML"
            )
            
        elif message.text == "📝 Подать объявление":
            bot.send_message(
                message.chat.id,
                """📝 <b>Подать объявление о пристройстве</b>

Для подачи объявления обратитесь к координатору:
👤 Екатерина: <a href="tel:+79781449070">+7 978 144-90-70</a>

📋 <b>Подготовьте информацию:</b>
🔹 Фото животного (2-3 хороших снимка)
🔹 Возраст, пол, окрас
🔹 Особенности характера
🔹 Здоровье (прививки, стерилизация)
🔹 Ваши контакты

💡 <b>Советы для успешного пристройства:</b>
✅ Качественные фото в хорошем свете
✅ Подробное описание характера
✅ Честная информация о здоровье
✅ Готовность отвечать на вопросы будущих хозяев

📱 <b>Также можете написать напрямую в канал:</b>
@Lapki_ruchki_Yalta_help""",
                parse_mode="HTML",
                disable_web_page_preview=True
            )
            
        elif message.text == "🔙 Назад":
            start(message)
            
        else:
            # Главное меню по умолчанию
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
            markup.add("🏥 Стерилизация", "🏠 Пристройство")
            markup.add("🚨 Экстренная помощь", "📞 Контакты")
            markup.add("ℹ️ О проекте")
            bot.send_message(
                message.chat.id,
                "❓ <b>Выберите раздел из меню:</b>\n\n🏥 Стерилизация - информация о платной и бесплатной стерилизации\n🏠 Пристройство - котята и кошки ищут дом\n🚨 Экстренная помощь - контакты клиник\n📞 Контакты - связь с волонтерами\n\nили используйте команды: /start, /status",
                reply_markup=markup,
                parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"❌ Ошибка обработки кнопок: {e}")
        bot.send_message(message.chat.id, "Ошибка. Попробуйте позже.")

# 🔄 Установка webhook
def setup_webhook():
    try:
        # Очищаем старый webhook
        bot.remove_webhook()
        time.sleep(3)
        
        if not WEBHOOK_URL:
            logger.error("❌ WEBHOOK_URL не задан! Проверьте переменную RAILWAY_STATIC_URL")
            return False
            
        full_url = f"https://{WEBHOOK_URL}/{TOKEN}"
        
        logger.info(f"🔗 Устанавливаем webhook: {full_url}")
        
        result = bot.set_webhook(
            url=full_url, 
            max_connections=10,
            drop_pending_updates=True
        )
        
        if result:
            logger.info(f"✅ Webhook установлен успешно!")
            # Проверяем webhook
            webhook_info = bot.get_webhook_info()
            logger.info(f"📊 Webhook URL: {webhook_info.url}")
            logger.info(f"📊 Pending updates: {webhook_info.pending_update_count}")
            return True
        else:
            logger.error("❌ Не удалось установить webhook")
            return False
            
    except Exception as e:
        logger.error(f"❌ Ошибка установки webhook: {e}")
        return False

# 🚀 Запуск сервера
if __name__ == "__main__":
    logger.info("🚀 Запуск Telegram бота @CatYalta_bot...")
    logger.info(f"🌐 URL: https://{WEBHOOK_URL}" if WEBHOOK_URL else "🌐 URL: не настроен")
    
    if setup_webhook():
        logger.info(f"🎯 Сервер запускается на порту {PORT}")
        app.run(host='0.0.0.0', port=PORT)
    else:
        logger.error("🚨 Webhook не настроен. Проверь конфигурацию:")
        logger.error("1. Убедись что переменная TOKEN правильная")
        logger.error("2. Добавь переменную RAILWAY_STATIC_URL с доменом")
        logger.error("3. Перезапусти сервис")
