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
        bot.send_message(
            message.chat.id,
            f"🤖 <b>Статус бота</b>\n\n✅ Бот активен\n⏰ Время: <code>{now}</code>\n🆔 Ваш ID: <code>{message.from_user.id}</code>",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"❌ Ошибка в /status: {e}")
        bot.send_message(message.chat.id, "Ошибка получения статуса.")

# 🏠 Функция получения постов о пристройстве (заглушка)
def get_adoption_posts():
    """Получает последние посты о пристройстве из канала"""
    # TODO: Интеграция с реальным каналом
    sample_posts = [
        {
            'title': '🐱 Котенок Мурзик ищет дом',
            'description': 'Возраст: 2 месяца\nПол: мальчик\nОкрас: рыжий\nЗдоров, привит, кастрирован',
            'photo': 'https://example.com/cat1.jpg',
            'contact': '@volunteer1'
        },
        {
            'title': '😺 Кошечка Муся',
            'description': 'Возраст: 1 год\nПол: девочка\nОкрас: трехцветная\nСтерилизована, очень ласковая',
            'photo': 'https://example.com/cat2.jpg',
            'contact': '@volunteer2'
        },
        {
            'title': '🐈 Кот Барсик',
            'description': 'Возраст: 3 года\nПол: мальчик\nОкрас: серый полосатый\nСпокойный, подходит для квартиры',
            'photo': 'https://example.com/cat3.jpg',
            'contact': '@volunteer3'
        }
    ]
    return sample_posts

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
                "🏥 <b>Стерилизация кошек</b>\n\nВыберите тип:",
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
            emergency_text = texts.get('emergency_help', """
🚨 <b>ЭКСТРЕННАЯ ПОМОЩЬ</b>

🏥 <b>Круглосуточные клиники:</b>
📞 Ветклиника "Доктор Айболит": <a href="tel:+79780000000">+7 978 000-00-00</a>
📍 г. Ялта, ул. Примерная, 1

🆘 <b>При отравлении:</b>
1️⃣ Не давайте воду и еду
2️⃣ Немедленно к врачу
3️⃣ Если есть рвота - сохранить образец

🩹 <b>При травмах:</b>
1️⃣ Не трогать животное без необходимости
2️⃣ Осторожно поместить в переноску
3️⃣ Доставить к ветеринару

📱 <b>Волонтеры онлайн:</b>
Telegram: @emergency_help_cats
""")
            bot.send_message(
                message.chat.id,
                emergency_text,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
            
        elif message.text == "📞 Контакты":
            contacts_text = texts.get('contacts', """
📞 <b>ВАЖНЫЕ КОНТАКТЫ</b>

👥 <b>Координаторы волонтеров:</b>
🔹 Екатерина (стерилизация): <a href="tel:+79781449070">+7 978 144-90-70</a>
🔹 Анна (пристройство): <a href="tel:+79780000001">+7 978 000-00-01</a>
🔹 Михаил (лечение): <a href="tel:+79780000002">+7 978 000-00-02</a>

🏥 <b>Партнерские клиники:</b>
🔹 "Айболит": <a href="tel:+79780000003">+7 978 000-00-03</a>
🔹 "ВетМир": <a href="tel:+79780000004">+7 978 000-00-04</a>

📱 <b>Социальные сети:</b>
🔹 Telegram канал: @yalta_cats
🔹 Instagram: @yalta_street_cats
🔹 ВКонтакте: vk.com/yalta_cats
""")
            bot.send_message(
                message.chat.id,
                contacts_text,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
            
        elif message.text == "ℹ️ О проекте":
            about_text = texts.get('about_project', """
ℹ️ <b>О ПРОЕКТЕ "ПОМОЩЬ УЛИЧНЫМ КОШКАМ"</b>

🎯 <b>Наша миссия:</b>
Помощь бездомным кошкам в Ялте и окрестностях

📊 <b>Наши достижения:</b>
🔹 Стерилизовано: 500+ кошек
🔹 Пристроено: 200+ котят
🔹 Волонтеров: 50+ активных

💰 <b>Поддержать проект:</b>
Карта Сбербанк: 2202 2020 0000 0000
Яндекс.Деньги: 410011000000000

🤝 <b>Присоединяйтесь:</b>
Мы всегда рады новым волонтерам!
""")
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
            posts = get_adoption_posts()
            bot.send_message(
                message.chat.id,
                "👶 <b>Котята ищут дом:</b>",
                parse_mode="HTML"
            )
            
            for post in posts[:3]:  # Показываем первые 3
                try:
                    bot.send_photo(
                        message.chat.id,
                        post['photo'],
                        caption=f"<b>{post['title']}</b>\n\n{post['description']}\n\n📞 Контакт: {post['contact']}",
                        parse_mode="HTML"
                    )
                except:
                    # Если фото не загружается, отправляем текст
                    bot.send_message(
                        message.chat.id,
                        f"<b>{post['title']}</b>\n\n{post['description']}\n\n📞 Контакт: {post['contact']}",
                        parse_mode="HTML"
                    )
                    
        elif message.text == "🐱 Взрослые кошки":
            bot.send_message(
                message.chat.id,
                "🐱 <b>Взрослые кошки ищут дом</b>\n\n⏳ Раздел в разработке...\n\nА пока посмотрите котят! 👶",
                parse_mode="HTML"
            )
            
        elif message.text == "📝 Подать объявление":
            bot.send_message(
                message.chat.id,
                """📝 <b>Подать объявление о пристройстве</b>

Для подачи объявления обратитесь к координатору:
👤 Анна: <a href="tel:+79780000001">+7 978 000-00-01</a>

📋 <b>Подготовьте информацию:</b>
🔹 Фото животного
🔹 Возраст, пол, окрас
🔹 Особенности характера
🔹 Здоровье (прививки, стерилизация)
🔹 Ваши контакты

💡 <b>Советы для успешного пристройства:</b>
✅ Качественные фото в хорошем свете
✅ Подробное описание характера
✅ Честная информация о здоровье
✅ Готовность отвечать на вопросы""",
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
                "❓ <b>Выберите раздел из меню:</b>\n\n🏥 Стерилизация\n🏠 Пристройство\n🚨 Экстренная помощь\n📞 Контакты\n\nили используйте команды: /start, /status",
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
