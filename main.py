import os
import telebot
from telebot import types
from flask import Flask, request, jsonify
from datetime import datetime
import time
import logging
import requests
from bs4 import BeautifulSoup
import re
from typing import Dict, List, Optional

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class GroupParser:
    """Усовершенствованный парсер для Telegram групп"""
    
    def __init__(self):
        self.groups = [
            {
                'username': 'lapki_ruchki_yalta',
                'url': 'https://t.me/lapki_ruchki_yalta',
                'type': 'cats'
            },
            {
                'username': 'yalta_aninmals',
                'url': 'https://t.me/yalta_aninmals',
                'type': 'dogs'
            }
        ]
        self.posts_cache = []
        self.last_update = None
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7'
        })

    def get_posts(self, group_type: str = 'all', limit: int = 5) -> List[Dict]:
        """Основной метод получения постов"""
        try:
            posts = []
            for group in self.groups:
                if group_type != 'all' and group['type'] != group_type:
                    continue
                    
                posts.extend(self._parse_group(group, limit))
            
            if posts:
                self.posts_cache = posts
                self.last_update = datetime.now()
                logger.info(f"Получено {len(posts)} постов")
            else:
                logger.warning("Использую тестовые данные")
                posts = self._get_mock_posts(group_type)
            
            return posts

        except Exception as e:
            logger.error(f"Ошибка: {e}")
            return self._get_mock_posts(group_type)

    def _parse_group(self, group: Dict, limit: int) -> List[Dict]:
        """Парсинг конкретной группы"""
        try:
            web_url = f'https://t.me/s/{group["username"]}'
            logger.info(f"Парсинг группы {web_url}")
            
            response = self.session.get(web_url, timeout=15)
            response.raise_for_status()
            
            if "tgme_widget_message" not in response.text:
                logger.error("Не найдены сообщения")
                return []
                
            soup = BeautifulSoup(response.text, 'html.parser')
            messages = soup.find_all('div', class_='tgme_widget_message', limit=limit*2)
            
            parsed_posts = []
            for msg in messages:
                post = self._parse_message(msg, group)
                if post and self._is_animal_post(post['text'], group['type']):
                    parsed_posts.append(post)
                    if len(parsed_posts) >= limit:
                        break
            
            return parsed_posts

        except Exception as e:
            logger.error(f"Ошибка парсинга группы: {e}")
            return []

    def _parse_message(self, message_div, group: Dict) -> Optional[Dict]:
        """Парсинг отдельного сообщения"""
        try:
            # Извлекаем основные данные
            post_id = message_div.get('data-post', '').split('/')[-1]
            text_div = message_div.find('div', class_='tgme_widget_message_text')
            text = text_div.get_text('\n', strip=True) if text_div else ""
            
            # Дата сообщения
            time_tag = message_div.find('time', datetime=True)
            date_str = time_tag['datetime'] if time_tag else "Недавно"
            
            # Медиа-вложения
            photo_url = None
            photo_wrap = message_div.find('a', class_='tgme_widget_message_photo_wrap')
            if photo_wrap and 'style' in photo_wrap.attrs:
                match = re.search(r"background-image:url\('(.*?)'\)", photo_wrap['style'])
                photo_url = match.group(1) if match else None
            
            if not text and not photo_url:
                return None
                
            return {
                'id': post_id,
                'text': text,
                'date': date_str,
                'url': f"{group['url']}/{post_id}",
                'photo_url': photo_url,
                'type': group['type']
            }

        except Exception as e:
            logger.error(f"Ошибка парсинга сообщения: {e}")
            return None

    def _is_animal_post(self, text: str, animal_type: str) -> bool:
        """Проверка что пост о животных"""
        keywords = {
            'cats': ['кот', 'кошк', 'котен', 'котик', 'мяу', 'мур'],
            'dogs': ['собак', 'щен', 'пес', 'гав', 'лайк', 'овчарк']
        }
        text_lower = text.lower()
        return any(word in text_lower for word in keywords.get(animal_type, []))

    def _get_mock_posts(self, group_type: str) -> List[Dict]:
        """Тестовые данные"""
        mock_data = {
            'cats': [{
                'id': 'mock1',
                'text': 'Котенок ищет дом. Мальчик, 2 месяца, привит',
                'date': datetime.now().isoformat(),
                'url': 'https://t.me/lapki_ruchki_yalta/mock1',
                'photo_url': 'https://via.placeholder.com/600x400?text=Котенок',
                'type': 'cats'
            }],
            'dogs': [{
                'id': 'mock2',
                'text': 'Щенок ищет хозяина. Девочка, 3 месяца',
                'date': datetime.now().isoformat(),
                'url': 'https://t.me/yalta_aninmals/mock2',
                'photo_url': 'https://via.placeholder.com/600x400?text=Щенок',
                'type': 'dogs'
            }]
        }
        return mock_data.get(group_type, [])

