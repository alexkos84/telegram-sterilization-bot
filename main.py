import os
import telebot
from telebot import types
from flask import Flask, request, jsonify
from datetime import datetime
import time
import logging
import json
import requests
from bs4 import BeautifulSoup
import re
from typing import Dict, List, Optional, Tuple

# 🔧 Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='bot.log'
)
logger = logging.getLogger(__name__)

# 🗂️ Загрузка текстов
def load_text(filename: str) -> str:
    """Загружает HTML-контент из файла"""
    try:
        path = os.path.join("assets", "texts", filename)
        with open(path, encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Ошибка загрузки {filename}: {str(e)}")
        return f"<b>Контент временно недоступен</b>"

# 🖼️ Проверка изображений
def get_image_path(filename: str) -> Optional[str]:
    path = os.path.join("assets", "images", filename)
    return path if os.path.exists(path) else None

# 📚 Текстовые ресурсы
TEXTS = {
    "paid_steril": load_text("paid_sterilization.html") or "Платная стерилизация",
    "free_steril": load_text("free_sterilization.html") or "Бесплатная стерилизация",
    "contacts": load_text("contacts.html") or "Контакты",
    "about": load_text("about.html") or "О проекте"
}

# 🏷️ Изображения
IMAGES = {
    "paid": get_image_path("paid.jpg"),
    "free": get_image_path("free.jpg"),
    "cats": get_image_path("cats.jpg"),
    "dogs": get_image_path("dogs.jpg")
}

class ChannelParser:
    """Парсер Telegram каналов"""
    
    CHANNELS = {
        "cats": {
            "username": "Lapki_ruchki_Yalta_help",
            "url": "https://t.me/Lapki_ruchki_Yalta_help",
            "keywords": ["кот", "кошк", "котен", "котик", "мурз", "мяу"]
        },
        "dogs": {
            "username": "yalta_aninmals",
            "url": "https://t.me/yalta_aninmals",
            "keywords": ["собак", "щен", "пес", "гав", "лайк", "овчарк"]
        }
    }
    
    def __init__(self):
        self.cache = {"cats": [], "dogs": []}
        self.last_update = None
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

    def parse_channel(self, channel_type: str, limit: int = 3) -> List[Dict]:
        """Парсит указанный канал"""
        channel = self.CHANNELS[channel_type]
        try:
            url = f"https://t.me/s/{channel['username']}"
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            posts = []
            
            for message in soup.find_all('div', class_='tgme_widget_message')[:limit*2]:
                post = self._parse_message(message, channel)
                if post and self._is_animal_post(post['text'], channel['keywords']):
                    posts.append(post)
                    if len(posts) >= limit:
                        break
            
            return posts
        
        except Exception as e:
            logger.error(f"Ошибка парсинга {channel_type}: {str(e)}")
            return []

    def _parse_message(self, message, channel) -> Optional[Dict]:
        """Парсит отдельное сообщение"""
        try:
            text_div = message.find('div', class_='tgme_widget_message_text')
            if not text_div:
                return None
                
            text = text_div.get_text('\n').strip()
            post_id = message.get('data-post', '').split('/')[-1]
            
            # Парсинг фото
            photo_style = message.find('a', class_='tgme_widget_message_photo_wrap').get('style', '')
            photo_url = re.search(r"url\('(.*?)'\)", photo_style).group(1) if photo_style else None
            
            # Парсинг даты
            time_tag = message.find('time', {'datetime': True})
            date = time_tag['datetime'] if time_tag else "Недавно"
            
            return {
                'id': post_id,
                'text': text,
                'photo_url': photo_url,
                'date': date,
                'url': f"{channel['url']}/{post_id}",
                'type': 'cats' if channel['username'] == self.CHANNELS['cats']['username'] else 'dogs'
            }
            
        except Exception as e:
            logger.error(f"Ошибка парсинга сообщения: {str(e)}")
            return None

    def _is_animal_post(self, text: str, keywords: List[str]) -> bool:
        """Проверяет, относится ли пост к животным"""
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in keywords)

    def get_posts(self, animal_type: str, force_update: bool = False) -> List[Dict]:
        """Возвращает посты с кэшированием"""
        if force_update or not self.cache[animal_type] or (datetime.now() - self.last_update).seconds > 3600:
            self.cache[animal_type] = self.parse_channel(animal_type)
            self.last_update = datetime.now()
        return self.cache[animal_type] or self._get_mock_posts(animal_type)

    def _get_mock_posts(self, animal_type: str) -> List[Dict]:
        """Возвращает тестовые данные"""
        if animal_type == 'cats':
            return [{
                'id': '1001',
                'text': 'Котенок ищет дом. Мальчик, 2 месяца, привит.',
                'photo_url': None,
                'date': '2023-01-01',
                'url': 'https://t.me/Lapki_ruchki_Yalta_help/1001',
                'type': 'cats'
            }]
        else:
            return [{
                'id': '2001',
                'text': 'Щенок ищет хозяина. Девочка, 3 месяца.',
                'photo_url': None,
                'date': '2023-01-01',
                'url': 'https://t.me/yalta_aninmals/2001',
                'type': 'dogs'
            }]

