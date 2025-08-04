import os
import telebot
from telebot import types
from flask import Flask, request, jsonify
from datetime import datetime
import time
import logging
import json
from typing import Dict, List, Optional

# 🔧 Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ContentManager:
    """Класс для управления контентом бота"""
    
    def __init__(self, assets_dir: str = "assets"):
        self.assets_dir = assets_dir
        self.texts = {}
        self.images = {}
        self.load_all_content()
    
    def load_text(self, filename: str) -> str:
        """Загружает текст из HTML файла"""
        try:
            path = os.path.join(self.assets_dir, filename)
            with open(path, encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            logger.error(f"❌ Файл {filename} не найден!")
            return f"Контент из {filename} недоступен"
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки {filename}: {e}")
            return "Ошибка загрузки контента"
    
    def load_all_content(self):
        """Загружает весь контент при инициализации"""
        if not os.path.exists(self.assets_dir):
            logger.warning(f"📁 Папка {self.assets_dir} не найдена!")
            os.makedirs(self.assets_dir, exist_ok=True)
            return
        
        try:
            for filename in os.listdir(self.assets_dir):
                if filename.endswith('.html'):
                    key = filename.replace('.html', '')
                    self.texts[key] = self.load_text(filename)
                    logger.info(f"✅ Загружен текст: {filename} -> {key}")
                elif filename.endswith(('.jpg', '.jpeg', '.png')):
                    key = filename.split('.')[0]
                    self.images[key] = os.path.join(self.assets_dir, filename)
                    logger.info(f"✅ Найдено изображение: {filename} -> {key}")
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки контента: {e}")
    
    def get_text(self, key: str, default: str = "Контент недоступен") -> str:
        """Получает текст по ключу"""
        return self.texts.get(key, default)
    
    def get_image_path(self, key: str) -> Optional[str]:
        """Получает путь к изображению по ключу"""
        return self.images.get(key)

class DatabaseManager:
    """Простой менеджер для хранения данных пользователей"""
    
    def __init__(self, db_file: str = "user_data.json"):
        self.db_file = db_file
        self.data = self.load_data()
    
    def load_data(self) -> Dict:
        """Загружает данные из файла"""
        try:
            if os.path.exists(self.db_file):
                with open(self.db_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки данных: {e}")
        return {"users": {}, "statistics": {"total_users": 0, "messages_sent": 0}}
    
    def save_data(self):
        """Сохраняет данные в файл"""
        try:
            with open(self.db_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения данных: {e}")
    
    def add_user(self, user_id: int, username: str = None):
        """Добавляет пользователя"""
        user_id_str = str(user_id)
        if user_id_str not in self.data["users"]:
            self.data["users"][user_id_str] = {
                "username": username,
                "first_seen": datetime.now().isoformat(),
                "last_activity": datetime.now().isoformat(),
                "message_count": 0
            }
            self.data["statistics"]["total_users"] += 1
            logger.info(f"👤 Новый пользователь: {user_id} (@{username})")
        else:
            self.data["users"][user_id_str]["last_activity"] = datetime.now().isoformat()
        
        self.data["users"][user_id_str]["message_count"] += 1
        self.data["statistics"]["messages_sent"] += 1
        self.save_data()

class CatBot:
    """Основной класс бота"""
    
    def __init__(self):
        self.token = os.environ.get('TOKEN')
        if not self.token:
            logger.error("❌ Ошибка: Переменная TOKEN не найдена!")
            exit(1)
        
        self.bot = telebot.TeleBot(self.token)
        self.content_manager = ContentManager()
        self.db_manager = DatabaseManager()
        self.app = Flask(__name__)
        
        # Конфигурация
        self.port = int(os.environ.get('PORT', 8080))
        self.webhook_url = (
            os.environ.get('RAILWAY_STATIC_URL') or 
            os.environ.get('RAILWAY_PUBLIC_DOMAIN') or
            os.environ.get('WEBHOOK_URL')
        )
        
        self.setup_handlers()
        self.setup_routes()
    
    def send_message_with_image(self, chat_id: int, text: str, image_key: str = None) -> bool:
        """Отправляет сообщение с изображением или без него"""
        try:
            if image_key:
                image_path = self.content_manager.get_image_path(image_key)
                if image_path and os.path.exists(image_path):
                    with open(image_path, 'rb') as photo:
                        self.bot.send_photo(
                            chat_id,
                            photo,
                            caption=text,
                            parse_mode="HTML",
                            disable_web_page_preview=True
                        )
                        return True
            
            # Отправляем только текст
            self.bot.send_message(
                chat_id,
                text,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки сообщения: {e}")
            return False
    
    def get_main_keyboard(self):
        """Создает главную клавиатуру"""
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add("🏥 Стерилизация", "🏠 Пристройство")
        markup.add("🚨 Экстренная помощь", "📞 Контакты")
        markup.add("ℹ️ О проекте", "📊 Статистика")
        return markup
    
    def get_back_keyboard(self):
        """Создает клавиатуру с кнопкой назад"""
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("🔙 Назад")
        return markup
    
    def setup_handlers(self):
        """Настраивает обработчики команд и сообщений"""
        
        @self.bot.message_handler(commands=['start'])
        def start_handler(message):
            self.db_manager.add_user(message.from_user.id, message.from_user.username)
            self.send_message_with_image(
                message.chat.id,
                "👋 <b>Добро пожаловать в помощник по уличным кошкам!</b>\n\n"
                "🐾 Выберите нужный раздел из меню:\n\n"
                "🏥 <b>Стерилизация</b> - информация о стерилизации\n"
                "🏠 <b>Пристройство</b> - поиск дома для кошек\n"
                "🚨 <b>Экстренная помощь</b> - срочная ветеринарная помощь\n"
                "📞 <b>Контакты</b> - связь с волонтерами\n"
                "ℹ️ <b>О проекте</b> - информация о нашей деятельности"
            )
            
            # Отправляем клавиатуру отдельным сообщением
            self.bot.send_message(
                message.chat.id,
                "Выберите раздел:",
                reply_markup=self.get_main_keyboard()
            )
        
        @self.bot.message_handler(commands=['status', 'stats'])
        def status_handler(message):
            stats = self.db_manager.data["statistics"]
            now = datetime.now().strftime('%d.%m.%Y %H:%M:%S')
            
            status_text = f"""🤖 <b>Статус бота</b>

✅ Бот активен
⏰ Время: <code>{now}</code>
🆔 Ваш ID: <code>{message.from_user.id}</code>

📊 <b>Статистика:</b>
👥 Всего пользователей: {stats['total_users']}
💬 Сообщений обработано: {stats['messages_sent']}
"""
            self.send_message_with_image(message.chat.id, status_text)
        
        @self.bot.message_handler(commands=['admin'])
        def admin_handler(message):
            # Простая защита админки
            admin_ids = [int(x) for x in os.environ.get('ADMIN_IDS', '').split(',') if x.strip()]
            if message.from_user.id not in admin_ids:
                self.send_message_with_image(message.chat.id, "❌ Доступ запрещен")
                return
            
            stats = self.db_manager.data["statistics"]
            users_count = len(self.db_manager.data["users"])
            
            admin_text = f"""👨‍💻 <b>АДМИН ПАНЕЛЬ</b>

📊 <b>Статистика:</b>
👥 Пользователей: {users_count}
💬 Сообщений: {stats['messages_sent']}

🔄 <b>Команды:</b>
/reload - перезагрузить контент
/backup - создать резервную копию
"""
            self.send_message_with_image(message.chat.id, admin_text)
        
        @self.bot.message_handler(commands=['reload'])
        def reload_handler(message):
            admin_ids = [int(x) for x in os.environ.get('ADMIN_IDS', '').split(',') if x.strip()]
            if message.from_user.id not in admin_ids:
                return
            
            self.content_manager.load_all_content()
            self.send_message_with_image(message.chat.id, "✅ Контент перезагружен")
        
        @self.bot.message_handler(func=lambda m: True)
        def message_handler(message):
            self.db_manager.add_user(message.from_user.id, message.from_user.username)
            self.handle_message(message)
    
    def handle_message(self, message):
        """Обрабатывает текстовые сообщения"""
        text = message.text
        chat_id = message.chat.id
        
        try:
            if text == "🏥 Стерилизация":
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                markup.add("💰 Платная", "🆓 Бесплатная")
                markup.add("🔙 Назад")
                
                self.bot.send_message(
                    chat_id,
                    "🏥 <b>Стерилизация кошек</b>\n\n"
                    "Выберите тип стерилизации:\n\n"
                    "💰 <b>Платная</b> - частные клиники\n"
                    "🆓 <b>Бесплатная</b> - по программам помощи",
                    reply_markup=markup,
                    parse_mode="HTML"
                )
            
            elif text in ["💰 Платная", "🆓 Бесплатная"]:
                content_key = "paid_text" if text == "💰 Платная" else "free_text"
                image_key = "paid" if text == "💰 Платная" else "free"
                
                content = self.content_manager.get_text(
                    content_key, 
                    f"Информация о {'платной' if text == '💰 Платная' else 'бесплатной'} стерилизации временно недоступна"
                )
                
                self.send_message_with_image(chat_id, content, image_key)
                
                # Добавляем кнопку "Назад"
                self.bot.send_message(
                    chat_id,
                    "Что еще вас интересует?",
                    reply_markup=self.get_back_keyboard()
                )
            
            elif text == "🏠 Пристройство":
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                markup.add("👶 Котята", "🐱 Взрослые кошки")
                markup.add("📝 Подать объявление", "🔙 Назад")
                
                self.bot.send_message(
                    chat_id,
                    "🏠 <b>Пристройство кошек</b>\n\n"
                    "Выберите категорию:\n\n"
                    "👶 <b>Котята</b> - малыши ищут дом\n"
                    "🐱 <b>Взрослые кошки</b> - взрослые животные\n"
                    "📝 <b>Подать объявление</b> - разместить свое объявление",
                    reply_markup=markup,
                    parse_mode="HTML"
                )
            
            elif text == "👶 Котята":
                content = self.content_manager.get_text(
                    "kittens_adoption",
                    """👶 <b>Котята ищут дом</b>

🐱 В настоящее время доступны для пристройства:
• Рыжий котенок "Мурзик" (2 мес.)
• Трехцветная кошечка "Муся" (1.5 мес.)
• Серый полосатый "Барсик" (3 мес.)

📞 Для получения подробной информации:
Анна: +7 978 000-00-01
Telegram: @adoption_coordinator

💝 Все котята:
✅ Здоровы и привиты
✅ Обработаны от паразитов
✅ Социализированы"""
                )
                self.send_message_with_image(chat_id, content, "kittens")
            
            elif text == "🚨 Экстренная помощь":
                content = self.content_manager.get_text(
                    "emergency_help",
                    """🚨 <b>ЭКСТРЕННАЯ ПОМОЩЬ</b>

🏥 <b>Круглосуточные клиники:</b>
📞 "Доктор Айболит": +7 978 000-00-00
📍 г. Ялта, ул. Примерная, 1

🆘 <b>При отравлении:</b>
1️⃣ Не давайте воду и еду
2️⃣ Немедленно к врачу
3️⃣ Сохранить образец рвоты

🩹 <b>При травмах:</b>
1️⃣ Осторожно в переноску
2️⃣ К ветеринару
3️⃣ Не давать обезболивающие

📱 <b>Волонтеры 24/7:</b>
@emergency_help_cats"""
                )
                self.send_message_with_image(chat_id, content)
            
            elif text == "📞 Контакты":
                content = self.content_manager.get_text("contacts", self.get_default_contacts())
                self.send_message_with_image(chat_id, content)
            
            elif text == "ℹ️ О проекте":
                content = self.content_manager.get_text("about_project", self.get_default_about())
                self.send_message_with_image(chat_id, content, "about")
            
            elif text == "📊 Статистика":
                stats = self.db_manager.data["statistics"]
                stats_text = f"""📊 <b>СТАТИСТИКА ПРОЕКТА</b>

👥 Пользователей бота: {stats['total_users']}
💬 Сообщений обработано: {stats['messages_sent']}

🏥 <b>Наши достижения:</b>
🔹 Стерилизовано: 500+ кошек
🔹 Пристроено: 200+ котят
🔹 Вылечено: 150+ животных
🔹 Волонтеров: 50+ активных

📈 Обновляется автоматически"""
                self.send_message_with_image(chat_id, stats_text)
            
            elif text == "🔙 Назад":
                self.bot.send_message(
                    chat_id,
                    "🏠 Главное меню:",
                    reply_markup=self.get_main_keyboard()
                )
            
            else:
                # Неизвестная команда
                self.bot.send_message(
                    chat_id,
                    "❓ Не понимаю эту команду.\n\n"
                    "Используйте кнопки меню или команды:\n"
                    "/start - главное меню\n"
                    "/status - статус бота",
                    reply_markup=self.get_main_keyboard()
                )
                
        except Exception as e:
            logger.error(f"❌ Ошибка обработки сообщения: {e}")
            self.send_message_with_image(
                chat_id, 
                "⚠️ Произошла ошибка. Попробуйте позже или используйте /start"
            )
    
    def get_default_contacts(self) -> str:
        """Возвращает контакты по умолчанию"""
        return """📞 <b>ВАЖНЫЕ КОНТАКТЫ</b>

👥 <b>Координаторы:</b>
🔹 Екатерина (стерилизация): +7 978 144-90-70
🔹 Анна (пристройство): +7 978 000-00-01
🔹 Михаил (лечение): +7 978 000-00-02

🏥 <b>Клиники-партнеры:</b>
🔹 "Айболит": +7 978 000-00-03
🔹 "ВетМир": +7 978 000-00-04

📱 <b>Социальные сети:</b>
🔹 Telegram: @yalta_cats
🔹 Instagram: @yalta_street_cats"""
    
    def get_default_about(self) -> str:
        """Возвращает информацию о проекте"""
        return """ℹ️ <b>О ПРОЕКТЕ</b>

🎯 <b>Миссия:</b>
Помощь бездомным кошкам в Ялте

📊 <b>Достижения:</b>
🔹 Стерилизовано: 500+ кошек
🔹 Пристроено: 200+ котят
🔹 Волонтеров: 50+ активных

💰 <b>Поддержать:</b>
Карта: 2202 2020 0000 0000

🤝 <b>Стать волонтером:</b>
Пишите @volunteer_coordinator"""
    
    def setup_routes(self):
        """Настраивает Flask маршруты"""
        
        @self.app.route(f'/{self.token}', methods=['POST'])
        def webhook():
            try:
                if request.headers.get('content-type') == 'application/json':
                    json_string = request.get_data().decode('utf-8')
                    update = telebot.types.Update.de_json(json_string)
                    self.bot.process_new_updates([update])
                    return '', 200
                return 'Bad request', 400
            except Exception as e:
                logger.error(f"❌ Ошибка webhook: {e}")
                return 'Internal error', 500
        
        @self.app.route('/')
        def home():
            stats = self.db_manager.data["statistics"]
            return jsonify({
                "status": "🤖 Cat Helper Bot is running!",
                "time": datetime.now().strftime('%H:%M:%S'),
                "date": datetime.now().strftime('%d.%m.%Y'),
                "users": stats["total_users"],
                "messages": stats["messages_sent"]
            })
        
        @self.app.route('/health')
        def health():
            return jsonify({
                "status": "ok",
                "timestamp": datetime.now().isoformat(),
                "bot_info": "Cat Helper Bot Active"
            })
        
        @self.app.route('/stats')
        def stats_endpoint():
            return jsonify(self.db_manager.data["statistics"])
    
    def setup_webhook(self) -> bool:
        """Устанавливает webhook"""
        try:
            self.bot.remove_webhook()
            time.sleep(2)
            
            if not self.webhook_url:
                logger.error("❌ WEBHOOK_URL не задан!")
                return False
            
            full_url = f"https://{self.webhook_url}/{self.token}"
            result = self.bot.set_webhook(url=full_url, max_connections=10)
            
            if result:
                logger.info(f"✅ Webhook установлен: {full_url}")
                return True
            else:
                logger.error("❌ Не удалось установить webhook")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка установки webhook: {e}")
            return False
    
    def run(self):
        """Запускает бота"""
        logger.info("🚀 Запуск Cat Helper Bot...")
        if self.setup_webhook():
            logger.info(f"🌐 Сервер запущен на порту {self.port}")
            self.app.run(host='0.0.0.0', port=self.port, debug=False)
        else:
            logger.error("🚨 Webhook не настроен. Проверьте конфигурацию.")

# 🚀 Точка входа
if __name__ == "__main__":
    bot = CatBot()
    bot.run()
