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

class AdvancedChannelParser:
    """Парсер групп и каналов о животных в Ялте"""
    
    def __init__(self):
        self.channels = [
            {
                'username': 'cats_yalta',
                'url': 'https://t.me/cats_yalta',
                'type': 'cats',
                'title': 'Котики Ялта (канал)'
            },
            {
                'username': 'cats_yalta_group',
                'url': 'https://t.me/cats_yalta_group',
                'type': 'cats',
                'title': 'Котики Ялта (группа)'
            },
            {
                'username': 'dogs_yalta',
                'url': 'https://t.me/dogs_yalta',
                'type': 'dogs',
                'title': 'Собаки Ялта'
            }
        ]
        self.posts_cache = []
        self.last_update = None
    
    def get_channel_posts(self, channel_type: str = 'all', limit: int = 5) -> List[Dict]:
        """Получает последние посты с фото из всех каналов"""
        try:
            posts = []
            for channel in self.channels:
                if channel_type != 'all' and channel['type'] != channel_type:
                    continue
                    
                web_url = f'https://t.me/s/{channel["username"]}'
                logger.info(f"🌐 Загрузка постов с {web_url}")
                response = requests.get(web_url, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }, timeout=15)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.content, 'html.parser')
                message_divs = soup.find_all('div', class_='tgme_widget_message')
                
                for div in message_divs[:limit*2]:
                    post_data = self.parse_message_div(div, channel)
                    if post_data and self.is_animal_related(post_data.get('text', ''), channel['type']):
                        posts.append(post_data)
                        if len(posts) >= limit:
                            break
            
            # Сортируем по дате (новые сначала)
            posts.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
            
            if posts:
                self.posts_cache = posts[:limit]
                self.last_update = datetime.now()
                logger.info(f"✅ Получено {len(posts)} постов (с фото: {sum(1 for p in posts if p['photo_url'])})")
            else:
                logger.warning("⚠️ Не найдено подходящих постов")
                
            return posts[:limit] or self.get_mock_posts(channel_type)
            
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга: {e}")
            return self.get_mock_posts(channel_type)
    
    def parse_message_div(self, div, channel) -> Optional[Dict]:
        """Парсит пост, извлекая текст и фото"""
        try:
            # Базовые данные
            post_id = div.get('data-post', '').split('/')[-1] or 'unknown'
            text_div = div.find('div', class_='tgme_widget_message_text')
            text = text_div.get_text(strip=True) if text_div else ""
            
            # Дата
            timestamp = 0
            date_elem = div.find('time', datetime=True)
            date_str = "Недавно"
            if date_elem:
                try:
                    dt = datetime.fromisoformat(date_elem['datetime'].replace('Z', '+00:00'))
                    date_str = dt.strftime('%d.%m.%Y %H:%M')
                    timestamp = dt.timestamp()
                except:
                    pass
            
            # Фото (основное превью)
            photo_url = None
            photo_wrap = div.find('a', class_='tgme_widget_message_photo_wrap')
            if photo_wrap and photo_wrap.get('style'):
                match = re.search(r"background-image:url\('(.*?)'\)", photo_wrap['style'])
                if match:
                    photo_url = match.group(1)
            
            # Видео
            video_url = None
            video_wrap = div.find('div', class_='tgme_widget_message_video_wrap')
            if video_wrap and video_wrap.get('style'):
                match = re.search(r"background-image:url\('(.*?)'\)", video_wrap['style'])
                if match:
                    video_url = match.group(1)
            
            if not text and not photo_url and not video_url:
                return None
            
            return {
                'id': post_id,
                'text': text,
                'date': date_str,
                'timestamp': timestamp,
                'url': f"{channel['url']}/{post_id}" if post_id else channel['url'],
                'title': self.extract_title(text, channel['type']),
                'description': self.extract_description(text),
                'contact': self.extract_contact(text),
                'photo_url': photo_url,
                'video_url': video_url,
                'has_media': bool(photo_url or video_url),
                'type': channel['type'],
                'channel': channel['title'],
                'channel_url': channel['url']
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга div: {e}")
            return None
    
    def extract_title(self, text: str, animal_type: str) -> str:
        """Извлекает заголовок из текста поста"""
        lines = text.split('\n')
        for line in lines[:3]:
            line = line.strip()
            if line and len(line) > 5:
                title = re.sub(r'[^\w\s\-\.,!?а-яёА-ЯЁ]', '', line)
                if len(title) > 50:
                    title = title[:50] + "..."
                return title or ("Котик ищет дом" if animal_type == 'cats' else "Собака ищет дом")
        return "Котик ищет дом" if animal_type == 'cats' else "Собака ищет дом"
    
    def extract_description(self, text: str) -> str:
        """Извлекает описание из текста"""
        clean_text = re.sub(r'@\w+|https?://\S+|\+?\d[\d\s\-\(\)]+', '', text)
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        if len(clean_text) > 200:
            return clean_text[:200] + "..."
        return clean_text or "Подробности в посте"
    
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
            
        return ' • '.join(contacts) if contacts else "См. в группе"
    
    def is_animal_related(self, text: str, animal_type: str) -> bool:
        """Проверяет, относится ли пост к животным"""
        if animal_type == 'cats':
            animal_keywords = [
                'кот', 'кошк', 'котен', 'котик', 'мурз', 'мяу',
                'пристрой', 'дом', 'питомец', 'стерил', 'прививк',
                'потерял', 'нашел', 'пропал', 'найден', 'потеряшка'
            ]
        else:
            animal_keywords = [
                'собак', 'щен', 'пес', 'псин', 'гав', 'лай',
                'пристрой', 'дом', 'питомец', 'стерил', 'прививк',
                'потерял', 'нашел', 'пропал', 'найден', 'потеряшка'
            ]
            
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in animal_keywords)
    
    def get_mock_posts(self, channel_type: str = 'cats') -> List[Dict]:
        """Возвращает тестовые посты с фото"""
        if channel_type == 'cats':
            return [
                {
                    'id': '1001',
                    'title': '🐱 Котенок Мурзик ищет дом',
                    'description': 'Возраст: 2 месяца, мальчик, рыжий окрас. Здоров, привит, очень игривый.',
                    'date': '03.08.2025 14:30',
                    'timestamp': time.time(),
                    'url': 'https://t.me/cats_yalta/1001',
                    'contact': '@volunteer1 • +7 978 123-45-67',
                    'photo_url': 'https://via.placeholder.com/600x400?text=Котенок+Мурзик',
                    'video_url': None,
                    'has_media': True,
                    'type': 'cats',
                    'channel': 'Котики Ялта',
                    'channel_url': 'https://t.me/cats_yalta'
                },
                {
                    'id': '1002',
                    'title': '🐱 Взрослый кот Барсик',
                    'description': 'Ищет дом взрослый кот, 3 года, кастрирован, приучен к лотку.',
                    'date': '02.08.2025 11:20',
                    'timestamp': time.time() - 3600,
                    'url': 'https://t.me/cats_yalta_group/1002',
                    'contact': '+7 978 765-43-21',
                    'photo_url': 'https://via.placeholder.com/600x400?text=Кот+Барсик',
                    'video_url': None,
                    'has_media': True,
                    'type': 'cats',
                    'channel': 'Котики Ялта (группа)',
                    'channel_url': 'https://t.me/cats_yalta_group'
                }
            ]
        else:
            return [
                {
                    'id': '2001',
                    'title': '🐶 Щенок Рекс ищет дом',
                    'description': 'Возраст: 3 месяца, мальчик, черный окрас. Активный, дружелюбный, привит.',
                    'date': '04.08.2025 10:15',
                    'timestamp': time.time(),
                    'url': 'https://t.me/dogs_yalta/2001',
                    'contact': '@dog_volunteer • +7 978 111-22-33',
                    'photo_url': 'https://via.placeholder.com/600x400?text=Щенок+Рекс',
                    'video_url': None,
                    'has_media': True,
                    'type': 'dogs',
                    'channel': 'Собаки Ялта',
                    'channel_url': 'https://t.me/dogs_yalta'
                },
                {
                    'id': '2002',
                    'title': '🐶 Взрослая собака Лайма',
                    'description': 'Ищет дом взрослая собака, 4 года, стерилизована, приучена к поводку.',
                    'date': '01.08.2025 09:10',
                    'timestamp': time.time() - 7200,
                    'url': 'https://t.me/dogs_yalta/2002',
                    'contact': '+7 978 222-33-44',
                    'photo_url': 'https://via.placeholder.com/600x400?text=Собака+Лайма',
                    'video_url': None,
                    'has_media': True,
                    'type': 'dogs',
                    'channel': 'Собаки Ялта',
                    'channel_url': 'https://t.me/dogs_yalta'
                }
            ]
    
    def get_cached_posts(self, channel_type: str = 'all') -> List[Dict]:
        """Возвращает кэшированные или обновленные посты"""
        if (not self.last_update or 
            (datetime.now() - self.last_update).seconds > 3600):  # Обновляем каждый час
            try:
                return self.get_channel_posts(channel_type)
            except:
                pass
        return [p for p in self.posts_cache if channel_type == 'all' or p['type'] == channel_type] or self.get_mock_posts(channel_type)

