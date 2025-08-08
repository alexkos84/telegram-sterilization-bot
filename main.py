import os
import re
import logging
from typing import List, Dict, Optional
from datetime import datetime
import telebot
from telebot import types
import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class GroupParser:
    def __init__(self):
        self.group_username = 'lapki_ruchki_yalta'
        self.group_url = f'https://t.me/{self.group_username}'
        self.posts_cache = []
        self.last_update = None
        self.phone_patterns = [
            r'\+?7[\s\-]?\(?9\d{2}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',  # RU
            r'\+?380[\s\-]?\d{2}[\s\-]?\d{3}[\s\-]?\d{4}',  # UA
            r'0\d{9}'  # UA локальный
        ]

    def extract_phones(self, text: str) -> List[str]:
        """Извлекает все телефонные номера из текста"""
        phones = []
        for pattern in self.phone_patterns:
            phones.extend(re.findall(pattern, text))
        return phones

    def parse_webpage(self) -> List[Dict]:
        """Парсит веб-страницу группы (если доступно)"""
        try:
            url = f'https://t.me/s/{self.group_username}'
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            messages = soup.find_all('div', class_='tgme_widget_message')
            
            posts = []
            for msg in messages:
                text_elem = msg.find('div', class_='tgme_widget_message_text')
                if not text_elem:
                    continue
                    
                text = text_elem.get_text()
                phones = self.extract_phones(text)
                if not phones:
                    continue
                
                # Извлечение фото
                photo_elem = msg.find('a', class_='tgme_widget_message_photo_wrap')
                photo_url = None
                if photo_elem and photo_elem.get('style'):
                    match = re.search(r"url\('(.*?)'\)", photo_elem['style'])
                    if match:
                        photo_url = match.group(1)
                
                # Извлечение даты
                date_elem = msg.find('time', {'datetime': True})
                post_date = "Недавно"
                if date_elem:
                    try:
                        dt = datetime.strptime(date_elem['datetime'], '%Y-%m-%dT%H:%M:%S%z')
                        post_date = dt.strftime('%d.%m.%Y %H:%M')
                    except:
                        pass
                
                posts.append({
                    'text': text,
                    'phones': phones,
                    'date': post_date,
                    'photo_url': photo_url,
                    'url': f"{self.group_url}/{msg.get('data-post', '').split('/')[-1]}"
                })
                
                if len(posts) >= 15:  # Лимит парсинга
                    break
            
            return posts
            
        except Exception as e:
            logger.error(f"Ошибка парсинга: {e}")
            return []

    def get_posts_with_phones(self, limit=5) -> List[Dict]:
        """Возвращает посты с телефонами"""
        try:
            # Пробуем получить свежие посты
            fresh_posts = self.parse_webpage()
            if fresh_posts:
                self.posts_cache = fresh_posts
                self.last_update = datetime.now()
                return fresh_posts[:limit]
            
            # Если не получилось, возвращаем кэш
            return self.posts_cache[:limit] if self.posts_cache else self.get_mock_posts()
            
        except Exception as e:
            logger.error(f"Ошибка получения постов: {e}")
            return self.get_mock_posts()

    def get_mock_posts(self) -> List[Dict]:
        """Возвращает тестовые данные"""
        return [{
            'text': "Котенок ищет дом. Очень ласковый. Тел: +79781234567, 0652123456",
            'phones': ["+79781234567", "0652123456"],
            'date': datetime.now().strftime('%d.%m.%Y %H:%M'),
            'photo_url': "https://via.placeholder.com/600x400?text=Котенок",
            'url': "https://t.me/lapki_ruchki_yalta/123"
        }]

class AnimalBot:
    def __init__(self):
        self.token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not self.token:
            raise ValueError("Не задан TELEGRAM_BOT_TOKEN")
            
        self.bot = telebot.TeleBot(self.token)
        self.parser = GroupParser()
        self.app = Flask(__name__)
        self.setup_handlers()
        
    def setup_handlers(self):
        @self.bot.message_handler(commands=['start'])
        def start(message):
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.add("🐱 Посты с телефонами", "🆘 Помощь")
            self.bot.send_message(
                message.chat.id,
                "🔍 Бот для поиска объявлений с контактами из @lapki_ruchki_yalta",
                reply_markup=markup
            )

        @self.bot.message_handler(func=lambda m: m.text == "🐱 Посты с телефонами")
        def show_posts(message):
            self.bot.send_chat_action(message.chat.id, 'typing')
            posts = self.parser.get_posts_with_phones(limit=5)
            
            if not posts:
                self.bot.send_message(message.chat.id, "😔 Сейчас нет объявлений с контактами")
                return
                
            for post in posts:
                try:
                    text = (
                        f"📅 {post['date']}\n\n"
                        f"{post['text']}\n\n"
                        f"📱 Телефоны: {', '.join(post['phones'])}\n"
                        f"🔗 <a href='{post['url']}'>Открыть в группе</a>"
                    )
                    
                    if post.get('photo_url'):
                        self.bot.send_photo(
                            message.chat.id,
                            post['photo_url'],
                            caption=text,
                            parse_mode='HTML'
                        )
                    else:
                        self.bot.send_message(
                            message.chat.id,
                            text,
                            parse_mode='HTML'
                        )
                except Exception as e:
                    logger.error(f"Ошибка отправки поста: {e}")

        @self.bot.message_handler(func=lambda m: m.text == "🆘 Помощь")
        def help(message):
            self.bot.send_message(
                message.chat.id,
                "ℹ️ Этот бот показывает объявления с телефонами из группы @lapki_ruchki_yalta\n\n"
                "🐱 Используйте кнопку 'Посты с телефонами' для просмотра\n\n"
                "⚠️ Бот не сохраняет номера телефонов и не звонит сам"
            )

    def run(self):
        """Запуск бота"""
        if os.getenv('WEBHOOK_MODE') == 'True':
            # Настройка вебхука для работы на сервере
            self.app.route(f'/{self.token}', methods=['POST'])(lambda: self.bot.process_new_updates(
                [telebot.types.Update.de_json(request.stream.read().decode("utf-8"))]
            ))
            self.app.run(host='0.0.0.0', port=int(os.getenv('PORT', 8080)))
        else:
            # Локальный запуск с polling
            self.bot.polling(none_stop=True)

if __name__ == '__main__':
    bot = AnimalBot()
    bot.run()
