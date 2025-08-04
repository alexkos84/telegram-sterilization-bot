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
    """Простой парсер канала через веб-интерфейс (без API)"""
    
    def __init__(self):
        self.channel_username = 'Lapki_ruchki_Yalta_help'
        self.channel_url = 'https://t.me/Lapki_ruchki_Yalta_help'
        self.web_url = f'https://t.me/s/{self.channel_username}'  # Публичный веб-интерфейс
        
        self.posts_cache = []
        self.last_update = None
        
        # Заголовки для запросов
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
    
    def get_channel_posts(self, limit: int = 3) -> List[Dict]:
        """Получает последние посты из канала через веб-скрейпинг"""
        try:
            logger.info(f"🌐 Загрузка постов с {self.web_url}")
            
            # Делаем запрос к веб-версии канала
            response = requests.get(self.web_url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            # Парсим HTML
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Ищем посты (div с классом tgme_widget_message)
            message_divs = soup.find_all('div', class_='tgme_widget_message')
            
            posts = []
            for div in message_divs[:limit*2]:  # Берем больше для фильтрации
                post_data = self.parse_message_div(div)
                if post_data and self.is_cat_related(post_data.get('text', '')):
                    posts.append(post_data)
                    
                if len(posts) >= limit:
                    break
            
            if posts:
                self.posts_cache = posts
                self.last_update = datetime.now()
                logger.info(f"✅ Получено {len(posts)} постов из канала")
            else:
                logger.warning("⚠️ Не найдено подходящих постов")
                
            return posts or self.get_mock_posts()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Ошибка запроса к каналу: {e}")
            return self.get_mock_posts()
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга канала: {e}")
            return self.get_mock_posts()
    
    def parse_message_div(self, div) -> Optional[Dict]:
        """Парсит отдельный пост из HTML div"""
        try:
            # Извлекаем ID поста
            post_id = None
            data_post_attr = div.get('data-post')
            if data_post_attr:
                post_id = data_post_attr.split('/')[-1]
            
            # Извлекаем текст поста
            text_div = div.find('div', class_='tgme_widget_message_text')
            text = text_div.get_text(strip=True) if text_div else ""
            
            # Извлекаем дату
            date_elem = div.find('time')
            date_str = "Недавно"
            if date_elem:
                datetime_attr = date_elem.get('datetime')
                if datetime_attr:
                    try:
                        dt = datetime.fromisoformat(datetime_attr.replace('Z', '+00:00'))
                        date_str = dt.strftime('%d.%m.%Y %H:%M')
                    except:
                        pass
            
            # Проверяем наличие фото
            has_photo = bool(div.find('a', class_='tgme_widget_message_photo_wrap'))
            
            if not text:  # Пропускаем посты без текста
                return None
            
            post_data = {
                'id': post_id or 'unknown',
                'text': text,
                'date': date_str,
                'url': f"{self.channel_url}/{post_id}" if post_id else self.channel_url,
                'title': self.extract_title(text),
                'description': self.extract_description(text),
                'contact': self.extract_contact(text),
                'has_photo': has_photo
            }
            
            return post_data
            
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга div поста: {e}")
            return None
    
    def extract_title(self, text: str) -> str:
        """Извлекает заголовок из текста поста"""
        lines = text.split('\n')
        for line in lines[:3]:
            line = line.strip()
            if line and len(line) > 10:
                # Убираем лишние символы для заголовка
                title = re.sub(r'[^\w\s\-\.,!?а-яёА-ЯЁ]', '', line)
                if len(title) > 50:
                    title = title[:50] + "..."
                return title or "Кошка ищет дом"
        return "Кошка ищет дом"
    
    def extract_description(self, text: str) -> str:
        """Извлекает описание из текста"""
        # Убираем контактную информацию для описания
        clean_text = re.sub(r'@\w+|https?://\S+|\+?\d[\d\s\-\(\)]+', '', text)
        
        if len(clean_text) > 200:
            return clean_text[:200] + "..."
        return clean_text
    
    def extract_contact(self, text: str) -> str:
        """Извлекает контактную информацию"""
        # Ищем телефоны
        phone_pattern = r'\+?[78][\s\-]?\(?9\d{2}\)?\s?[\d\s\-]{7,10}'
        phones = re.findall(phone_pattern, text)
        
        # Ищем юзернеймы
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
        """Возвращает тестовые посты"""
        return [
            {
                'id': '1001',
                'title': '🐱 Котенок Мурзик ищет дом',
                'description': 'Возраст: 2 месяца, мальчик, рыжий окрас. Здоров, привит, очень игривый.',
                'date': '03.08.2025 14:30',
                'url': f'{self.channel_url}/1001',
                'contact': '@volunteer1 • +7 978 123-45-67',
                'has_photo': True
            },
            {
                'id': '1002',
                'title': '😺 Кошечка Муся',
                'description': 'Возраст: 1 год, девочка, трехцветная. Стерилизована, привита.',
                'date': '03.08.2025 12:15',
                'url': f'{self.channel_url}/1002',
                'contact': '@volunteer2',
                'has_photo': True
            },
            {
                'id': '1003',
                'title': '🐈 Взрослый кот Барсик',
                'description': 'Возраст: 3 года, мальчик, серый. Кастрирован, спокойный.',
                'date': '02.08.2025 18:45',
                'url': f'{self.channel_url}/1003',
                'contact': '+7 978 987-65-43',
                'has_photo': False
            }
        ]
    
    def get_cached_posts(self) -> List[Dict]:
        """Возвращает кэшированные или обновленные посты"""
        # Если кэш старше 30 минут, обновляем
        if (not self.last_update or 
            (datetime.now() - self.last_update).seconds > 1800):
            try:
                return self.get_channel_posts()
            except:
                pass
        
        return self.posts_cache if self.posts_cache else self.get_mock_posts()

class CatBotSimple:
    """Упрощенная версия бота с веб-скрейпингом"""
    
    def __init__(self):
        self.token = os.environ.get('TOKEN')
        if not self.token:
            logger.error("❌ Переменная TOKEN не найдена!")
            exit(1)
        
        self.bot = telebot.TeleBot(self.token)
        self.channel_parser = SimpleChannelParser()
        self.app = Flask(__name__)
        
        # Конфигурация
        self.port = int(os.environ.get('PORT', 8080))
        self.webhook_url = (
            os.environ.get('RAILWAY_STATIC_URL') or 
            os.environ.get('RAILWAY_PUBLIC_DOMAIN') or
            os.environ.get('WEBHOOK_URL')
        )
        
        # Простая статистика
        self.stats = {"users": set(), "messages": 0}
        
        self.setup_handlers()
        self.setup_routes()
    
    def send_message(self, chat_id: int, text: str, markup=None) -> bool:
        """Отправляет сообщение"""
        try:
            self.bot.send_message(
                chat_id,
                text,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=markup
            )
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка отправки: {e}")
            return False
    
    def send_channel_posts(self, chat_id: int):
        """Отправляет посты из канала"""
        try:
            posts = self.channel_parser.get_cached_posts()
            
            if not posts:
                self.send_message(
                    chat_id,
                    f"😿 Сейчас нет актуальных объявлений.\n\n"
                    f"📢 Проверьте канал: {self.channel_parser.channel_url}"
                )
                return
            
            # Заголовок
            header = f"""🐱 <b>КОШКИ ИЩУТ ДОМ</b>

📢 Объявления из канала:
<a href="{self.channel_parser.channel_url}">Лапки-ручки Ялта помощь</a>

⬇️ Последние {len(posts)} объявления:"""
            
            self.send_message(chat_id, header)
            
            # Отправляем посты
            for i, post in enumerate(posts, 1):
                post_text = f"""{'🔸' if i == 1 else '🔹'} <b>{post['title']}</b>

📝 {post['description']}

📅 {post['date']}
📞 {post['contact']}
{'📷 Есть фото' if post.get('has_photo') else ''}

🔗 <a href="{post['url']}">Смотреть в канале</a>
{'━━━━━━━━━━━━━━━━' if i < len(posts) else ''}"""
                
                self.send_message(chat_id, post_text)
                time.sleep(0.3)
            
            # Футер
            footer = f"""💡 <b>Как помочь:</b>

🏠 <b>Взять кошку:</b>
Свяжитесь с контактом из объявления

📢 <b>Канал:</b> <a href="{self.channel_parser.channel_url}">Лапки-ручки Ялта помощь</a>

🤝 <b>Стать волонтером:</b>
Напишите в канал"""
            
            self.send_message(chat_id, footer)
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки постов: {e}")
            self.send_message(
                chat_id,
                f"⚠️ Ошибка загрузки.\n\n"
                f"📢 Канал: {self.channel_parser.channel_url}"
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
            
            self.send_message(message.chat.id, welcome_text, self.get_main_keyboard())
        
        @self.bot.message_handler(commands=['update'])
        def update_handler(message):
            """Обновление постов (для админов)"""
            self.channel_parser.posts_cache = []
            self.channel_parser.last_update = None
            self.send_message(message.chat.id, "🔄 Обновляю посты...")
            posts = self.channel_parser.get_channel_posts()
            self.send_message(message.chat.id, f"✅ Обновлено: {len(posts)} постов")
        
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
                    
                    self.send_message(chat_id, info_text, self.get_adoption_keyboard())
                
                elif text == "🐱 Кошки ищут дом":
                    self.send_channel_posts(chat_id)
                
                elif text == "📝 Подать объявление":
                    info_text = f"""📝 <b>Подать объявление</b>

📢 <b>Канал для объявлений:</b>
<a href="{self.channel_parser.channel_url}">Лапки-ручки Ялта помощь</a>

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
🔹 Ваши контакты

💡 <b>Советы:</b>
✅ Честное описание
✅ Качественные фото
✅ Быстрые ответы на вопросы"""
                    
                    self.send_message(chat_id, info_text)
                
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
                    
                    self.send_message(chat_id, contacts_text)
                
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
                    
                    self.send_message(chat_id, about_text)
                
                elif text == "🔙 Назад":
                    self.send_message(chat_id, "🏠 Главное меню:", self.get_main_keyboard())
                
                else:
                    self.send_message(
                        chat_id,
                        "❓ Используйте кнопки меню\n\n/start - главное меню",
                        self.get_main_keyboard()
                    )
                    
            except Exception as e:
                logger.error(f"❌ Ошибка обработки: {e}")
                self.send_message(chat_id, "⚠️ Ошибка. Попробуйте /start")
    
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
                "channel": self.channel_parser.channel_url
            })
        
        @self.app.route('/posts')
        def posts_api():
            try:
                posts = self.channel_parser.get_cached_posts()
                return jsonify({
                    "status": "ok",
                    "count": len(posts),
                    "posts": posts,
                    "channel": self.channel_parser.channel_url
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
        """Запуск бота"""
        logger.info("🚀 Запуск простого Cat Bot...")
        
        # Предзагрузка постов
        try:
            posts = self.channel_parser.get_cached_posts()
            logger.info(f"✅ Загружено {len(posts)} постов")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось загрузить посты: {e}")
        
        if self.setup_webhook():
            logger.info(f"🌐 Сервер на порту {self.port}")
            self.app.run(host='0.0.0.0', port=self.port, debug=False)
        else:
            logger.error("🚨 Ошибка настройки webhook")

# 🚀 Запуск
if __name__ == "__main__":
    bot = CatBotSimple()
    bot.run()