class AnimalBot:
    """Основной класс бота"""
    
    def __init__(self):
        self.token = os.getenv('TELEGRAM_TOKEN')
        if not self.token:
            logger.error("Токен не найден!")
            raise ValueError("Токен Telegram не установлен")
            
        self.bot = telebot.TeleBot(self.token)
        self.parser = ChannelParser()
        self.app = Flask(__name__)
        self._setup_handlers()
        
    def _send_animal_posts(self, chat_id: int, animal_type: str):
        """Отправляет посты о животных"""
        try:
            posts = self.parser.get_posts(animal_type)
            if not posts:
                self.bot.send_message(chat_id, "😿 Нет актуальных объявлений")
                return
                
            emoji = "🐱" if animal_type == "cats" else "🐶"
            self.bot.send_message(
                chat_id,
                f"{emoji} <b>Последние объявления</b>\n\n"
                f"Канал: {self.parser.CHANNELS[animal_type]['url']}",
                parse_mode="HTML"
            )
            
            for post in posts:
                self._send_post(chat_id, post)
                
        except Exception as e:
            logger.error(f"Ошибка отправки постов: {str(e)}")
            self.bot.send_message(chat_id, "⚠️ Ошибка загрузки объявлений")

    def _send_post(self, chat_id: int, post: Dict):
        """Отправляет одно объявление"""
        try:
            text = (
                f"{'🐱' if post['type'] == 'cats' else '🐶'} <b>Новое объявление</b>\n\n"
                f"{post['text']}\n\n"
                f"🔗 <a href='{post['url']}'>Открыть в канале</a>"
            )
            
            if post.get('photo_url'):
                self.bot.send_photo(
                    chat_id,
                    post['photo_url'],
                    caption=text,
                    parse_mode="HTML"
                )
            else:
                self.bot.send_message(
                    chat_id,
                    text,
                    parse_mode="HTML"
                )
        except Exception as e:
            logger.error(f"Ошибка отправки поста: {str(e)}")

    def _setup_handlers(self):
        """Настройка обработчиков команд"""
        
        @self.bot.message_handler(commands=['start'])
        def start(message):
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.row("🏥 Стерилизация", "🏠 Пристройство")
            markup.row("📞 Контакты", "ℹ️ О проекте")
            
            self.bot.send_message(
                message.chat.id,
                "🐾 <b>Помощник для животных Ялты</b>\n\n"
                "Выберите раздел:",
                reply_markup=markup,
                parse_mode="HTML"
            )

        @self.bot.message_handler(func=lambda m: m.text == "🏥 Стерилизация")
        def sterilization(message):
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.row("💰 Платная", "🆓 Бесплатная")
            markup.add("🔙 Назад")
            
            self.bot.send_message(
                message.chat.id,
                "🏥 <b>Программы стерилизации</b>\n\nВыберите тип:",
                reply_markup=markup,
                parse_mode="HTML"
            )

        @self.bot.message_handler(func=lambda m: m.text == "💰 Платная")
        def paid_sterilization(message):
            try:
                if IMAGES['paid']:
                    with open(IMAGES['paid'], 'rb') as photo:
                        self.bot.send_photo(
                            message.chat.id,
                            photo,
                            caption=TEXTS['paid_steril'],
                            parse_mode="HTML"
                        )
                else:
                    self.bot.send_message(
                        message.chat.id,
                        TEXTS['paid_steril'],
                        parse_mode="HTML"
                    )
            except Exception as e:
                logger.error(f"Ошибка отправки платной стерилизации: {str(e)}")
                self.bot.send_message(message.chat.id, "⚠️ Ошибка загрузки информации")

        @self.bot.message_handler(func=lambda m: m.text == "🆓 Бесплатная")
        def free_sterilization(message):
            try:
                if IMAGES['free']:
                    with open(IMAGES['free'], 'rb') as photo:
                        self.bot.send_photo(
                            message.chat.id,
                            photo,
                            caption=TEXTS['free_steril'],
                            parse_mode="HTML"
                        )
                else:
                    self.bot.send_message(
                        message.chat.id,
                        TEXTS['free_steril'],
                        parse_mode="HTML"
                    )
            except Exception as e:
                logger.error(f"Ошибка отправки бесплатной стерилизации: {str(e)}")
                self.bot.send_message(message.chat.id, "⚠️ Ошибка загрузки информации")

        @self.bot.message_handler(func=lambda m: m.text == "🏠 Пристройство")
        def adoption(message):
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.row("🐱 Кошки", "🐶 Собаки")
            markup.add("🔙 Назад")
            
            self.bot.send_message(
                message.chat.id,
                "🏠 <b>Пристройство животных</b>\n\nВыберите категорию:",
                reply_markup=markup,
                parse_mode="HTML"
            )

        @self.bot.message_handler(func=lambda m: m.text == "🐱 Кошки")
        def cats(message):
            self._send_animal_posts(message.chat.id, "cats")

        @self.bot.message_handler(func=lambda m: m.text == "🐶 Собаки")
        def dogs(message):
            self._send_animal_posts(message.chat.id, "dogs")

        @self.bot.message_handler(func=lambda m: m.text == "📞 Контакты")
        def contacts(message):
            self.bot.send_message(
                message.chat.id,
                TEXTS['contacts'],
                parse_mode="HTML"
            )

        @self.bot.message_handler(func=lambda m: m.text == "ℹ️ О проекте")
        def about(message):
            self.bot.send_message(
                message.chat.id,
                TEXTS['about'],
                parse_mode="HTML"
            )

        @self.bot.message_handler(func=lambda m: m.text == "🔙 Назад")
        def back(message):
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.row("🏥 Стерилизация", "🏠 Пристройство")
            markup.row("📞 Контакты", "ℹ️ О проекте")
            
            self.bot.send_message(
                message.chat.id,
                "Главное меню:",
                reply_markup=markup
            )

    def run(self):
        """Запуск бота"""
        if os.getenv('USE_WEBHOOK', 'false').lower() == 'true':
            self._setup_webhook()
            self.app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
        else:
            self.bot.polling()

    def _setup_webhook(self):
        """Настройка webhook"""
        self.bot.remove_webhook()
        time.sleep(1)
        webhook_url = f"{os.getenv('WEBHOOK_URL')}/{self.token}"
        self.bot.set_webhook(url=webhook_url)
        logger.info(f"Webhook установлен на {webhook_url}")

if __name__ == '__main__':
    # Создаем необходимые папки
    os.makedirs("assets/texts", exist_ok=True)
    os.makedirs("assets/images", exist_ok=True)
    
    # Запуск бота
    try:
        bot = AnimalBot()
        bot.run()
    except Exception as e:
        logger.critical(f"Ошибка запуска бота: {str(e)}")