class AnimalBot:
    """Основной класс бота"""
    
    def __init__(self):
        self.token = os.getenv('TELEGRAM_TOKEN')
        if not self.token:
            logger.error("Токен не найден!")
            raise ValueError("Токен Telegram не установлен")
            
        self.bot = telebot.TeleBot(self.token)
        self.parser = GroupParser()
        self.app = Flask(__name__)
        
        self._register_handlers()
        self._setup_routes()

    def _register_handlers(self):
        """Регистрация обработчиков команд"""
        
        @self.bot.message_handler(commands=['start'])
        def start(message):
            self._send_main_menu(message.chat.id)

        @self.bot.message_handler(func=lambda m: m.text == '🐱 Кошки')
        def show_cats(message):
            self._send_posts(message.chat.id, 'cats')

        @self.bot.message_handler(func=lambda m: m.text == '🐶 Собаки')
        def show_dogs(message):
            self._send_posts(message.chat.id, 'dogs')

        @self.bot.message_handler(func=lambda m: m.text == '🔄 Обновить')
        def update_posts(message):
            self.parser.posts_cache = []
            self.bot.send_message(message.chat.id, "Обновляю данные...")
            self._send_posts(message.chat.id, 'all')

    def _send_main_menu(self, chat_id):
        """Отправка главного меню"""
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.row('🐱 Кошки', '🐶 Собаки')
        markup.row('🔄 Обновить')
        
        self.bot.send_message(
            chat_id,
            "🐾 Выберите категорию:",
            reply_markup=markup
        )

    def _send_posts(self, chat_id, animal_type):
        """Отправка постов пользователю"""
        posts = self.parser.get_posts(animal_type)
        
        if not posts:
            self.bot.send_message(chat_id, "😿 Нет доступных объявлений")
            return
            
        for post in posts:
            try:
                if post.get('photo_url'):
                    self.bot.send_photo(
                        chat_id,
                        post['photo_url'],
                        caption=self._format_post(post),
                        parse_mode='HTML'
                    )
                else:
                    self.bot.send_message(
                        chat_id,
                        self._format_post(post),
                        parse_mode='HTML'
                    )
                time.sleep(0.5)
            except Exception as e:
                logger.error(f"Ошибка отправки поста: {e}")

    def _format_post(self, post: Dict) -> str:
        """Форматирование текста поста"""
        return (
            f"<b>{'🐱' if post['type'] == 'cats' else '🐶'} {post['text'][:100]}...</b>\n\n"
            f"📅 {post['date']}\n"
            f"🔗 <a href='{post['url']}'>Открыть в группе</a>"
        )

    def _setup_routes(self):
        """Настройка Flask маршрутов"""
        
        @self.app.route(f'/{self.token}', methods=['POST'])
        def webhook():
            json_str = request.get_data().decode('UTF-8')
            update = telebot.types.Update.de_json(json_str)
            self.bot.process_new_updates([update])
            return '', 200
            
        @self.app.route('/')
        def index():
            return "Бот работает 🐾"

    def run(self):
        """Запуск бота"""
        self.bot.remove_webhook()
        time.sleep(1)
        
        webhook_url = os.getenv('WEBHOOK_URL')
        if webhook_url:
            self.bot.set_webhook(url=f"{webhook_url}/{self.token}")
            self.app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
        else:
            self.bot.polling()

if __name__ == '__main__':
    bot = AnimalBot()
    bot.run()
