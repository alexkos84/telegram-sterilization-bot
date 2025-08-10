import os
import telebot
from telebot import types
from flask import Flask, request, jsonify
from datetime import datetime, timedelta
import time
import logging
import json
import requests
from bs4 import BeautifulSoup
import re
from typing import Dict, List, Optional
import random
from urllib.parse import quote_plus
import cloudscraper
import html

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class AnimalNewsParser:
    """Парсер новостей о животных из каналов Ялты"""
    
    def __init__(self):
        self.channels = [
            {
                'username': 'yalta_podslushano',
                'url': 'https://t.me/yalta_podslushano',
                'name': 'Ялта Подслушано'
            },
            {
                'username': 'yaltaya',
                'url': 'https://t.me/yaltaya',
                'name': 'Ялтая'
            },
            {
                'username': 'yalta_animals',
                'url': 'https://t.me/yalta_animals',
                'name': 'Ялта Животные'
            },
            {
                'username': 'yalta_zoo',
                'url': 'https://t.me/yalta_zoo',
                'name': 'Ялта Зоо'
            },
            {
                'username': 'yalta_pets',
                'url': 'https://t.me/yalta_pets',
                'name': 'Ялта Питомцы'
            }
        ]
        
        self.animal_keywords = [
            'кошк', 'кот', 'котён', 'котен', 'котэ', 'котейк', 'кис', 'кис-кис',
            'соба', 'пёс', 'пес', 'щен', 'собак', 'псин', 'хвост', 'лап',
            'животн', 'питом', 'звер', 'зверюшк', 'зверёк', 'питомец',
            'пристр', 'потерял', 'нашел', 'найдён', 'найден', 'пропал', 'пропада',
            'приют', 'передерж', 'ветеринар', 'корм', 'стерилиз', 'кастрац'
        ]
        
        self.posts_cache = []
        self.last_update = None
        self.last_attempt = None
        self.failure_count = 0
        
        # Инициализация CloudScraper
        try:
            self.scraper = cloudscraper.create_scraper(
                browser={
                    'browser': 'chrome',
                    'platform': 'windows',
                    'mobile': False
                }
            )
        except:
            self.scraper = requests.Session()
            logger.warning("⚠️ CloudScraper недоступен, используем обычный requests")
        
        # User-Agents для ротации
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
        ]
    
    def is_recent_post(self, timestamp: float) -> bool:
        """Проверяет, является ли пост свежим (за последние 24 часа)"""
        if not timestamp:
            return False
        post_time = datetime.fromtimestamp(timestamp)
        return (datetime.now() - post_time) < timedelta(days=1)
    
    def get_animal_posts(self, limit_per_channel: int = 5) -> List[Dict]:
        """Получает свежие посты о животных за последние 24 часа"""
        self.last_attempt = datetime.now()
        all_posts = []
        
        for channel in self.channels:
            try:
                url = f'https://t.me/s/{channel["username"]}'
                logger.info(f"🌐 Парсинг канала: {channel['name']} ({url})")
                
                headers = {
                    'User-Agent': random.choice(self.user_agents),
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
                }
                
                response = self.scraper.get(url, headers=headers, timeout=20)
                
                if response.status_code == 200:
                    channel_posts = self.parse_html_content(
                        response.text, 
                        channel,
                        limit_per_channel
                    )
                    if channel_posts:
                        # Фильтруем только свежие посты
                        recent_posts = [p for p in channel_posts if self.is_recent_post(p.get('timestamp'))]
                        if recent_posts:
                            all_posts.extend(recent_posts)
                            logger.info(f"✅ Найдено {len(recent_posts)} свежих постов в {channel['name']}")
                else:
                    logger.warning(f"⚠️ HTTP ошибка {response.status_code} для {channel['name']}")
                
                # Пауза между запросами к разным каналам
                time.sleep(random.uniform(2, 5))
                
            except Exception as e:
                logger.error(f"❌ Ошибка парсинга {channel['name']}: {str(e)}")
                self.failure_count += 1
                continue
        
        if all_posts:
            # Сортируем посты по дате (новые сначала)
            all_posts.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
            self.posts_cache = all_posts
            self.last_update = datetime.now()
            self.failure_count = 0
            logger.info(f"✅ Всего найдено {len(all_posts)} свежих постов о животных")
        else:
            logger.warning("⚠️ Не найдено ни одного свежего поста о животных")
        
        return all_posts

    # ... (остальные методы класса остаются без изменений)

