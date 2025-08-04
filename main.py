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
from typing import Dict, List, Optional

# 🔧 Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SimpleChannelParser:
    """Улучшенный парсер канала с поддержкой фото"""
    
    def __init__(self):
        self.channel_username = 'Lapki_ruchki_Yalta_help'
        self.channel_url = 'https://t.me/Lapki_ruchki_Yalta_help'
        self.web_url = f'https://t.me/s/{self.channel_username}'
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.posts_cache = []
        self.last_update = None
    
    def get_channel_posts(self, limit: int = 3) -> List[Dict]:
        """Получает последние посты с фото"""
        try:
            logger.info(f"🌐 Загрузка постов с {self.web_url}")
            response = requests.get(self.web_url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            message_divs = soup.find_all('div', class_='tgme_widget_message')
            
            posts = []
            for div in message_divs[:limit*2]:
                post_data = self.parse_message_div(div)
                if post_data and self.is_cat_related(post_data.get('text', '')):
                    posts.append(post_data)
                    
                if len(posts) >= limit:
                    break
            
            if posts:
                self.posts_cache = posts
                self.last_update = datetime.now()
                logger.info(f"✅ Получено {len(posts)} постов (с фото: {sum(1 for p in posts if p['photo_url'])})")
            else:
                logger.warning("⚠️ Не найдено подходящих постов")
                
            return posts or self.get_mock_posts()
            
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга: {e}")
            return self.get_mock_posts()
    
    def parse_message_div(self, div) -> Optional[Dict]:
        """Парсит пост, извлекая текст и фото"""
        try:
            # Базовые данные
            post_id = div.get('data-post', '').split('/')[-1] or 'unknown'
            text_div = div.find('div', class_='tgme_widget_message_text')
            text = text_div.get_text(strip=True) if text_div else ""
            
            # Дата
            date_elem = div.find('time', datetime=True)
            date_str = "Недавно"
            if date_elem:
                try:
                    dt = datetime.fromisoformat(date_elem['datetime'].replace('Z', '+00:00'))
                    date_str = dt.strftime('%d.%m.%Y %H:%M')
                except:
                    pass
            
            # Фото (основное превью)
            photo_url = None
            photo_wrap = div.find('a', class_='tgme_widget_message_photo_wrap')
            if photo_wrap and photo_wrap.get('style'):
                match = re.search(r"background-image:url\('(.*?)'\)", photo_wrap['style'])
                if match:
                    photo_url = match.group(1)
            
            if not text:
                return None
            
            return {
                'id': post_id,
                'text': text,
                'date': date_str,
                'url': f"{self.channel_url}/{post_id}" if post_id else self.channel_url,
                'title': self.extract_title(text),
                'description': self.extract_description(text),
                'contact': self.extract_contact(text),
                'photo_url': photo_url,
                'has_photo': bool(photo_url)
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга div: {e}")
            return None
    
    # ... (остальные методы класса остаются без изменений: extract_title, extract_description, 
    # extract_contact, is_cat_related, get_mock_posts, get_cached_posts)

class CatBotWithPhotos:
    """Бот с поддержкой фото из постов"""
    
    def __init__(self):
        self.token = os.environ.get('TOKEN')
        if not self.token:
            logger.error("❌ TOKEN не найден!")
            exit(1)
        
        self.bot = telebot.TeleBot(self.token)
        self.parser = SimpleChannelParser()
        self.app = Flask(__name__)
        self.port = int(os.environ.get('PORT', 8080))
        self.webhook_url = os.environ.get('WEBHOOK_URL')
        self.stats = {"users": set(), "messages": 0}
        
        self.setup_handlers()
        self.setup_routes()
    
    def send_post(self, chat_id: int, post: Dict):
        """Отправляет один пост с фото или текстом"""
        try:
            # Формируем текст
            post_text = (
                f"🐱 <b>{post['title']}</b>\n\n"
                f"{post['description']}\n\n"
                f"📅 {post['date']}\n"
                f"📞 {post['contact']}\n"
                f"🔗 <a href='{post['url']}'>Открыть в канале</a>"
            )
            
            # Укорачиваем текст если нужно (ограничение Telegram)
            if len(post_text) > 1024:
                post_text = post_text[:1000] + "..."
            
            # Отправляем фото с подписью если есть
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
                    logger.error(f"❌ Ошибка отправки фото: {e}")
            
            # Если фото нет или не удалось отправить
            self.bot.send_message(
                chat_id,
                post_text,
                parse_mode="HTML",
                disable_web_page_preview=False,
                reply_markup=types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton("📢 Открыть в канале", url=post['url'])
                )
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки поста: {e}")

    def send_channel_posts(self, chat_id: int):
        """Отправляет все посты с фото"""
        try:
            posts = self.parser.get_cached_posts()
            
            if not posts:
                self.bot.send_message(
                    chat_id,
                    "😿 Сейчас нет актуальных объявлений.\n"
                    f"📢 Проверьте канал: {self.parser.channel_url}"
                )
                return
            
            # Отправляем заголовок
            self.bot.send_message(
                chat_id,
                f"🐱 <b>КОШКИ ИЩУТ ДОМ</b>\n\n"
                f"📢 Последние объявления из канала:\n"
                f"<a href='{self.parser.channel_url}'>Лапки-ручки Ялта</a>",
                parse_mode="HTML"
            )
            
            # Отправляем каждый пост
            for post in posts:
                self.send_post(chat_id, post)
                time.sleep(0.5)  # Защита от флуда
            
            # Отправляем футер
            self.bot.send_message(
                chat_id,
                "💡 <b>Как помочь?</b>\n\n"
                "🏠 <b>Взять кошку:</b>\nСвяжитесь по контактам из объявления\n\n"
                "📢 <b>Канал:</b> @Lapki_ruchki_Yalta_help\n\n"
                "🤝 <b>Стать волонтером:</b>\nНапишите в канал",
                parse_mode="HTML"
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки постов: {e}")
            self.bot.send_message(
                chat_id,
                f"⚠️ Ошибка загрузки объявлений\n\n"
                f"Попробуйте позже или посетите канал:\n"
                f"{self.parser.channel_url}"
            )

    # ... (методы get_main_keyboard, get_adoption_keyboard, setup_handlers, 
    # setup_routes, setup_webhook остаются без изменений, как в исходном коде)

    def run(self):
        """Запуск бота с фото-поддержкой"""
        logger.info("🚀 Запуск CatBot с поддержкой фото...")
        
        # Предзагрузка постов
        try:
            posts = self.parser.get_cached_posts()
            logger.info(f"✅ Предзагружено {len(posts)} постов")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка предзагрузки: {e}")
        
        if self.setup_webhook():
            self.app.run(host='0.0.0.0', port=self.port)
        else:
            logger.error("🚨 Ошибка webhook, запуск в polling режиме")
            self.bot.polling()

if __name__ == "__main__":
    bot = CatBotWithPhotos()
    bot.run()
