import os
import telebot
from telebot import types
from flask import Flask, request, jsonify
from datetime import datetime
import time
import logging
import json
import asyncio
from telethon import TelegramClient
from telethon.tl.types import Channel
import re
from typing import Dict, List, Optional, Union

# 🔧 Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TelegramChannelParser:
    """Класс для парсинга постов из Telegram канала/группы"""
    
    def __init__(self):
        # Данные для Telegram API (нужно получить на https://my.telegram.org)
        self.api_id = os.environ.get('TELEGRAM_API_ID')
        self.api_hash = os.environ.get('TELEGRAM_API_HASH')
        self.phone = os.environ.get('TELEGRAM_PHONE')  # Ваш номер телефона
        
        # Настройки канала
        self.channel_username = 'Lapki_ruchki_Yalta_help'  # без @
        self.channel_url = 'https://t.me/Lapki_ruchki_Yalta_help'
        
        self.client = None
        self.posts_cache = []
        self.last_update = None
        
    async def init_client(self):
        """Инициализация Telegram клиента"""
        try:
            if not all([self.api_id, self.api_hash]):
                logger.error("❌ Не заданы TELEGRAM_API_ID или TELEGRAM_API_HASH")
                return False
                
            self.client = TelegramClient('bot_session', self.api_id, self.api_hash)
            await self.client.start(phone=self.phone)
            logger.info("✅ Telegram клиент инициализирован")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации клиента: {e}")
            return False
    
    async def get_channel_posts(self, limit: int = 3) -> List[Dict]:
        """Получает последние посты из канала"""
        try:
            if not self.client:
                if not await self.init_client():
                    return self.get_mock_posts()
            
            # Получаем канал
            channel = await self.client.get_entity(self.channel_username)
            
            # Получаем последние сообщения
            messages = await self.client.get_messages(channel, limit=limit*2)  # Берем больше для фильтрации
            
            posts = []
            for message in messages:
                if not message.text:  # Пропускаем сообщения без текста
                    continue
                    
                # Парсим пост
                post_data = await self.parse_post(message)
                if post_data and self.is_cat_related(post_data['text']):
                    posts.append(post_data)
                    
                if len(posts) >= limit:
                    break
            
            self.posts_cache = posts
            self.last_update = datetime.now()
            logger.info(f"✅ Получено {len(posts)} постов из канала")
            return posts
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения постов: {e}")
            return self.get_mock_posts()
    
    async def parse_post(self, message) -> Optional[Dict]:
        """Парсит отдельный пост"""
        try:
            text = message.text or ""
            
            # Извлекаем основную информацию
            post_data = {
                'id': message.id,
                'text': text,
                'date': message.date.strftime('%d.%m.%Y %H:%M'),
                'url': f"{self.channel_url}/{message.id}",
                'photo': None,
                'title': self.extract_title(text),
                'description': self.extract_description(text),
                'contact': self.extract_contact(text)
            }
            
            # Проверяем наличие фото
            if message.photo:
                # Для получения фото нужны дополнительные права
                post_data['has_photo'] = True
            
            return post_data
            
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга поста: {e}")
            return None
    
    def extract_title(self, text: str) -> str:
        """Извлекает заголовок из текста поста"""
        lines = text.split('\n')
        for line in lines[:3]:  # Смотрим первые 3 строки
            line = line.strip()
            if line and len(line) > 10:
                # Убираем эмодзи для заголовка
                title = re.sub(r'[^\w\s\-\.,!?а-яёА-ЯЁ]', '', line)
                if len(title) > 50:
                    title = title[:50] + "..."
                return title or "Кошка ищет дом"
        return "Кошка ищет дом"
    
    def extract_description(self, text: str) -> str:
        """Извлекает описание из текста"""
        # Убираем контактную информацию для описания
        clean_text = re.sub(r'@\w+|https?://\S+|\+?\d[\d\s\-\(\)]+', '', text)
        
        if len(clean_text) > 200:
            return clean_text[:200] + "..."
        return clean_text
    
    def extract_contact(self, text: str) -> str:
        """Извлекает контактную информацию"""
        # Ищем телефоны
        phone_pattern = r'\+?[78][\s\-]?\(?9\d{2}\)?\s?[\d\s\-]{7,10}'
        phones = re.findall(phone_pattern, text)
        
        # Ищем юзернеймы
        username_pattern = r'@\w+'
        usernames = re.findall(username_pattern, text)
        
        contacts = []
        if phones:
            contacts.extend(phones[:1])  # Берем первый телефон
        if usernames:
            contacts.extend(usernames[:1])  # Берем первый username
            
        return ' • '.join(contacts) if contacts else "См. в канале"
    
    def is_cat_related(self, text: str) -> bool:
        """Проверяет, относится ли пост к кошкам"""
        cat_keywords = [
            'кот', 'кошк', 'котен', 'котик', 'мурз', 'мяу',
            'кастр', 'стерил', 'привит', 'пристрой', 'дом',
            'котята', 'мама-кошка', 'беременная'
        ]
        
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in cat_keywords)
    
    def get_mock_posts(self) -> List[Dict]:
        """Возвращает тестовые посты если API недоступно"""
        return [
            {
                'id': 1001,
                'title': '🐱 Котенок Мурзик ищет дом',
                'description': 'Возраст: 2 месяца, мальчик, рыжий окрас. Здоров, привит, очень игривый и ласковый.',
                'date': '03.08.2025 14:30',
                'url': f'{self.channel_url}/1001',
                'contact': '@volunteer1 • +7 978 123-45-67',
                'has_photo': True
            },
            {
                'id': 1002,
                'title': '😺 Кошечка Муся стерилизована',
                'description': 'Возраст: 1 год, девочка, трехцветная. Стерилизована, привита, очень спокойная.',
                'date': '03.08.2025 12:15',
                'url': f'{self.channel_url}/1002',
                'contact': '@volunteer2',
                'has_photo': True
            },
            {
                'id': 1003,
                'title': '🐈 Взрослый кот Барсик',
                'description': 'Возраст: 3 года, мальчик, серый полосатый. Кастрирован, подходит для квартиры.',
                'date': '02.08.2025 18:45',
                'url': f'{self.channel_url}/1003',
                'contact': '+7 978 987-65-43',
                'has_photo': False
            }
        ]
    
    def get_cached_posts(self) -> List[Dict]:
        """Возвращает кэшированные посты"""
        # Если кэш старше 30 минут, обновляем
        if (self.last_update and 
            (datetime.now() - self.last_update).seconds > 1800):
            try:
                # Запускаем асинхронное обновление
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                posts = loop.run_until_complete(self.get_channel_posts())
                loop.close()
                return posts
            except Exception as e:
                logger.error(f"❌ Ошибка API постов канала: {e}")
                return jsonify({"status": "error", "message": str(e)}), 500
    
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
        
        # Предварительная загрузка постов из канала
        try:
            logger.info("📡 Инициализация парсера канала...")
            posts = self.channel_parser.get_cached_posts()
            logger.info(f"✅ Загружено {len(posts)} постов для кэша")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось загрузить посты при старте: {e}")
        
        if self.setup_webhook():
            logger.info(f"🌐 Сервер запущен на порту {self.port}")
            logger.info(f"📢 Канал: {self.channel_parser.channel_url}")
            self.app.run(host='0.0.0.0', port=self.port, debug=False)
        else:
            logger.error("🚨 Webhook не настроен. Проверьте конфигурацию.")