class AnimalNewsBot:
    """Бот для новостей о животных Ялты"""
    
    def __init__(self):
        self.token = os.environ.get('TOKEN')
        if not self.token:
            logger.error("❌ TOKEN не найден!")
            exit(1)
        
        self.bot = telebot.TeleBot(self.token)
        self.parser = AnimalNewsParser()
        self.app = Flask(__name__)
        self.port = int(os.environ.get('PORT', 8080))
        self.webhook_url = os.environ.get('WEBHOOK_URL')
        
        self.setup_handlers()
        self.setup_routes()
    
    def send_animal_post(self, chat_id: int, post: Dict):
        """Отправка поста о животных"""
        try:
            # Формируем текст с информацией о канале
            post_text = (
                f"🐾 <b>{post['channel_name']}</b>\n\n"
                f"{post['text']}\n\n"
                f"📅 {post['date']}\n"
                f"🔗 <a href='{post['url']}'>Открыть в канале</a>"
            )
            
            # Обрезаем если слишком длинный
            if len(post_text) > 4000:
                lines = post_text.split('\n')
                truncated = []
                length = 0
                for line in lines:
                    if length + len(line) < 3800:
                        truncated.append(line)
                        length += len(line) + 1
                    else:
                        break
                post_text = '\n'.join(truncated) + "...\n\n🔗 Читать далее в канале"
            
            # Отправляем медиа если есть
            if post.get('has_media'):
                media = post['media']
                try:
                    if media['type'] == 'photo':
                        # Проверяем URL фото
                        if not media['url'].startswith('http'):
                            raise ValueError("Неверный URL фото")
                            
                        # Пробуем скачать фото для проверки
                        test_response = requests.head(media['url'], timeout=5)
                        if test_response.status_code != 200:
                            raise ValueError("Фото недоступно")
                            
                        self.bot.send_photo(
                            chat_id,
                            media['url'],
                            caption=post_text,
                            parse_mode="HTML",
                            reply_markup=self.get_post_markup(post['url'])
                        )
                        return
                    
                    elif media['type'] == 'video':
                        # Проверяем URL видео
                        if not media['url'].startswith('http'):
                            raise ValueError("Неверный URL видео")
                            
                        self.bot.send_video(
                            chat_id,
                            media['url'],
                            caption=post_text,
                            parse_mode="HTML",
                            reply_markup=self.get_post_markup(post['url'])
                        )
                        return
                    
                    elif media['type'] == 'document':
                        # Для документов просто отправляем ссылку
                        post_text += f"\n\n📎 Вложение: {media['url']}"
                        
                except Exception as media_error:
                    logger.error(f"⚠️ Ошибка отправки медиа: {media_error}. Пробуем отправить как текст.")
                    # Продолжаем с текстовым вариантом
            
            # Текстовая отправка (если нет медиа или не удалось отправить)
            self.bot.send_message(
                chat_id,
                post_text,
                parse_mode="HTML",
                disable_web_page_preview=False,
                reply_markup=self.get_post_markup(post['url'])
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки поста: {str(e)}")
            self.bot.send_message(
                chat_id,
                f"⚠️ Не удалось отправить пост. Вы можете посмотреть его прямо в канале:\n{post['url']}"
            )

    # ... (остальные методы класса остаются без изменений)

if __name__ == "__main__":
    print("""
🔧 Для работы бота необходимо установить зависимости:
pip install telebot flask requests beautifulsoup4 cloudscraper lxml

🔄 Запуск бота...
""")
    
    try:
        bot = AnimalNewsBot()
        bot.run()
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"💥 Ошибка запуска: {str(e)}")
        print("\n❌ Возможные причины:")
        print("1. Не установлен TOKEN в переменных окружения")
        print("2. Проблемы с сетью или доступом к Telegram API")
        print("\n🔄 Попробуйте перезапустить...")
        time.sleep(5)
