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
    """Парсер новостей о животных из нескольких каналов"""
    
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
            }
        ]
        
        self.animal_keywords = [
            # Животные
            'кошк', 'кот', 'котён', 'котен', 'котэ', 'котейк', 'кис', 'кис-кис',
            'соба', 'пёс', 'пес', 'щен', 'собак', 'псин', 'хвост', 'лап',
            'животн', 'питом', 'звер', 'зверюшк', 'зверёк', 'питомец',
            
            # Действия
            'пристр', 'потерял', 'нашел', 'найдён', 'найден', 'пропал', 'пропада',
            'приют', 'передерж', 'ветеринар', 'корм', 'стерилиз', 'кастрац',
            'лечен', 'болезн', 'помощ', 'помоги', 'ищет', 'ищем', 'найти',
            
            # Характеристики
            'лап', 'хвост', 'ус', 'шерст', 'породист', 'дворняж', 'дворняг',
            'пушист', 'рыж', 'черн', 'бел', 'сер', 'полоса', 'пятнист',
            
            # Звуки
            'мяу', 'гав', 'мур', 'тяф', 'рыч'
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
    
    def is_animal_post(self, text: str) -> bool:
        """Проверяет, относится ли пост к животным"""
        if not text or len(text) < 10:
            return False
            
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in self.animal_keywords)
    
    def clean_text(self, text: str) -> str:
        """Очистка текста от лишних символов"""
        if not text:
            return ""
            
        cleaned = html.unescape(text)
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        symbol_replacements = {
            '➿': '🌀',
            '️': '',
            ' ': ' ',
            '​': '',
            '­': ''
        }
        for old, new in symbol_replacements.items():
            cleaned = cleaned.replace(old, new)
        return cleaned.strip()
    
    def get_animal_posts(self, limit_per_channel: int = 3) -> List[Dict]:
        """Получает посты о животных со всех каналов"""
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
                        all_posts.extend(channel_posts)
                        logger.info(f"✅ Найдено {len(channel_posts)} постов в {channel['name']}")
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
            logger.info(f"✅ Всего найдено {len(all_posts)} постов о животных")
        else:
            logger.warning("⚠️ Не найдено ни одного поста о животных")
        
        return all_posts
    
    def parse_html_content(self, html_content: str, channel: Dict, limit: int) -> List[Dict]:
        """Парсинг HTML контента и фильтрация постов о животных"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            if "Cloudflare" in html_content or "checking your browser" in html_content.lower():
                logger.warning(f"⚠️ Обнаружена защита Cloudflare в {channel['name']}")
                return []
            
            messages = soup.select('div.tgme_widget_message_wrap')
            if not messages:
                logger.warning(f"❌ Сообщения не найдены в {channel['name']}")
                return []
            
            animal_posts = []
            for msg_div in messages:
                post = self.parse_message_div(msg_div, channel)
                if post and self.is_animal_post(post['text']):
                    animal_posts.append(post)
                    if len(animal_posts) >= limit:
                        break
            
            return animal_posts
            
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга HTML в {channel['name']}: {str(e)}")
            return []
    
    def parse_message_div(self, div, channel: Dict) -> Optional[Dict]:
        """Парсинг отдельного сообщения"""
        try:
            # ID поста
            post_id = div.get('data-post', '') or f"msg_{hash(str(div)[:100]) % 10000}"
            if '/' in str(post_id):
                post_id = str(post_id).split('/')[-1]
            
            # Текст сообщения
            text_elem = div.select_one('.tgme_widget_message_text')
            if not text_elem:
                return None
                
            text = '\n'.join([p.get_text(strip=True) for p in text_elem.find_all(['p', 'br']) if p.get_text(strip=True)])
            if not text:
                text = text_elem.get_text(separator='\n', strip=True)
            
            text = self.clean_text(text)
            if len(text) < 10:
                return None
            
            # Дата и время
            date_elem = div.select_one('.tgme_widget_message_date time')
            date_str = "Недавно"
            timestamp = 0
            
            if date_elem:
                datetime_attr = date_elem.get('datetime')
                if datetime_attr:
                    try:
                        dt = datetime.fromisoformat(datetime_attr.replace('Z', '+00:00'))
                        date_str = dt.strftime('%d.%m.%Y %H:%M')
                        timestamp = dt.timestamp()
                    except:
                        date_str = date_elem.get_text(strip=True)
            
            # Медиа
            media = self.extract_media(div)
            
            return {
                'id': post_id,
                'text': text,
                'date': date_str,
                'timestamp': timestamp,
                'url': f"{channel['url']}/{post_id}",
                'channel_name': channel['name'],
                'channel_url': channel['url'],
                'media': media,
                'has_media': bool(media),
                'source': 'parsed'
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга сообщения в {channel['name']}: {str(e)}")
            return None
    
    def extract_media(self, div):
        """Извлечение медиа (фото, видео)"""
        # 1. Фото через тег img
        img_elem = div.select_one('.tgme_widget_message_photo img[src]')
        if img_elem:
            return {'type': 'photo', 'url': img_elem.get('src')}
        
        # 2. Фото через background-image
        photo_wrap = div.select_one('.tgme_widget_message_photo_wrap[style*="background-image"]')
        if photo_wrap:
            style = photo_wrap.get('style', '')
            match = re.search(r"background-image:url\('([^']+)'\)", style)
            if match:
                return {'type': 'photo', 'url': match.group(1)}
        
        # 3. Видео
        video_elem = div.select_one('video.tgme_widget_message_video')
        if video_elem:
            video_src = video_elem.get('src')
            if video_src:
                return {'type': 'video', 'url': video_src}
        
        # 4. Документы (гифки и др.)
        doc_elem = div.select_one('a.tgme_widget_message_document')
        if doc_elem:
            doc_url = doc_elem.get('href')
            if doc_url:
                return {'type': 'document', 'url': doc_url}
        
        return None
    
    def get_cached_animal_posts(self, limit: int = 10) -> List[Dict]:
        """Получение кэшированных постов о животных"""
        should_update = (
            not self.last_update or 
            (datetime.now() - self.last_update).seconds > 3600 or
            not self.posts_cache
        )
        
        if should_update:
            return self.get_animal_posts(limit // len(self.channels))
        
        return self.posts_cache[:limit]

class AnimalNewsBot:
    """Бот для новостей о животных"""
    
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
                    elif media['type'] == 'document':
                        post_text += f"\n\n📎 Вложение: {media['url']}"
                except Exception as media_error:
                    logger.error(f"⚠️ Ошибка отправки медиа: {media_error}")
            
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
        markup.add("🐾 Последние новости", "🔄 Обновить")
        markup.add("📢 Все каналы", "ℹ️ О боте")
        return markup
    
    def setup_handlers(self):
        """Обработчики команд"""
        
        @self.bot.message_handler(commands=['start', 'help'])
        def start_handler(message):
            welcome_text = (
                "🐕🐈 <b>Бот новостей о животных Ялты</b> 🐦🐇\n\n"
                "Я собираю новости о животных из нескольких каналов:\n"
                "- Ялта Подслушано\n"
                "- ВетЯлта\n"
                "- Ялтая\n\n"
                "📌 <b>Доступные команды:</b>\n"
                "/news - последние новости о животных\n"
                "/update - обновить данные\n"
                "/channels - список всех каналов\n\n"
                "💡 Вы также можете использовать кнопки меню ниже"
            )
            
            self.bot.send_message(
                message.chat.id,
                welcome_text,
                parse_mode="HTML",
                reply_markup=self.get_main_keyboard()
            )
        
        @self.bot.message_handler(commands=['news', 'posts'])
        def news_handler(message):
            self.bot.send_chat_action(message.chat.id, 'typing')
            posts = self.parser.get_cached_animal_posts(10)
            
            if not posts:
                self.bot.send_message(
                    message.chat.id,
                    "😕 В данный момент нет новостей о животных. Попробуйте позже.",
                    reply_markup=self.get_main_keyboard()
                )
                return
            
            self.bot.send_message(
                message.chat.id,
                f"🐾 <b>Последние {len(posts)} новостей о животных</b>",
                parse_mode="HTML"
            )
            
            for post in posts:
                self.send_animal_post(message.chat.id, post)
                time.sleep(0.3)
        
        @self.bot.message_handler(commands=['update'])
        def update_handler(message):
            self.bot.send_chat_action(message.chat.id, 'typing')
            self.bot.send_message(message.chat.id, "🔄 Обновление данных...")
            
            posts = self.parser.get_animal_posts(3)  # 3 поста с каждого канала
            
            if posts:
                self.bot.send_message(
                    message.chat.id,
                    f"✅ Успешно обновлено! Найдено {len(posts)} новых постов.\n"
                    f"📅 Последнее обновление: {datetime.now().strftime('%H:%M:%S')}",
                    reply_markup=self.get_main_keyboard()
                )
                self.news_handler(message)
            else:
                self.bot.send_message(
                    message.chat.id,
                    "⚠️ Не удалось найти новые посты о животных. Попробуйте позже.",
                    reply_markup=self.get_main_keyboard()
                )
        
        @self.bot.message_handler(commands=['channels'])
        def channels_handler(message):
            channels_text = "📢 <b>Каналы, которые я отслеживаю:</b>\n\n"
            for channel in self.parser.channels:
                channels_text += f"🔹 <a href='{channel['url']}'>{channel['name']}</a>\n"
            
            channels_text += "\nℹ️ Я ищу только посты о животных в этих каналах."
            
            self.bot.send_message(
                message.chat.id,
                channels_text,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        
        @self.bot.message_handler(func=lambda m: m.text in ["🐾 Последние новости", "новости"])
        def news_button_handler(message):
            news_handler(message)
        
        @self.bot.message_handler(func=lambda m: m.text in ["🔄 Обновить", "обновить"])
        def update_button_handler(message):
            update_handler(message)
        
        @self.bot.message_handler(func=lambda m: m.text in ["📢 Все каналы", "каналы"])
        def channels_button_handler(message):
            channels_handler(message)
        
        @self.bot.message_handler(func=lambda m: m.text in ["ℹ️ О боте", "о боте"])
        def about_button_handler(message):
            self.bot.send_message(
                message.chat.id,
                "ℹ️ <b>О боте</b>\n\n"
                "Этот бот собирает новости о животных из нескольких каналов Ялты.\n\n"
                "📌 <b>Что я умею:</b>\n"
                "- Находить посты о кошках, собаках и других животных\n"
                "- Показывать актуальные объявления о пропажах/находках\n"
                "- Отображать информацию о помощи животным\n\n"
                "🔄 <b>Частота обновления:</b> 1 раз в час\n"
                "🔍 <b>Фильтрация:</b> только посты о животных\n\n"
                "По вопросам и предложениям: @ваш_аккаунт",
                parse_mode="HTML",
                reply_markup=self.get_main_keyboard()
            )
        
        @self.bot.message_handler(func=lambda m: True)
        def default_handler(message):
            self.bot.send_message(
                message.chat.id,
                "ℹ️ Используйте команды или кнопки меню:\n\n"
                "🐾 Последние новости - показать новые посты о животных\n"
                "🔄 Обновить - обновить данные\n"
                "📢 Все каналы - список отслеживаемых каналов\n"
                "ℹ️ О боте - информация о боте",
                reply_markup=self.get_main_keyboard()
            )
    
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
                "status": "Animal News Bot",
                "channels": [c['name'] for c in self.parser.channels],
                "animal_posts_cached": len(self.parser.posts_cache),
                "last_update": self.parser.last_update.isoformat() if self.parser.last_update else None,
                "version": "1.1"
            })

    def setup_webhook(self) -> bool:
        """Настройка webhook"""
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
        """Запуск бота"""
        logger.info("🚀 Запуск бота новостей о животных...")
        
        try:
            import cloudscraper
            logger.info("✅ CloudScraper доступен")
        except ImportError:
            logger.warning("⚠️ CloudScraper не установлен. Парсинг может не работать.")
        
        try:
            posts = self.parser.get_cached_animal_posts()
            logger.info(f"✅ Предзагружено {len(posts)} постов о животных")
        except Exception as e:
            logger.error(f"❌ Ошибка предзагрузки: {str(e)}")
        
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
            self.run()

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
