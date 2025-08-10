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

# 🔧 Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class YaltaPodslushanoParser:
    """Улучшенный парсер канала Ялта Подслушано с обработкой спецсимволов"""
    
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
    
    def clean_text(self, text: str) -> str:
        """Очистка текста от лишних символов и форматирования"""
        # Декодируем HTML-сущности
        cleaned = html.unescape(text)
        
        # Удаляем лишние переносы строк (оставляем максимум 2 подряд)
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        
        # Заменяем специальные символы на аналоги или убираем
        symbol_replacements = {
            '➿': '🌀',  # Заменяем на другой символ
            '️': '',     # Удаляем невидимые символы
            ' ': ' ',    # Заменяем специальные пробелы
        }
        
        for old, new in symbol_replacements.items():
            cleaned = cleaned.replace(old, new)
        
        return cleaned.strip()
    
    def get_channel_posts(self, limit: int = 5) -> List[Dict]:
        """Получение постов с канала с обработкой ошибок"""
        self.last_attempt = datetime.now()
        
        try:
            url = f'https://t.me/s/{self.channel["username"]}'
            logger.info(f"🌐 Парсинг канала: {url}")
            
            headers = {
                'User-Agent': random.choice(self.user_agents),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            }
            
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
                    logger.warning("⚠️ Не удалось распарсить посты")
            else:
                logger.warning(f"⚠️ HTTP ошибка: {response.status_code}")
                
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга: {str(e)}")
            self.failure_count += 1
        
        return self.posts_cache if self.posts_cache else []
    
    def parse_html_content(self, html_content: str, limit: int) -> List[Dict]:
        """Улучшенный парсинг HTML с обработкой спецсимволов"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Проверка на блокировку
            if "Cloudflare" in html_content or "checking your browser" in html_content.lower():
                logger.warning("⚠️ Обнаружена защита Cloudflare")
                return []
            
            messages = soup.select('div.tgme_widget_message_wrap')
            if not messages:
                logger.warning("❌ Сообщения не найдены в HTML")
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
            logger.error(f"❌ Ошибка парсинга HTML: {str(e)}")
            return []
    
    def parse_message_div(self, div) -> Optional[Dict]:
        """Парсинг отдельного сообщения с улучшенной обработкой текста"""
        try:
            # ID поста
            post_id = div.get('data-post', '') or f"msg_{hash(str(div)[:100]) % 10000}"
            if '/' in str(post_id):
                post_id = str(post_id).split('/')[-1]
            
            # Текст сообщения с улучшенной обработкой
            text_elem = div.select_one('.tgme_widget_message_text')
            if not text_elem:
                return None
                
            # Получаем текст с сохранением переносов строк
            text = '\n'.join([p.get_text(strip=True) for p in text_elem.find_all(['p', 'br']) if p.get_text(strip=True)])
            if not text:
                text = text_elem.get_text(separator='\n', strip=True)
            
            # Очищаем текст
            text = self.clean_text(text)
            
            # Пропускаем слишком короткие сообщения
            if len(text) < 20:
                return None
            
            # Дата
            date_elem = div.select_one('.tgme_widget_message_date time')
            date_str = date_elem.get('datetime', 'Недавно') if date_elem else "Недавно"
            
            # Медиа
            media = self.extract_media(div)
            
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
            logger.error(f"❌ Ошибка парсинга сообщения: {str(e)}")
            return None
    
    def extract_media(self, div):
        """Извлечение медиа с улучшенной обработкой"""
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
        
        # Документы/гифки
        document_elem = div.select_one('a.tgme_widget_message_document')
        if document_elem:
            doc_url = document_elem.get('href')
            if doc_url:
                return {'type': 'document', 'url': doc_url}
        
        return None
    
    def get_cached_posts(self, limit: int = 5) -> List[Dict]:
        """Получение кэшированных постов с автоматическим обновлением"""
        should_update = (
            not self.last_update or 
            (datetime.now() - self.last_update).seconds > 3600 or  # 1 час
            not self.posts_cache
        )
        
        if should_update:
            return self.get_channel_posts(limit)
        
        return self.posts_cache[:limit]

class YaltaPodslushanoBot:
    """Улучшенный бот для канала Ялта Подслушано"""
    
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
        """Улучшенная отправка поста с обработкой форматирования"""
        try:
            # Формируем текст с ограничением длины
            post_text = (
                f"📢 <b>{self.parser.channel['name']}</b>\n\n"
                f"{post['text']}\n\n"
                f"🔗 <a href='{post['url']}'>Открыть в канале</a>"
            )
            
            # Обрезаем если слишком длинный, сохраняя целые строки
            if len(post_text) > 4000:  # Максимальная длина для Telegram
                lines = post_text.split('\n')
                truncated = []
                length = 0
                for line in lines:
                    if length + len(line) < 3800:  # Оставляем место для остального текста
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
                        self.bot.send_photo(
                            chat_id,
                            media['url'],
                            caption=post_text,
                            parse_mode="HTML",
                            reply_markup=self.get_post_markup(post['url'])
                        )
                        return
                    elif media['type'] == 'video':
                        self.bot.send_video(
                            chat_id,
                            media['url'],
                            caption=post_text,
                            parse_mode="HTML",
                            reply_markup=self.get_post_markup(post['url'])
                        )
                        return
                except Exception as media_error:
                    logger.error(f"⚠️ Ошибка отправки медиа: {media_error}")
                    # Продолжаем с текстовым вариантом
            
            # Текстовая отправка
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
    
    def get_post_markup(self, url: str):
        """Клавиатура для поста"""
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📢 Открыть в канале", url=url))
        return markup
    
    def get_main_keyboard(self):
        """Главное меню"""
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add("📢 Последние посты", "🔄 Обновить")
        markup.add("ℹ️ О канале")
        return markup
    
    def setup_handlers(self):
        """Обработчики команд с улучшенной обработкой ошибок"""
        
        @self.bot.message_handler(commands=['start', 'help'])
        def start_handler(message):
            try:
                welcome_text = (
                    f"👋 <b>Добро пожаловать в бот для канала {self.parser.channel['name']}</b>\n\n"
                    "📌 Доступные команды:\n"
                    "/posts - последние посты из канала\n"
                    "/update - обновить данные\n"
                    "/channel - ссылка на канал\n\n"
                    "💡 Вы также можете использовать кнопки меню ниже"
                )
                
                self.bot.send_message(
                    message.chat.id,
                    welcome_text,
                    parse_mode="HTML",
                    reply_markup=self.get_main_keyboard()
                )
            except Exception as e:
                logger.error(f"❌ Ошибка в start_handler: {str(e)}")
        
        @self.bot.message_handler(commands=['posts'])
        def posts_handler(message):
            try:
                self.bot.send_chat_action(message.chat.id, 'typing')
                posts = self.parser.get_cached_posts(5)
                
                if not posts:
                    self.bot.send_message(
                        message.chat.id,
                        "😕 В данный момент не удалось получить посты. Попробуйте позже.",
                        reply_markup=self.get_main_keyboard()
                    )
                    return
                
                self.bot.send_message(
                    message.chat.id,
                    f"📢 <b>Последние {len(posts)} постов из {self.parser.channel['name']}</b>",
                    parse_mode="HTML"
                )
                
                for post in posts:
                    self.send_post(message.chat.id, post)
                    time.sleep(0.3)  # Небольшая пауза между постами
                
            except Exception as e:
                logger.error(f"❌ Ошибка в posts_handler: {str(e)}")
                self.bot.send_message(
                    message.chat.id,
                    "⚠️ Произошла ошибка при получении постов. Попробуйте позже."
                )
        
        @self.bot.message_handler(commands=['update'])
        def update_handler(message):
            try:
                self.bot.send_chat_action(message.chat.id, 'typing')
                self.bot.send_message(message.chat.id, "🔄 Обновление данных...")
                
                posts = self.parser.get_channel_posts(5)
                
                if posts:
                    self.bot.send_message(
                        message.chat.id,
                        f"✅ Успешно обновлено! Получено {len(posts)} новых постов.\n"
                        f"📅 Последнее обновление: {datetime.now().strftime('%H:%M:%S')}",
                        reply_markup=self.get_main_keyboard()
                    )
                    
                    # Показываем обновленные посты
                    self.posts_handler(message)
                else:
                    self.bot.send_message(
                        message.chat.id,
                        "⚠️ Не удалось получить новые посты. Возможно, проблема с доступом к каналу.",
                        reply_markup=self.get_main_keyboard()
                    )
                    
            except Exception as e:
                logger.error(f"❌ Ошибка в update_handler: {str(e)}")
                self.bot.send_message(
                    message.chat.id,
                    f"⚠️ Ошибка обновления: {str(e)[:200]}",
                    reply_markup=self.get_main_keyboard()
                )
        
        @self.bot.message_handler(commands=['channel'])
        def channel_handler(message):
            try:
                self.bot.send_message(
                    message.chat.id,
                    f"📢 <b>{self.parser.channel['name']}</b>\n\n"
                    f"🔗 {self.parser.channel['url']}",
                    parse_mode="HTML",
                    reply_markup=types.InlineKeyboardMarkup().add(
                        types.InlineKeyboardButton(
                            "📢 Перейти в канал", 
                            url=self.parser.channel['url']
                        )
                    )
                )
            except Exception as e:
                logger.error(f"❌ Ошибка в channel_handler: {str(e)}")
        
        @self.bot.message_handler(func=lambda m: m.text in ["📢 Последние посты", "посты"])
        def posts_button_handler(message):
            posts_handler(message)
        
        @self.bot.message_handler(func=lambda m: m.text in ["🔄 Обновить", "обновить"])
        def update_button_handler(message):
            update_handler(message)
        
        @self.bot.message_handler(func=lambda m: m.text in ["ℹ️ О канале", "о канале"])
        def about_button_handler(message):
            channel_handler(message)
        
        @self.bot.message_handler(func=lambda m: True)
        def default_handler(message):
            try:
                self.bot.send_message(
                    message.chat.id,
                    "ℹ️ Используйте команды или кнопки меню:\n\n"
                    "📢 Последние посты - показать новые посты\n"
                    "🔄 Обновить - обновить данные\n"
                    "ℹ️ О канале - ссылка на канал",
                    reply_markup=self.get_main_keyboard()
                )
            except Exception as e:
                logger.error(f"❌ Ошибка в default_handler: {str(e)}")
    
    def setup_routes(self):
        """Flask маршруты для веб-интерфейса"""
        
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
                logger.error(f"❌ Webhook error: {str(e)}")
                return 'Internal error', 500
        
        @self.app.route('/')
        def home():
            return jsonify({
                "status": "YaltaPodslushano Bot",
                "channel": self.parser.channel['url'],
                "posts_cached": len(self.parser.posts_cache),
                "last_update": self.parser.last_update.isoformat() if self.parser.last_update else None,
                "version": "2.0"
            })
        
        @self.app.route('/posts')
        def posts_api():
            try:
                posts = self.parser.get_cached_posts(5)
                return jsonify({
                    "status": "success",
                    "count": len(posts),
                    "posts": posts[:5]  # Ограничиваем для API
                })
            except Exception as e:
                return jsonify({"status": "error", "message": str(e)}), 500

    def setup_webhook(self) -> bool:
        """Настройка webhook с обработкой ошибок"""
        try:
            self.bot.remove_webhook()
            time.sleep(1)
            
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
            logger.error(f"❌ Ошибка настройки webhook: {str(e)}")
            return False

    def run(self):
        """Запуск бота с обработкой ошибок"""
        logger.info("🚀 Запуск улучшенного бота для Ялта Подслушано...")
        
        # Проверка cloudscraper
        try:
            import cloudscraper
            logger.info("✅ CloudScraper доступен")
        except ImportError:
            logger.warning("⚠️ CloudScraper не установлен. Парсинг может не работать.")
        
        # Предзагрузка постов
        try:
            posts = self.parser.get_cached_posts()
            logger.info(f"✅ Предзагружено {len(posts)} постов")
        except Exception as e:
            logger.error(f"❌ Ошибка предзагрузки: {str(e)}")
        
        # Запуск бота
        try:
            if self.setup_webhook():
                logger.info("🌐 Запуск в webhook режиме")
                self.app.run(host='0.0.0.0', port=self.port)
            else:
                logger.info("🔄 Запуск в polling режиме")
                self.bot.polling(none_stop=True, interval=1, timeout=20)
        except Exception as e:
            logger.error(f"💥 Критическая ошибка запуска: {str(e)}")
            time.sleep(5)
            self.run()  # Попробуем перезапуститься

if __name__ == "__main__":
    print("""
🔧 Для работы бота необходимо установить зависимости:
pip install telebot flask requests beautifulsoup4 cloudscraper lxml

🔄 Запуск бота...
""")
    
    try:
        bot = YaltaPodslushanoBot()
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
