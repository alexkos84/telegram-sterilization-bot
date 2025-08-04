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
    
    def extract_title(self, text: str) -> str:
        """Извлекает заголовок из текста поста"""
        lines = text.split('\n')
        for line in lines[:3]:
            line = line.strip()
            if line and len(line) > 10:
                title = re.sub(r'[^\w\s\-\.,!?а-яёА-ЯЁ]', '', line)
                if len(title) > 50:
                    title = title[:50] + "..."
                return title or "Кошка ищет дом"
        return "Кошка ищет дом"
    
    def extract_description(self, text: str) -> str:
        """Извлекает описание из текста"""
        clean_text = re.sub(r'@\w+|https?://\S+|\+?\d[\d\s\-\(\)]+', '', text)
        if len(clean_text) > 200:
            return clean_text[:200] + "..."
        return clean_text
    
    def extract_contact(self, text: str) -> str:
        """Извлекает контактную информацию"""
        phone_pattern = r'\+?[78][\s\-]?\(?9\d{2}\)?\s?[\d\s\-]{7,10}'
        phones = re.findall(phone_pattern, text)
        
        username_pattern = r'@\w+'
        usernames = re.findall(username_pattern, text)
        
        contacts = []
        if phones:
            contacts.extend(phones[:1])
        if usernames:
            contacts.extend(usernames[:1])
            
        return ' • '.join(contacts) if contacts else "См. в канале"
    
    def is_cat_related(self, text: str) -> bool:
        """Проверяет, относится ли пост к кошкам"""
        cat_keywords = [
            'кот', 'кошк', 'котен', 'котик', 'мурз', 'мяу',
            'кастр', 'стерил', 'привит', 'пристрой', 'дом',
            'котята', 'мама-кошка', 'беременная', 'питомец'
        ]
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in cat_keywords)
    
    def get_mock_posts(self) -> List[Dict]:
        """Возвращает тестовые посты с фото"""
        return [
            {
                'id': '1001',
                'title': '🐱 Котенок Мурзик ищет дом',
                'description': 'Возраст: 2 месяца, мальчик, рыжий окрас. Здоров, привит, очень игривый.',
                'date': '03.08.2025 14:30',
                'url': f'{self.channel_url}/1001',
                'contact': '@volunteer1 • +7 978 123-45-67',
                'photo_url': 'https://via.placeholder.com/600x400?text=Котенок+Мурзик',
                'has_photo': True
            },
            {
                'id': '1002',
                'title': '😺 Кошечка Муся',
                'description': 'Возраст: 1 год, девочка, трехцветная. Стерилизована, привита.',
                'date': '03.08.2025 12:15',
                'url': f'{self.channel_url}/1002',
                'contact': '@volunteer2',
                'photo_url': None,
                'has_photo': False
            }
        ]
    
    def get_cached_posts(self) -> List[Dict]:
        """Возвращает кэшированные или обновленные посты"""
        if (not self.last_update or 
            (datetime.now() - self.last_update).seconds > 1800):
            try:
                return self.get_channel_posts()
            except:
                pass
        return self.posts_cache if self.posts_cache else self.get_mock_posts()

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
            post_text = (
                f"🐱 <b>{post['title']}</b>\n\n"
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
                    logger.error(f"❌ Ошибка отправки фото: {e}")
            
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
            
            self.bot.send_message(
                chat_id,
                f"🐱 <b>КОШКИ ИЩУТ ДОМ</b>\n\n"
                f"📢 Последние объявления из канала:\n"
                f"<a href='{self.parser.channel_url}'>Лапки-ручки Ялта</a>",
                parse_mode="HTML"
            )
            
            for post in posts:
                self.send_post(chat_id, post)
                time.sleep(0.5)
            
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

    def get_main_keyboard(self):
        """Главная клавиатура"""
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add("🏥 Стерилизация", "🏠 Пристройство")
        markup.add("📞 Контакты", "ℹ️ О проекте")
        return markup
    
    def get_adoption_keyboard(self):
        """Клавиатура пристройства"""
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("🐱 Кошки ищут дом")
        markup.add("📝 Подать объявление")
        markup.add("🔙 Назад")
        return markup
    
    def setup_handlers(self):
        """Обработчики сообщений"""
        
        @self.bot.message_handler(commands=['start'])
        def start_handler(message):
            self.stats["users"].add(message.from_user.id)
            self.stats["messages"] += 1
            
            welcome_text = """👋 <b>Добро пожаловать!</b>

🐾 Помощник по уличным кошкам Ялты

Выберите раздел:
🏥 <b>Стерилизация</b> - информация
🏠 <b>Пристройство</b> - кошки ищут дом
📞 <b>Контакты</b> - связь с волонтерами
ℹ️ <b>О проекте</b> - наша деятельность"""
            
            self.bot.send_message(
                message.chat.id, 
                welcome_text, 
                parse_mode="HTML",
                reply_markup=self.get_main_keyboard()
            )
        
        @self.bot.message_handler(commands=['update'])
        def update_handler(message):
            """Обновление постов (для админов)"""
            self.parser.posts_cache = []
            self.parser.last_update = None
            self.bot.send_message(message.chat.id, "🔄 Обновляю посты...")
            posts = self.parser.get_channel_posts()
            self.bot.send_message(
                message.chat.id, 
                f"✅ Обновлено: {len(posts)} постов (с фото: {sum(1 for p in posts if p['photo_url'])})"
            )
        
        @self.bot.message_handler(func=lambda m: True)
        def message_handler(message):
            self.stats["users"].add(message.from_user.id)
            self.stats["messages"] += 1
            
            text = message.text
            chat_id = message.chat.id
            
            try:
                if text == "🏠 Пристройство":
                    info_text = """🏠 <b>Пристройство кошек</b>

Выберите действие:

🐱 <b>Кошки ищут дом</b>
Актуальные объявления из канала

📝 <b>Подать объявление</b>
Как разместить свое объявление"""
                    
                    self.bot.send_message(
                        chat_id, 
                        info_text, 
                        parse_mode="HTML",
                        reply_markup=self.get_adoption_keyboard()
                    )
                
                elif text == "🐱 Кошки ищут дом":
                    self.send_channel_posts(chat_id)
                
                elif text == "📝 Подать объявление":
                    info_text = f"""📝 <b>Подать объявление</b>

📢 <b>Канал для объявлений:</b>
<a href="{self.parser.channel_url}">Лапки-ручки Ялта помощь</a>

✍️ <b>Как подать:</b>
1️⃣ Перейти в канал
2️⃣ Написать администраторам
3️⃣ Или связаться с координаторами:
   • Анна: +7 978 000-00-01
   • Telegram: @adoption_coordinator

📋 <b>Нужная информация:</b>
🔹 Фото животного
🔹 Возраст, пол, окрас
🔹 Характер
🔹 Здоровье (прививки, стерилизация)
🔹 Ваши контакты"""
                    
                    self.bot.send_message(chat_id, info_text, parse_mode="HTML")
                
                elif text == "📞 Контакты":
                    contacts_text = """📞 <b>КОНТАКТЫ</b>

👥 <b>Координаторы:</b>
🔹 Стерилизация: +7 978 144-90-70
🔹 Пристройство: +7 978 000-00-01
🔹 Лечение: +7 978 000-00-02

🏥 <b>Клиники:</b>
🔹 "Айболит": +7 978 000-00-03
🔹 "ВетМир": +7 978 000-00-04

📱 <b>Социальные сети:</b>
🔹 Telegram: @yalta_cats
🔹 Instagram: @yalta_street_cats"""
                    
                    self.bot.send_message(chat_id, contacts_text, parse_mode="HTML")
                
                elif text == "ℹ️ О проекте":
                    about_text = """ℹ️ <b>О ПРОЕКТЕ</b>

🎯 <b>Миссия:</b>
Помощь бездомным кошкам Ялты

📊 <b>Достижения:</b>
🔹 Стерилизовано: 500+ кошек
🔹 Пристроено: 200+ котят
🔹 Волонтеров: 50+ активных

💰 <b>Поддержать:</b>
Карта: 2202 2020 0000 0000

🤝 <b>Стать волонтером:</b>
Пишите @volunteer_coordinator"""
                    
                    self.bot.send_message(chat_id, about_text, parse_mode="HTML")
                
                elif text == "🔙 Назад":
                    self.bot.send_message(
                        chat_id, 
                        "🏠 Главное меню:", 
                        reply_markup=self.get_main_keyboard()
                    )
                
                else:
                    self.bot.send_message(
                        chat_id,
                        "❓ Используйте кнопки меню\n\n/start - главное меню",
                        reply_markup=self.get_main_keyboard()
                    )
                    
            except Exception as e:
                logger.error(f"❌ Ошибка обработки: {e}")
                self.bot.send_message(chat_id, "⚠️ Ошибка. Попробуйте /start")
    
    def setup_routes(self):
        """Flask маршруты"""
        
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
                logger.error(f"❌ Webhook ошибка: {e}")
                return 'Internal error', 500
        
        @self.app.route('/')
        def home():
            return jsonify({
                "status": "🤖 Cat Bot Running",
                "time": datetime.now().strftime('%H:%M:%S'),
                "users": len(self.stats["users"]),
                "messages": self.stats["messages"],
                "channel": self.parser.channel_url
            })
        
        @self.app.route('/posts')
        def posts_api():
            try:
                posts = self.parser.get_cached_posts()
                return jsonify({
                    "status": "ok",
                    "count": len(posts),
                    "posts": posts,
                    "channel": self.parser.channel_url
                })
            except Exception as e:
                return jsonify({"status": "error", "message": str(e)}), 500
    
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
                logger.info(f"✅ Webhook: {full_url}")
                return True
            else:
                logger.error("❌ Не удалось установить webhook")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка webhook: {e}")
            return False
    
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