class CatBotWithPhotos:
    """Бот для помощи животным Ялты с поддержкой фото и видео"""
    
    def __init__(self):
        self.token = os.environ.get('TOKEN')
        if not self.token:
            logger.error("❌ TOKEN не найден!")
            exit(1)
        
        self.bot = telebot.TeleBot(self.token)
        self.parser = AdvancedChannelParser()
        self.app = Flask(__name__)
        self.port = int(os.environ.get('PORT', 8080))
        self.webhook_url = os.environ.get('WEBHOOK_URL')
        self.stats = {"users": set(), "messages": 0}
        
        self.setup_handlers()
        self.setup_routes()
    
    def send_post(self, chat_id: int, post: Dict):
        """Отправляет один пост с медиа или текстом"""
        try:
            emoji = '🐱' if post['type'] == 'cats' else '🐶'
            post_text = (
                f"{emoji} <b>{post['title']}</b>\n\n"
                f"{post['description']}\n\n"
                f"📅 {post['date']}\n"
                f"📞 {post['contact']}\n"
                f"📢 <a href='{post['channel_url']}'>{post['channel']}</a>\n"
                f"🔗 <a href='{post['url']}'>Открыть пост</a>"
            )
            
            if len(post_text) > 1024:
                post_text = post_text[:1000] + "..."
            
            # Пытаемся отправить медиа
            if post.get('photo_url'):
                try:
                    self.bot.send_photo(
                        chat_id,
                        post['photo_url'],
                        caption=post_text,
                        parse_mode="HTML",
                        reply_markup=types.InlineKeyboardMarkup().add(
                            types.InlineKeyboardButton("📢 Открыть пост", url=post['url'])
                        )
                    )
                    return
                except Exception as e:
                    logger.error(f"❌ Ошибка отправки фото: {e}")
            
            if post.get('video_url'):
                try:
                    self.bot.send_video(
                        chat_id,
                        post['video_url'],
                        caption=post_text,
                        parse_mode="HTML",
                        reply_markup=types.InlineKeyboardMarkup().add(
                            types.InlineKeyboardButton("📢 Открыть пост", url=post['url'])
                        )
                    )
                    return
                except Exception as e:
                    logger.error(f"❌ Ошибка отправки видео: {e}")
            
            # Если не удалось отправить медиа, отправляем текст
            self.bot.send_message(
                chat_id,
                post_text,
                parse_mode="HTML",
                disable_web_page_preview=False,
                reply_markup=types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton("📢 Открыть пост", url=post['url'])
                )
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки поста: {e}")

    def send_channel_posts(self, chat_id: int, animal_type: str = 'cats'):
        """Отправляет все посты с медиа"""
        try:
            posts = self.parser.get_cached_posts(animal_type)
            
            if not posts:
                self.bot.send_message(
                    chat_id,
                    "😿 Сейчас нет актуальных объявлений.\n"
                    f"📢 Проверьте группы:\n"
                    f"• {self.parser.channels[0]['url']}\n"
                    f"• {self.parser.channels[1]['url']}"
                )
                return
            
            animal_name = "КОТИКИ" if animal_type == 'cats' else "СОБАКИ"
            self.bot.send_message(
                chat_id,
                f"{'🐱' if animal_type == 'cats' else '🐶'} <b>{animal_name} ИЩУТ ДОМ</b>\n\n"
                f"📢 Последние объявления из групп Ялты:",
                parse_mode="HTML"
            )
            
            for post in posts:
                self.send_post(chat_id, post)
                time.sleep(0.7)  # Задержка между постами
            
            self.bot.send_message(
                chat_id,
                "💡 <b>Как помочь?</b>\n\n"
                f"🏠 <b>Взять питомца:</b>\nСвяжитесь по контактам из объявления\n\n"
                f"📢 <b>Группы:</b>\n"
                f"• <a href='{self.parser.channels[0]['url']}'>Котики Ялта (канал)</a>\n"
                f"• <a href='{self.parser.channels[1]['url']}'>Котики Ялта (группа)</a>\n"
                f"• <a href='{self.parser.channels[2]['url']}'>Собаки Ялта</a>\n\n"
                "🤝 <b>Стать волонтером:</b>\nНапишите в соответствующую группу",
                parse_mode="HTML"
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки постов: {e}")
            self.bot.send_message(
                chat_id,
                f"⚠️ Ошибка загрузки объявлений\n\n"
                f"Попробуйте позже или посетите группы:\n"
                f"• {self.parser.channels[0]['url']}\n"
                f"• {self.parser.channels[1]['url']}\n"
                f"• {self.parser.channels[2]['url']}"
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
        markup.add("🐱 Кошки ищут дом", "🐶 Собаки ищут дом")
        markup.add("📝 Подать объявление")
        markup.add("🔙 Назад")
        return markup
    
    def get_sterilization_keyboard(self):
        """Клавиатура стерилизации"""
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("💰 Платная стерилизация", "🆓 Бесплатная стерилизация")
        markup.add("🔙 Назад")
        return markup

    def load_html_file(self, filename: str) -> str:
        """Загружает HTML файл из папки assets"""
        try:
            with open(f'assets/{filename}', 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки HTML: {e}")
            return f"⚠️ Информация временно недоступна ({filename})"

    def setup_handlers(self):
        """Обработчики сообщений"""
        
        @self.bot.message_handler(commands=['start'])
        def start_handler(message):
            self.stats["users"].add(message.from_user.id)
            self.stats["messages"] += 1
            
            welcome_text = """👋 <b>Добро пожаловать в "Помощь животным Ялты"!</b>

🐾 Помощник по животным Ялты

Выберите раздел:
🏥 <b>Стерилизация</b> - информация
🏠 <b>Пристройство</b> - животные ищут дом
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
            if message.from_user.id not in [123456789]:  # Замените на ваш ID
                return
                
            self.parser.posts_cache = []
            self.parser.last_update = None
            self.bot.send_message(message.chat.id, "🔄 Обновляю посты...")
            posts = self.parser.get_channel_posts()
            self.bot.send_message(
                message.chat.id, 
                f"✅ Обновлено: {len(posts)} постов (с медиа: {sum(1 for p in posts if p['has_media'])})"
            )
        
        @self.bot.message_handler(func=lambda m: m.text == "🏥 Стерилизация")
        def sterilization_handler(message):
            self.stats["users"].add(message.from_user.id)
            self.stats["messages"] += 1
            
            try:
                with open('assets/images/sterilization.jpg', 'rb') as photo:
                    self.bot.send_photo(
                        message.chat.id,
                        photo,
                        caption="🏥 <b>Стерилизация животных</b>\n\nВыберите вариант:",
                        parse_mode="HTML",
                        reply_markup=self.get_sterilization_keyboard()
                    )
            except Exception as e:
                logger.error(f"❌ Ошибка загрузки фото: {e}")
                self.bot.send_message(
                    message.chat.id,
                    "🏥 <b>Стерилизация животных</b>\n\nВыберите вариант:",
                    parse_mode="HTML",
                    reply_markup=self.get_sterilization_keyboard()
                )
        
        @self.bot.message_handler(func=lambda m: m.text == "💰 Платная стерилизация")
        def paid_sterilization_handler(message):
            self.bot.send_message(
                message.chat.id,
                self.load_html_file('paid_text.html'),
                parse_mode="HTML"
            )
        
        @self.bot.message_handler(func=lambda m: m.text == "🆓 Бесплатная стерилизация")
        def free_sterilization_handler(message):
            self.bot.send_message(
                message.chat.id,
                self.load_html_file('free_text.html'),
                parse_mode="HTML"
            )
        
        @self.bot.message_handler(func=lambda m: m.text == "🏠 Пристройство")
        def adoption_handler(message):
            self.stats["users"].add(message.from_user.id)
            self.stats["messages"] += 1
            
            info_text = """🏠 <b>Пристройство животных</b>

Выберите действие:

🐱 <b>Кошки ищут дом</b>
Актуальные объявления о кошках

🐶 <b>Собаки ищут дом</b>
Актуальные объявления о собаках

📝 <b>Подать объявление</b>
Как разместить свое объявление"""
                    
            self.bot.send_message(
                message.chat.id, 
                info_text, 
                parse_mode="HTML",
                reply_markup=self.get_adoption_keyboard()
            )
        
        @self.bot.message_handler(func=lambda m: m.text == "🐱 Кошки ищут дом")
        def cats_posts_handler(message):
            self.send_channel_posts(message.chat.id, 'cats')
        
        @self.bot.message_handler(func=lambda m: m.text == "🐶 Собаки ищут дом")
        def dogs_posts_handler(message):
            self.send_channel_posts(message.chat.id, 'dogs')
        
        @self.bot.message_handler(func=lambda m: m.text == "📝 Подать объявление")
        def submit_ad_handler(message):
            info_text = f"""📝 <b>Подать объявление</b>

📢 <b>Группы для объявлений:</b>
• <a href="{self.parser.channels[0]['url']}">Котики Ялта (канал)</a>
• <a href="{self.parser.channels[1]['url']}">Котики Ялта (группа)</a>
• <a href="{self.parser.channels[2]['url']}">Собаки Ялта</a>

✍️ <b>Как подать:</b>
1️⃣ Перейти в соответствующую группу
2️⃣ Написать администраторам
3️⃣ Или связаться с координатором: +7 978 000-00-01

📋 <b>Нужная информация:</b>
🔹 Фото животного
🔹 Возраст, пол, окрас
🔹 Характер
🔹 Здоровье (прививки, стерилизация)
🔹 Ваши контакты"""
                    
            self.bot.send_message(message.chat.id, info_text, parse_mode="HTML")
        
        @self.bot.message_handler(func=lambda m: m.text == "📞 Контакты")
        def contacts_handler(message):
            contacts_text = """📞 <b>КОНТАКТЫ</b>

👥 <b>Координаторы:</b>
🔹 По кошкам: +7 978 144-90-70
🔹 По собакам: +7 978 000-00-02
🔹 Стерилизация: +7 978 000-00-03
🔹 Лечение: +7 978 000-00-04

🏥 <b>Клиники:</b>
🔹 "Айболит": +7 978 000-00-05
🔹 "ВетМир": +7 978 000-00-06

📱 <b>Социальные сети:</b>
🔹 Telegram: @animals_yalta
🔹 Instagram: @yalta_animals"""
                    
            self.bot.send_message(message.chat.id, contacts_text, parse_mode="HTML")
        
        @self.bot.message_handler(func=lambda m: m.text == "ℹ️ О проекте")
        def about_handler(message):
            about_text = """ℹ️ <b>О ПРОЕКТЕ "ПОМОЩЬ ЖИВОТНЫМ ЯЛТЫ"</b>

🎯 <b>Миссия:</b>
Помощь бездомным животным Ялты

📊 <b>Достижения:</b>
🔹 Стерилизовано: 800+ животных
🔹 Пристроено: 500+ питомцев
🔹 Волонтеров: 50+ активных

💰 <b>Поддержать:</b>
Карта: 2202 2020 0000 0000

🤝 <b>Стать волонтером:</b>
Пишите @animals_yalta_coordinator"""
                    
            self.bot.send_message(message.chat.id, about_text, parse_mode="HTML")
        
        @self.bot.message_handler(func=lambda m: m.text == "🔙 Назад")
        def back_handler(message):
            self.bot.send_message(
                message.chat.id, 
                "🏠 Главное меню:", 
                reply_markup=self.get_main_keyboard()
            )
        
        @self.bot.message_handler(func=lambda m: True)
        def default_handler(message):
            self.stats["users"].add(message.from_user.id)
            self.stats["messages"] += 1
            self.bot.send_message(
                message.chat.id,
                "❓ Используйте кнопки меню\n\n/start - главное меню",
                reply_markup=self.get_main_keyboard()
            )
    
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
                "status": "🤖 Animal Bot Running",
                "time": datetime.now().strftime('%H:%M:%S'),
                "users": len(self.stats["users"]),
                "messages": self.stats["messages"],
                "channels": [c['url'] for c in self.parser.channels],
                "last_update": self.parser.last_update.isoformat() if self.parser.last_update else None
            })
        
        @self.app.route('/posts')
        def posts_api():
            try:
                posts = self.parser.get_cached_posts()
                return jsonify({
                    "status": "ok",
                    "count": len(posts),
                    "posts": [{
                        "title": p["title"],
                        "url": p["url"],
                        "date": p["date"],
                        "channel": p["channel"]
                    } for p in posts],
                    "channels": [c['url'] for c in self.parser.channels]
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
        logger.info("🚀 Запуск AnimalBot для Ялты...")
        
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
    # Создаем необходимые папки и файлы, если их нет
    os.makedirs('assets/images', exist_ok=True)
    
    # Создаем файлы с информацией о стерилизации
    if not os.path.exists('assets/free_text.html'):
        with open('assets/free_text.html', 'w', encoding='utf-8') as f:
            f.write("""<b>🐾 БЕСПЛАТНАЯ СТЕРИЛИЗАЦИЯ ЖИВОТНЫХ</b>

🏥 <b>Программы:</b>
🔹 Муниципальная программа Ялты
🔹 Благотворительные фонды

📋 <b>Условия:</b>
✅ Бездомные животные
✅ Животные из малоимущих семей
✅ По направлению волонтеров

📞 <b>Контакты:</b>
🔹 Координатор: +7 978 144-90-70
🔹 Клиника "Айболит": +7 978 000-00-11

📍 <b>Адреса:</b>
ул. Кирова, 15 (пн-пт 9:00-18:00)""")

    if not os.path.exists('assets/paid_text.html'):
        with open('assets/paid_text.html', 'w', encoding='utf-8') as f:
            f.write("""<b>💵 ПЛАТНАЯ СТЕРИЛИЗАЦИЯ ЖИВОТНЫХ</b>

🏥 <b>Клиники:</b>
🔹 "Айболит": от 3000₽ (кошки), от 5000₽ (собаки)
🔹 "ВетМир": от 2500₽ (кошки), от 4500₽ (собаки)

🌟 <b>Включено:</b>
✔️ Операция
✔️ Наркоз
✔️ Послеоперационный уход
✔️ Консультация

📞 <b>Запись:</b>
🔹 "Айболит": +7 978 000-00-12
🔹 "ВетМир": +7 978 000-00-13

💡 <b>Скидки:</b>
🔸 Волонтерам - 20%
🔸 Многоквартирным животным - 15%""")

    # Создаем placeholder изображение, если его нет
    if not os.path.exists('assets/images/sterilization.jpg'):
        # Здесь можно добавить код для создания placeholder изображения
        pass

    bot = CatBotWithPhotos()
    bot.run()
