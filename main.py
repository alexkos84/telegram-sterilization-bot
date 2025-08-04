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

class ChannelParser:
    """Парсер канала с разделением на кошек и собак"""
    
    def __init__(self):
        self.channel_username = 'Lapki_ruchki_Yalta_help'
        self.channel_url = f'https://t.me/{self.channel_username}'
        self.web_url = f'https://t.me/s/{self.channel_username}'
        self.headers = {'User-Agent': 'Mozilla/5.0'}
        self.posts_cache = []
        self.last_update = None
    
    def get_channel_posts(self, limit: int = 10) -> List[Dict]:
        """Получает последние посты"""
        try:
            logger.info(f"Загрузка постов с {self.web_url}")
            response = requests.get(self.web_url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            message_divs = soup.find_all('div', class_='tgme_widget_message')
            
            posts = []
            for div in message_divs[:limit*2]:
                post_data = self.parse_message_div(div)
                if post_data and (self.is_cat_related(post_data['text']) or self.is_dog_related(post_data['text'])):
                    posts.append(post_data)
                if len(posts) >= limit:
                    break
            
            if posts:
                self.posts_cache = posts
                self.last_update = datetime.now()
                logger.info(f"Получено {len(posts)} постов")
            return posts or self.get_mock_posts()
            
        except Exception as e:
            logger.error(f"Ошибка парсинга: {e}")
            return self.get_mock_posts()
    
    def parse_message_div(self, div) -> Optional[Dict]:
        """Парсит пост"""
        try:
            post_id = div.get('data-post', '').split('/')[-1] or 'unknown'
            text_div = div.find('div', class_='tgme_widget_message_text')
            text = text_div.get_text(strip=True) if text_div else ""
            
            date_elem = div.find('time', datetime=True)
            date_str = "Недавно"
            if date_elem:
                try:
                    dt = datetime.fromisoformat(date_elem['datetime'].replace('Z', '+00:00'))
                    date_str = dt.strftime('%d.%m.%Y %H:%M')
                except:
                    pass
            
            photo_url = None
            photo_wrap = div.find('a', class_='tgme_widget_message_photo_wrap')
            if photo_wrap and photo_wrap.get('style'):
                match = re.search(r"background-image:url\('(.*?)'\)", photo_wrap['style'])
                if match:
                    photo_url = match.group(1)
            
            if not text:
                return None
            
            is_cat = self.is_cat_related(text)
            is_dog = self.is_dog_related(text)
            
            return {
                'id': post_id,
                'text': text,
                'date': date_str,
                'url': f"{self.channel_url}/{post_id}",
                'title': self.extract_title(text, is_cat, is_dog),
                'description': self.extract_description(text),
                'contact': self.extract_contact(text),
                'photo_url': photo_url,
                'is_cat': is_cat,
                'is_dog': is_dog
            }
            
        except Exception as e:
            logger.error(f"Ошибка парсинга div: {e}")
            return None
    
    def extract_title(self, text: str, is_cat: bool, is_dog: bool) -> str:
        """Генерирует заголовок с учетом типа животного"""
        emoji = "🐱" if is_cat else "🐶" if is_dog else "🐾"
        lines = text.split('\n')
        for line in lines[:3]:
            line = line.strip()
            if line and len(line) > 10:
                title = re.sub(r'[^\w\s\-\.,!?а-яёА-ЯЁ]', '', line)
                if len(title) > 50:
                    title = title[:50] + "..."
                return f"{emoji} {title}" if title else f"{emoji} Животное ищет дом"
        return f"{emoji} Животное ищет дом"
    
    def extract_description(self, text: str) -> str:
        clean_text = re.sub(r'@\w+|https?://\S+|\+?\d[\d\s\-\(\)]+', '', text)
        return clean_text[:200] + "..." if len(clean_text) > 200 else clean_text
    
    def extract_contact(self, text: str) -> str:
        phones = re.findall(r'\+?[78][\s\-]?\(?9\d{2}\)?\s?[\d\s\-]{7,10}', text)
        usernames = re.findall(r'@\w+', text)
        contacts = []
        if phones:
            contacts.extend(phones[:1])
        if usernames:
            contacts.extend(usernames[:1])
        return ' • '.join(contacts) if contacts else "См. в канале"
    
    def is_cat_related(self, text: str) -> bool:
        cat_keywords = ['кот', 'кошк', 'котен', 'котик', 'мурз', 'мяу', 'кастр', 'стерил']
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in cat_keywords)
    
    def is_dog_related(self, text: str) -> bool:
        dog_keywords = ['собак', 'щен', 'пес', 'пёс', 'гав', 'лай', 'овчар', 'дог', 'терьер']
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in dog_keywords)
    
    def get_mock_posts(self) -> List[Dict]:
        return [
            {
                'id': '1001',
                'title': '🐱 Котенок Мурзик',
                'text': 'Котенок 2 месяца, ищет дом...',
                'date': '10.08.2025 14:00',
                'url': f'{self.channel_url}/1001',
                'contact': '@cat_volunteer',
                'photo_url': 'https://via.placeholder.com/600x400?text=Котенок',
                'is_cat': True,
                'is_dog': False
            },
            {
                'id': '1002',
                'title': '🐶 Пес Барсик',
                'text': 'Взрослый пес ищет дом...',
                'date': '09.08.2025 12:30',
                'url': f'{self.channel_url}/1002',
                'contact': '+7 978 123-45-67',
                'photo_url': 'https://via.placeholder.com/600x400?text=Собака',
                'is_cat': False,
                'is_dog': True
            }
        ]
    
    def get_cached_posts(self) -> List[Dict]:
        if not self.last_update or (datetime.now() - self.last_update).seconds > 1800:
            try:
                return self.get_channel_posts()
            except:
                pass
        return self.posts_cache if self.posts_cache else self.get_mock_posts()