# 🚀 Точка входа
if __name__ == "__main__":
    bot = CatBot()
    bot.run():
                pass
        
        return self.posts_cache if self.posts_cache else self.get_mock_posts()

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
        self.channel_parser = TelegramChannelParser()
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
    
    def send_channel_posts(self, chat_id: int):
        """Отправляет посты из канала о кошках"""
        try:
            # Получаем посты из канала
            posts = self.channel_parser.get_cached_posts()
            
            if not posts:
                self.send_message_with_image(
                    chat_id,
                    "😿 К сожалению, сейчас нет актуальных объявлений о кошках.\n\n"
                    f"📢 Проверьте канал напрямую: {self.channel_parser.channel_url}"
                )
                return
            
            # Отправляем заголовок
            header_text = f"""🐱 <b>КОШКИ ИЩУТ ДОМ</b>

📢 Актуальные объявления из канала:
<a href="{self.channel_parser.channel_url}">Лапки-ручки Ялта помощь</a>

⬇️ Последние {len(posts)} объявления:"""
            
            self.send_message_with_image(chat_id, header_text)
            
            # Отправляем каждый пост
            for i, post in enumerate(posts, 1):
                post_text = f"""{'🔸' if i == 1 else '🔹'} <b>{post['title']}</b>

📝 {post['description']}

📅 {post['date']}
📞 Контакт: {post['contact']}

🔗 <a href="{post['url']}">Смотреть в канале</a>
{'━━━━━━━━━━━━━━━━' if i < len(posts) else ''}"""
                
                self.send_message_with_image(chat_id, post_text)
                time.sleep(0.5)  # Небольшая задержка между сообщениями
            
            # Добавляем информацию о канале
            footer_text = f"""💡 <b>Как помочь кошкам:</b>

🏠 <b>Хотите взять кошку?</b>
Свяжитесь с контактом из объявления

📢 <b>Подписывайтесь на канал:</b>
<a href="{self.channel_parser.channel_url}">Лапки-ручки Ялта помощь</a>

🤝 <b>Стать волонтером:</b>
Напишите в канал или администраторам

💰 <b>Поддержать финансово:</b>
Реквизиты в канале"""
            
            self.send_message_with_image(chat_id, footer_text)
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки постов канала: {e}")
            self.send_message_with_image(
                chat_id,
                f"⚠️ Ошибка загрузки объявлений.\n\n"
                f"📢 Посмотрите актуальные объявления в канале:\n"
                f"{self.channel_parser.channel_url}"
            )
    
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
                "🏠 <b>Пристройство</b> - кошки ищут дом\n"
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
        
        @self.bot.message_handler(commands=['update_posts'])
        def update_posts_handler(message):
            """Принудительное обновление постов из канала"""
            admin_ids = [int(x) for x in os.environ.get('ADMIN_IDS', '').split(',') if x.strip()]
            if message.from_user.id not in admin_ids:
                return
            
            try:
                # Очищаем кэш и загружаем новые посты
                self.channel_parser.posts_cache = []
                self.channel_parser.last_update = None
                
                self.send_message_with_image(message.chat.id, "🔄 Обновление постов...")
                
                # Асинхронное обновление
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                posts = loop.run_until_complete(self.channel_parser.get_channel_posts())
                loop.close()
                
                self.send_message_with_image(
                    message.chat.id, 
                    f"✅ Обновлено {len(posts)} постов из канала"
                )
            except Exception as e:
                logger.error(f"❌ Ошибка обновления постов: {e}")
                self.send_message_with_image(message.chat.id, f"❌ Ошибка обновления: {e}")
        
        @self.bot.message_handler(func=lambda m: True)
        def message_handler(message):
            self.db_manager.add_user(message.from_user.id, message.from_user.username)
            self.handle_message(message)
    
    def handle_message(self, message):
        """Обрабатывает текстовые сообщения"""
        text = message.text
        chat_id = message.chat.id
        
        try:
            if text == "🏠 Пристройство":
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                markup.add("🐱 Кошки ищут дом")
                markup.add("📝 Подать объявление", "🔙 Назад")
                
                self.bot.send_message(
                    chat_id,
                    "🏠 <b>Пристройство кошек</b>\n\n"
                    "Выберите действие:\n\n"
                    "🐱 <b>Кошки ищут дом</b> - актуальные объявления\n"
                    "📝 <b>Подать объявление</b> - разместить свое объявление",
                    reply_markup=markup,
                    parse_mode="HTML"
                )
            
            elif text == "🐱 Кошки ищут дом":
                # Отправляем посты из канала
                self.send_channel_posts(chat_id)
                
                # Добавляем кнопку назад
                self.bot.send_message(
                    chat_id,
                    "Что еще вас интересует?",
                    reply_markup=self.get_back_keyboard()
                )
            
            elif text == "📝 Подать объявление":
                channel_info = f"""📝 <b>Как подать объявление о пристройстве</b>

📢 <b>Основной канал для объявлений:</b>
<a href="{self.channel_parser.channel_url}">Лапки-ручки Ялта помощь</a>

✍️ <b>Способы подачи объявления:</b>

1️⃣ <b>Написать в канал напрямую</b>
   • Перейдите в канал по ссылке выше
   • Напишите сообщение администраторам

2️⃣ <b>Связаться с координаторами:</b>
   • Анна (пристройство): +7 978 000-00-01
   • Telegram координатора: @adoption_coordinator

📋 <b>Информация для объявления:</b>
🔹 Качественные фото животного
🔹 Возраст, пол, окрас
🔹 Особенности характера
🔹 Состояние здоровья (прививки, стерилизация)
🔹 Ваши контактные данные
🔹 История животного (откуда взялось)

💡 <b>Советы для успешного пристройства:</b>
✅ Честно описывайте характер
✅ Указывайте все проблемы со здоровьем
✅ Делайте фото при хорошем освещении
✅ Отвечайте быстро на вопросы потенциальных хозяев
✅ Проводите знакомство на нейтральной территории

🤝 <b>Волонтеры помогут:</b>
• Составить хорошее описание
• Сделать качественные фото
• Найти передержку на время поиска
• Проверить потенциальных хозяев

📱 <b>Следите за каналом:</b>
В канале постоянно появляются новые объявления и советы по пристройству."""

                self.send_message_with_image(chat_id, channel_info)
            
            elif text == "🔙 Назад":
                self.bot.send_message(
                    chat_id,
                    "🏠 Главное меню:",
                    reply_markup=self.get_main_keyboard()
                )
            
            # Остальные обработчики остаются прежними...
            # (добавьте здесь остальные обработчики из предыдущей версии)
            
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
                "messages": stats["messages_sent"],
                "channel": self.channel_parser.channel_url
            })
        
        @self.app.route('/channel_posts')
        def channel_posts_api():
            """API эндпоинт для получения постов канала"""
            try:
                posts = self.channel_parser.get_cached_posts()
                return jsonify({
                    "status": "ok",
                    "posts_count": len(posts),
                    "posts": posts,
                    "channel_url": self.channel_parser.channel_url,
                    "last_update": self.channel_parser.last_update.isoformat() if self.channel_parser.last_update else None
                })
            except
