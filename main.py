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

# 🔧 Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class YaltaPodslushanoParser:
    """Парсер канала Ялта Подслушано"""
    
    def __init__(self):
        self.channel = {
            'username': 'yalta_podslushano',
            'url': 'https://t.me/yalta_podslushano',
            'name': 'Ялта Подслушано'
        }
        self.posts_cache = []
        self.last_update = None
        self.last_attempt = None
        self.failure_count = 0
        
        # Создаем CloudScraper сессию для обхода Cloudflare
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
        
        # Ротация User-Agents
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
        ]
    
    def get_channel_posts(self, limit: int = 5) -> List[Dict]:
        """Получение постов с канала"""
        self.last_attempt = datetime.now()
        
        try:
            url = f'https://t.me/s/{self.channel["username"]}'
            logger.info(f"🌐 Парсинг канала: {url}")
            
            # Настраиваем headers
            headers = {
                'User-Agent': random.choice(self.user_agents),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
                'DNT': '1'
            }
            
            # Делаем запрос
            response = self.scraper.get(url, headers=headers, timeout=20)
            
            if response.status_code == 200:
                posts = self.parse_html_content(response.text, limit)
                if posts:
                    self.posts_cache = posts
                    self.last_update = datetime.now()
                    self.failure_count = 0
                    logger.info(f"✅ Успешно получено {len(posts)} постов")
                    return posts
            else:
                logger.warning(f"⚠️ HTTP ошибка: {response.status_code}")
                
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга: {e}")
            self.failure_count += 1
        
        # Если не получилось, возвращаем кэш или пустой список
        return self.posts_cache if self.posts_cache else []
    
    def parse_html_content(self, html: str, limit: int) -> List[Dict]:
        """Парсинг HTML контента"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Проверяем на блокировку
            if "Cloudflare" in html or "checking your browser" in html.lower():
                logger.warning("⚠️ Обнаружена защита Cloudflare")
                return []
            
            # Ищем сообщения
            messages = soup.select('div.tgme_widget_message_wrap')
            if not messages:
                logger.warning("❌ Сообщения не найдены")
                return []
            
            posts = []
            for msg_div in messages[:limit*2]:  # Берем с запасом для фильтрации
                post = self.parse_message_div(msg_div)
                if post:
                    posts.append(post)
                    if len(posts) >= limit:
                        break
            
            return posts
            
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга HTML: {e}")
            return []
    
    def parse_message_div(self, div) -> Optional[Dict]:
        """Парсинг отдельного сообщения"""
        try:
            # ID поста
            post_id = div.get('data-post', '') or f"msg_{hash(str(div)[:100]) % 10000}"
            if '/' in str(post_id):
                post_id = str(post_id).split('/')[-1]
            
            # Текст сообщения
            text_elem = div.select_one('.tgme_widget_message_text')
            text = text_elem.get_text(separator='\n', strip=True) if text_elem else ""
            
            # Пропускаем короткие или пустые сообщения
            if not text or len(text) < 30:
                return None
            
            # Дата
            date_elem = div.select_one('.tgme_widget_message_date time')
            date_str = date_elem.get('datetime', 'Недавно') if date_elem else "Недавно"
            
            # Фото/видео
            media = self.extract_media(div)
            
            # Формируем пост
            return {
                'id': post_id,
                'text': text,
                'date': date_str,
                'url': f"{self.channel['url']}/{post_id}",
                'media': media,
                'has_media': bool(media),
                'source': 'parsed'
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга сообщения: {e}")
            return None
    
    def extract_media(self, div):
        """Извлечение медиа (фото/видео)"""
        # Фото
        photo_elem = div.select_one('.tgme_widget_message_photo_wrap[style*="background-image"]')
        if photo_elem:
            style = photo_elem.get('style', '')
            match = re.search(r"background-image:url\('([^']+)'\)", style)
            if match:
                return {'type': 'photo', 'url': match.group(1)}
        
        # Видео
        video_elem = div.select_one('video.tgme_widget_message_video')
        if video_elem:
            video_src = video_elem.get('src')
            if video_src:
                return {'type': 'video', 'url': video_src}
        
        return None
    
    def get_cached_posts(self, limit: int = 5) -> List[Dict]:
        """Получение кэшированных постов"""
        # Обновляем если давно не обновляли или кэш пустой
        should_update = (
            not self.last_update or 
            (datetime.now() - self.last_update).seconds > 3600 or  # 1 час
            not self.posts_cache
        )
        
        if should_update:
            return self.get_channel_posts(limit)
        
        return self.posts_cache[:limit]

class YaltaPodslushanoBot:
    """Бот для канала Ялта Подслушано"""
    
    def __init__(self):
        self.token = os.environ.get('TOKEN')
        if not self.token:
            logger.error("❌ TOKEN не найден!")
            exit(1)
        
        self.bot = telebot.TeleBot(self.token)
        self.parser = YaltaPodslushanoParser()
        self.app = Flask(__name__)
        self.port = int(os.environ.get('PORT', 8080))
        self.webhook_url = os.environ.get('WEBHOOK_URL')
        
        self.setup_handlers()
        self.setup_routes()
    
    def send_post(self, chat_id: int, post: Dict):
        """Отправка одного поста"""
        try:
            # Формируем текст
            post_text = (
                f"📢 <b>{self.parser.channel['name']}</b>\n\n"
                f"{post['text']}\n\n"
                f"🔗 <a href='{post['url']}'>Открыть в канале</a>"
            )
            
            # Обрезаем если слишком длинный
            if len(post_text) > 1024:
                post_text = post_text[:1000] + "..."
            
            # Отправляем медиа если есть
            if post.get('has_media'):
                media = post['media']
                if media['type'] == 'photo':
                    self.bot.send_photo(
                        chat_id,
                        media['url'],
                        caption=post_text,
                        parse_mode="HTML",
                        reply_markup=types.InlineKeyboardMarkup().add(
                            types.InlineKeyboardButton("📢 Открыть в канале", url=post['url'])
                        )
                    )
                    return
                elif media['type'] == 'video':
                    self.bot.send_video(
                        chat_id,
                        media['url'],
                        caption=post_text,
                        parse_mode="HTML",
                        reply_markup=types.InlineKeyboardMarkup().add(
                            types.InlineKeyboardButton("📢 Открыть в канале", url=post['url'])
                        )
                    )
                    return
            
            # Отправляем как текст если нет медиа или не удалось отправить
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

    def setup_handlers(self):
        """Обработчики команд"""
        
        @self.bot.message_handler(commands=['start'])
        def start_handler(message):
            welcome_text = (
                f"👋 <b>Добро пожаловать!</b>\n\n"
                f"Это бот для канала <b>{self.parser.channel['name']}</b>\n\n"
                f"📌 Доступные команды:\n"
                f"/posts - последние посты\n"
                f"/update - обновить данные\n"
                f"/channel - ссылка на канал"
            )
            
            self.bot.send_message(
                message.chat.id,
                welcome_text,
                parse_mode="HTML",
                reply_markup=self.get_main_keyboard()
            )
        
        @self.bot.message_handler(commands=['posts'])
        def posts_handler(message):
            self.bot.send_message(message.chat.id, "🔄 Получаю последние посты...")
            posts = self.parser.get_cached_posts(5)
            
            if not posts:
                self.bot.send_message(
                    message.chat.id,
                    "😕 Не удалось получить посты. Попробуйте позже.",
                    reply_markup=self.get_main_keyboard()
                )
                return
            
            for post in posts:
                self.send_post(message.chat.id, post)
                time.sleep(0.5)  # Пауза между постами
            
            self.bot.send_message(
                message.chat.id,
                f"✅ Показано {len(posts)} последних постов\n\n"
                f"🔄 Для обновления: /update\n"
                f"📢 Канал: {self.parser.channel['url']}",
                reply_markup=self.get_main_keyboard()
            )
        
        @self.bot.message_handler(commands=['update'])
        def update_handler(message):
            """Принудительное обновление"""
            self.bot.send_message(message.chat.id, "🔄 Принудительное обновление...")
            
            try:
                posts = self.parser.get_channel_posts(5)
                if posts:
                    self.bot.send_message(
                        message.chat.id,
                        f"✅ Успешно обновлено! Получено {len(posts)} постов.\n"
                        f"📅 Последнее обновление: {datetime.now().strftime('%H:%M:%S')}",
                        reply_markup=self.get_main_keyboard()
                    )
                else:
                    self.bot.send_message(
                        message.chat.id,
                        "⚠️ Не удалось получить новые посты. Попробуйте позже.",
                        reply_markup=self.get_main_keyboard()
                    )
            except Exception as e:
                self.bot.send_message(
                    message.chat.id,
                    f"❌ Ошибка обновления: {str(e)[:200]}",
                    reply_markup=self.get_main_keyboard()
                )
        
        @self.bot.message_handler(commands=['channel'])
        def channel_handler(message):
            """Ссылка на канал"""
            self.bot.send_message(
                message.chat.id,
                f"📢 <b>{self.parser.channel['name']}</b>\n\n"
                f"🔗 {self.parser.channel['url']}",
                parse_mode="HTML",
                reply_markup=types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton("📢 Перейти в канал", url=self.parser.channel['url'])
                )
            )
        
        @self.bot.message_handler(func=lambda m: True)
        def default_handler(message):
            """Обработка остальных сообщений"""
            self.bot.send_message(
                message.chat.id,
                "ℹ️ Используйте команды:\n\n"
                "/posts - последние посты\n"
                "/update - обновить данные\n"
                "/channel - ссылка на канал",
                reply_markup=self.get_main_keyboard()
            )
    
    def get_main_keyboard(self):
        """Главная клавиатура"""
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("/posts", "/update")
        markup.add("/channel")
        return markup
    
    def setup_routes(self):
        """Flask маршруты"""
        
        @self.app.route(f'/{self.token}', methods=['POST'])
        def webhook():
            if request.headers.get('content-type') == 'application/json':
                json_string = request.get_data().decode('utf-8')
                update = telebot.types.Update.de_json(json_string)
                self.bot.process_new_updates([update])
                return '', 200
            return 'Bad request', 400
        
        @self.app.route('/')
        def home():
            return jsonify({
                "status": "YaltaPodslushano Bot",
                "channel": self.parser.channel['url'],
                "posts_cached": len(self.parser.posts_cache),
                "last_update": self.parser.last_update.isoformat() if self.parser.last_update else None
            })

    def setup_webhook(self) -> bool:
        """Настройка webhook"""
        try:
            self.bot.remove_webhook()
            time.sleep(2)
            
            if not self.webhook_url:
                logger.error("❌ WEBHOOK_URL не задан!")
                return False
            
            full_url = f"https://{self.webhook_url}/{self.token}"
            result = self.bot.set_webhook(url=full_url)
            
            if result:
                logger.info(f"✅ Webhook установлен: {full_url}")
                return True
            else:
                logger.error("❌ Не удалось установить webhook")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка настройки webhook: {e}")
            return False

    def run(self):
        """Запуск бота"""
        logger.info("🚀 Запуск бота для Ялта Подслушано...")
        
        # Предзагрузка постов
        try:
            posts = self.parser.get_cached_posts()
            logger.info(f"✅ Предзагружено {len(posts)} постов")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка предзагрузки: {e}")
        
        # Запуск бота
        if self.setup_webhook():
            logger.info("🌐 Запуск в webhook режиме")
            self.app.run(host='0.0.0.0', port=self.port)
        else:
            logger.info("🔄 Запуск в polling режиме")
            self.bot.polling(none_stop=True)

if __name__ == "__main__":
    # Проверка зависимостей
    requirements = """
Для работы бота необходимо установить:
pip install telebot flask requests beautifulsoup4 cloudscraper
"""
    print(requirements)
    
    # Запуск бота
    try:
        bot = YaltaPodslushanoBot()
        bot.run()
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"💥 Критическая ошибка: {e}")
        print("\n❌ Возможные причины:")
        print("1. Не установлен TOKEN в переменных окружения")
        print("2. Проблемы с сетью или доступом к Telegram API")
        print("\n🔄 Попробуйте перезапустить...")
        time.sleep(5)