class PetsBot:
    def __init__(self):
        self.token = os.environ.get('TOKEN')
        if not self.token:
            logger.error("Токен не найден!")
            exit(1)
        
        self.bot = telebot.TeleBot(self.token)
        self.parser = ChannelParser()
        self.app = Flask(__name__)
        self.stats = {"users": set(), "messages": 0}
        
        self.setup_handlers()
        self.setup_routes()
    
    def send_post(self, chat_id: int, post: Dict):
        try:
            post_text = (
                f"{post['title']}\n\n"
                f"{post['description']}\n\n"
                f"📅 {post['date']}\n"
                f"📞 {post['contact']}\n"
                f"🔗 <a href='{post['url']}'>Открыть в канале</a>"
            )
            
            if len(post_text) > 1024:
                post_text = post_text[:1000] + "..."
            
            if post.get('photo_url'):
                try:
                    self.bot.send_photo(
                        chat_id,
                        post['photo_url'],
                        caption=post_text,
                        parse_mode="HTML",
                        reply_markup=types.InlineKeyboardMarkup().add(
                            types.InlineKeyboardButton("📢 Открыть в канале", url=post['url'])
                        )
                    )
                    return
                except Exception as e:
                    logger.error(f"Ошибка отправки фото: {e}")
            
            self.bot.send_message(
                chat_id,
                post_text,
                parse_mode="HTML",
                reply_markup=types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton("📢 Открыть в канале", url=post['url'])
                )
            )
            
        except Exception as e:
            logger.error(f"Ошибка отправки поста: {e}")

    def send_posts_by_type(self, chat_id: int, is_cat: bool = True):
        animal_type = "кошек" if is_cat else "собак"
        try:
            posts = [p for p in self.parser.get_cached_posts() 
                    if (p['is_cat'] if is_cat else p['is_dog'])]
            
            if not posts:
                self.bot.send_message(
                    chat_id,
                    f"😿 Сейчас нет объявлений о {animal_type}.\n"
                    f"📢 Проверьте канал: {self.parser.channel_url}"
                )
                return
            
            self.bot.send_message(
                chat_id,
                f"🐱 <b>КОШКИ ИЩУТ ДОМ</b>\n\n" if is_cat else f"🐶 <b>СОБАКИ ИЩУТ ДОМ</b>\n\n",
                parse_mode="HTML"
            )
            
            for post in posts[:5]:  # Ограничим 5 постами
                self.send_post(chat_id, post)
                time.sleep(0.5)
            
        except Exception as e:
            logger.error(f"Ошибка отправки постов: {e}")
            self.bot.send_message(chat_id, "⚠️ Ошибка загрузки. Попробуйте позже.")

    def get_main_keyboard(self):
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add("🐱 Кошки", "🐶 Собаки")
        markup.add("🏥 Стерилизация", "📞 Контакты", "ℹ️ О проекте")
        return markup
    
    def setup_handlers(self):
        @self.bot.message_handler(commands=['start'])
        def start_handler(message):
            self.stats["users"].add(message.from_user.id)
            self.stats["messages"] += 1
            self.bot.send_message(
                message.chat.id,
                "🐾 <b>Помощник для животных Ялты</b>\n\n"
                "Выберите раздел:\n"
                "🐱 <b>Кошки</b> - ищут дом\n"
                "🐶 <b>Собаки</b> - ищут дом\n"
                "🏥 <b>Стерилизация</b> - информация\n"
                "📞 <b>Контакты</b> - волонтеры",
                parse_mode="HTML",
                reply_markup=self.get_main_keyboard()
            )
        
        @self.bot.message_handler(func=lambda m: m.text in ["🐱 Кошки", "🐶 Собаки"])
        def animals_handler(message):
            is_cat = message.text == "🐱 Кошки"
            self.send_posts_by_type(message.chat.id, is_cat)
        
        @self.bot.message_handler(func=lambda m: m.text == "📞 Контакты")
        def contacts_handler(message):
            self.bot.send_message(
                message.chat.id,
                "📞 <b>Контакты</b>\n\n"
                "🐱 Кошки: @cat_volunteer\n"
                "🐶 Собаки: @dog_volunteer\n"
                "🏥 Клиника: +7 978 000-00-01",
                parse_mode="HTML"
            )
        
        @self.bot.message_handler(func=lambda m: True)
        def fallback_handler(message):
            self.bot.send_message(
                message.chat.id,
                "Используйте кнопки меню или команду /start",
                reply_markup=self.get_main_keyboard()
            )
    
    def setup_routes(self):
        @self.app.route(f'/{self.token}', methods=['POST'])
        def webhook():
            if request.headers.get('content-type') == 'application/json':
                update = telebot.types.Update.de_json(request.get_data().decode('utf-8'))
                self.bot.process_new_updates([update])
                return '', 200
            return 'Bad request', 400
        
        @self.app.route('/')
        def home():
            return jsonify({
                "status": "Pets Bot is running",
                "users": len(self.stats["users"]),
                "messages": self.stats["messages"]
            })
    
    def run(self):
        logger.info("Запуск бота...")
        try:
            self.parser.get_cached_posts()  # Предзагрузка
        except Exception as e:
            logger.warning(f"Ошибка предзагрузки: {e}")
        
        self.app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

if __name__ == "__main__":
    bot = PetsBot()
    bot.run()
