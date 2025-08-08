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
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='bot.log'
)
logger = logging.getLogger(__name__)

class SimpleChannelParser:
    """Улучшенный парсер каналов с поддержкой фото"""
    
    def __init__(self):
        self.channels = [
            {
                'username': 'lapki_ruchki_yalta',
                'url': 'https://t.me/lapki_ruchki_yalta',
                'type': 'cats'
            },
            {
                'username': 'yalta_aninmals',
                'url': 'https://t.me/yalta_aninmals',
                'type': 'dogs'
            }
        ]
        self.posts_cache = []
        self.last_update = None
    
    def get_channel_posts(self, channel_type: str = 'all', limit: int = 3) -> List[Dict]:
        """Получает последние посты с фото из указанного типа канала"""
        try:
            posts = []
            for channel in self.channels:
                if channel_type != 'all' and channel['type'] != channel_type:
                    continue
                    
                web_url = f'https://t.me/s/{channel["username"]}'
                logger.info(f"🌐 Загрузка постов с {web_url}")
                response = requests.get(web_url, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }, timeout=10)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.content, 'html.parser')
                message_divs = soup.find_all('div', class_='tgme_widget_message')
                
                for div in message_divs[:limit*2]:
                    post_data = self.parse_message_div(div, channel)
                    if post_data and self.is_animal_related(post_data.get('text', ''), channel['type']):
                        posts.append(post_data)
                        
                    if len(posts) >= limit:
                        break
            
            if posts:
                self.posts_cache = posts
                self.last_update = datetime.now()
                logger.info(f"✅ Получено {len(posts)} постов (с фото: {sum(1 for p in posts if p['photo_url'])})")
            else:
                logger.warning("⚠️ Не найдено подходящих постов")
                
            return posts or self.get_mock_posts(channel_type)
            
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга: {e}")
            return self.get_mock_posts(channel_type)
    
    def parse_message_div(self, div, channel) -> Optional[Dict]:
        """Парсит пост, извлекая текст и фото"""
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
            
            return {
                'id': post_id,
                'text': text,
                'date': date_str,
                'url': f"{channel['url']}/{post_id}" if post_id else channel['url'],
                'title': self.extract_title(text, channel['type']),
                'description': self.extract_description(text),
                'contact': self.extract_contact(text),
                'photo_url': photo_url,
                'has_photo': bool(photo_url),
                'type': channel['type']
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга div: {e}")
            return None
    
    def extract_title(self, text: str, animal_type: str) -> str:
        """Извлекает заголовок из текста поста"""
        lines = text.split('\n')
        for line in lines[:3]:
            line = line.strip()
            if line and len(line) > 10:
                title = re.sub(r'[^\w\s\-\.,!?а-яёА-ЯЁ]', '', line)
                if len(title) > 50:
                    title = title[:50] + "..."
                return title or ("Кошка ищет дом" if animal_type == 'cats' else "Собака ищет дом")
        return "Кошка ищет дом" if animal_type == 'cats' else "Собака ищет дом"
    
    def extract_description(self, text: str) -> str:
        """Извлекает описание из текста"""
        clean_text = re.sub(r'@\w+|https?://\S+|\+?\d[\d\s\-\(\)]+', '', text)
        if len(clean_text) > 200:
            return clean_text[:200] + "..."
        return clean_text
    
    def extract_contact(self, text: str) -> str:
        """Извлекает контактную информацию"""
        phone_patterns = [
            r'\+?7[\s\-]?9\d{2}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',
            r'\+?7[\s\-]?\(9\d{2}\)[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',
            r'8[\s\-]?9\d{2}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',
            r'8[\s\-]?\(9\d{2}\)[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',
        ]
        
        phones = []
        for pattern in phone_patterns:
            found_phones = re.findall(pattern, text)
            phones.extend(found_phones)
        
        formatted_phones = []
        for phone in phones[:2]:
            clean_phone = re.sub(r'[^\d+]', '', phone)
            if clean_phone.startswith('8'):
                clean_phone = '+7' + clean_phone[1:]
            elif clean_phone.startswith('7'):
                clean_phone = '+' + clean_phone
            elif not clean_phone.startswith('+7'):
                clean_phone = '+7' + clean_phone
            formatted_phones.append(clean_phone)
        
        username_pattern = r'@\w+'
        usernames = re.findall(username_pattern, text)
        
        contacts = []
        if formatted_phones:
            contacts.extend(formatted_phones)
        if usernames:
            contacts.extend(usernames[:1])
            
        return ' • '.join(contacts) if contacts else "См. в канале"
    
    def is_animal_related(self, text: str, animal_type: str) -> bool:
        """Проверяет, относится ли пост к животным"""
        text_lower = text.lower()
        
        if animal_type == 'cats':
            cat_keywords = [
                'кот', 'кошк', 'котен', 'котик', 'мурз', 'мяу',
                'котята', 'котёнок', 'котёнка', 'кошечка',
                'ищет дом', 'нужен дом', 'в добрые руки', 'пристрой',
                'отдам', 'отдается', 'забрать', 'взять'
            ]
            exclusion_words = [
                'продам', 'продается', 'купл', 'цена', 'стоимость',
                'корм для', 'аксессуар', 'игрушк', 'товар'
            ]
        else:
            dog_keywords = [
                'собак', 'щен', 'пес', 'псин', 'лайк', 'дворняж',
                'щенок', 'щенки', 'собачк', 'песик',
                'ищет дом', 'нужен дом', 'в добрые руки', 'пристрой',
                'отдам', 'отдается', 'забрать', 'взять'
            ]
            exclusion_words = [
                'продам', 'продается', 'купл', 'цена', 'стоимость',
                'корм для', 'аксессуар', 'игрушк', 'товар', 'услуг'
            ]
        
        if any(excl_word in text_lower for excl_word in exclusion_words):
            return False
        
        keywords = cat_keywords if animal_type == 'cats' else dog_keywords
        return any(keyword in text_lower for keyword in keywords)
    
    def get_mock_posts(self, channel_type: str = 'cats') -> List[Dict]:
        """Возвращает тестовые посты"""
        if channel_type == 'cats':
            return [
                {
                    'id': '1001',
                    'title': '🐱 Котенок Мурзик ищет дом',
                    'description': 'Возраст: 2 месяца, мальчик, рыжий окрас. Здоров, привит, очень игривый.',
                    'date': '03.08.2025 14:30',
                    'url': 'https://t.me/lapki_ruchki_yalta/1001',
                    'contact': '@volunteer1 • +79781234567',
                    'photo_url': 'https://via.placeholder.com/600x400?text=Котенок+Мурзик',
                    'has_photo': True,
                    'type': 'cats'
                }
            ]
        else:
            return [
                {
                    'id': '2001',
                    'title': '🐶 Щенок Бобик ищет дом',
                    'description': 'Возраст: 3 месяца, мальчик, черный окрас. Здоров, привит, активный.',
                    'date': '03.08.2025 15:45',
                    'url': 'https://t.me/yalta_aninmals/2001',
                    'contact': '@dog_volunteer • +79787654321',
                    'photo_url': 'https://via.placeholder.com/600x400?text=Щенок+Бобик',
                    'has_photo': True,
                    'type': 'dogs'
                }
            ]
    
    def get_cached_posts(self, channel_type: str = 'all') -> List[Dict]:
        """Возвращает кэшированные посты"""
        if (not self.last_update or 
            (datetime.now() - self.last_update).seconds > 1800):
            try:
                return self.get_channel_posts(channel_type)
            except Exception as e:
                logger.error(f"Ошибка обновления кэша: {e}")
        return [p for p in self.posts_cache if channel_type == 'all' or p['type'] == channel_type] or self.get_mock_posts(channel_type)

class CatBotWithPhotos:
    """Бот с поддержкой фото из постов"""
    
    def __init__(self):
        self.token = os.environ.get('TOKEN')
        if not self.token:
            logger.error("❌ TOKEN не найден! Убедитесь, что переменная окружения TOKEN установлена")
            raise ValueError("Токен бота не найден")
        
        logger.info(f"✅ Токен бота получен (длина: {len(self.token)} символов)")
        
        self.bot = telebot.TeleBot(self.token)
        self.parser = SimpleChannelParser()
        self.app = Flask(__name__)
        self.port = int(os.environ.get('PORT', 8080))
        self.webhook_url = os.environ.get('WEBHOOK_URL')
        self.stats = {"users": set(), "messages": 0}
        
        self.setup_handlers()
        self.setup_routes()
    
    def format_phone_links(self, text: str) -> str:
        """Делает телефоны кликабельными"""
        phone_patterns = [
            (r'(\+7\d{10})', r'<a href="tel:\1">\1</a>'),
            (r'(\+7\s?\d{3}\s?\d{3}\s?\d{2}\s?\d{2})', lambda m: f'<a href="tel:{re.sub(r"[^+\d]", "", m.group(1))}">{m.group(1)}</a>'),
            (r'(8\s?\d{3}\s?\d{3}\s?\d{2}\s?\d{2})', lambda m: f'<a href="tel:+7{re.sub(r"[^\\d]", "", m.group(1))[1:]}">{m.group(1)}</a>'),
        ]
        
        result = text
        for pattern, replacement in phone_patterns:
            if callable(replacement):
                result = re.sub(pattern, replacement, result)
            else:
                result = re.sub(pattern, replacement, result)
        
        return result

    def send_post(self, chat_id: int, post: Dict):
        """Отправляет один пост"""
        try:
            emoji = '🐱' if post['type'] == 'cats' else '🐶'
            formatted_contact = self.format_phone_links(post['contact'])
            
            post_text = (
                f"{emoji} <b>{post['title']}</b>\n\n"
                f"{post['description']}\n\n"
                f"📅 {post['date']}\n"
                f"📞 {formatted_contact}\n"
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

    def send_channel_posts(self, chat_id: int, animal_type: str = 'cats'):
        """Отправляет посты из канала"""
        try:
            posts = self.parser.get_cached_posts(animal_type)
            
            if not posts:
                channel_url = self.parser.channels[0]['url'] if animal_type == 'cats' else self.parser.channels[1]['url']
                self.bot.send_message(
                    chat_id,
                    "😿 Сейчас нет актуальных объявлений.\n"
                    f"📢 Проверьте канал: {channel_url}"
                )
                return
            
            channel_name = "Лапки-ручки Ялта" if animal_type == 'cats' else "Ялта Животные"
            channel_url = self.parser.channels[0]['url'] if animal_type == 'cats' else self.parser.channels[1]['url']
            
            self.bot.send_message(
                chat_id,
                f"{'🐱' if animal_type == 'cats' else '🐶'} <b>{'КОШКИ' if animal_type == 'cats' else 'СОБАКИ'} ИЩУТ ДОМ</b>\n\n"
                f"📢 Последние объявления из канала:\n"
                f"<a href='{channel_url}'>{channel_name}</a>",
                parse_mode="HTML"
            )
            
            for post in posts:
                self.send_post(chat_id, post)
                time.sleep(0.5)
            
            help_text = self.format_phone_links(
                "💡 <b>Как помочь?</b>\n\n"
                f"🏠 <b>Взять {'кошку' if animal_type == 'cats' else 'собаку'}:</b>\nСвяжитесь по контактам из объявления\n\n"
                f"📢 <b>Канал:</b> {channel_url}\n\n"
                "🤝 <b>Стать волонтером:</b>\nНапишите в канал\n\n"
                "📞 <b>Горячая линия:</b> +7 978 144-90-70"
            )
            
            self.bot.send_message(chat_id, help_text, parse_mode="HTML")
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки постов: {e}")
            channel_url = self.parser.channels[0]['url'] if animal_type == 'cats' else self.parser.channels[1]['url']
            self.bot.send_message(
                chat_id,
                f"⚠️ Ошибка загрузки объявлений\n\n"
                f"Попробуйте позже или посетите канал:\n{channel_url}"
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
        """Загружает HTML файл"""
        try:
            if not os.path.exists(f'assets/{filename}'):
                logger.error(f"Файл не найден: assets/{filename}")
                return f"Файл {filename} не найден"
                
            with open(f'assets/{filename}', 'r', encoding='utf-8') as f:
                content = f.read()
                return self.format_phone_links(content)
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки HTML: {e}")
            return f"⚠️ Информация временно недоступна ({filename})"

    def setup_handlers(self):
        """Обработчики сообщений"""
        
        @self.bot.message_handler(commands=['start'])
        def start_handler(message):
            try:
                logger.info(f"🆕 Новый пользователь: {message.from_user.id}")
                self.stats["users"].add(message.from_user.id)
                self.stats["messages"] += 1
                    
                welcome_text = """👋 <b>Добро пожаловать!</b>

🐾 Помощник по уличным животным Ялты

Выберите раздел:
🏥 <b>Стерилизация</b> - информация о программах
🏠 <b>Пристройство</b> - животные ищут дом
📞 <b>Контакты</b> - связь с волонтерами
ℹ️ <b>О проекте</b> - наша деятельность

<b>Экстренная помощь:</b> <a href="tel:+79781449070">+7 978 144-90-70</a>"""
                
                self.bot.send_message(
                    message.chat.id, 
                    welcome_text, 
                    parse_mode="HTML",
                    reply_markup=self.get_main_keyboard()
                )
                logger.info(f"✅ Приветственное сообщение отправлено пользователю {message.from_user.id}")
            except Exception as e:
                logger.error(f"❌ Ошибка в обработчике /start: {e}")
                self.bot.send_message(
                    message.chat.id,
                    "⚠️ Произошла ошибка. Пожалуйста, попробуйте позже."
                )
        
        @self.bot.message_handler(commands=['update'])
        def update_handler(message):
            self.parser.posts_cache = []
            self.parser.last_update = None
            self.bot.send_message(message.chat.id, "🔄 Обновляю посты...")
            posts = self.parser.get_channel_posts()
            self.bot.send_message(
                message.chat.id, 
                f"✅ Обновлено: {len(posts)} постов (с фото: {sum(1 for p in posts if p['photo_url'])})"
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
        
        @self.bot.message_handler(func=lambda m: True)
        def message_handler(message):
            self.stats["users"].add(message.from_user.id)
            self.stats["messages"] += 1
            
            text = message.text
            chat_id = message.chat.id
            
            try:
                if text == "🏠 Пристройство":
                    info_text = """🏠 <b>Пристройство животных</b>

Выберите действие:

🐱 <b>Кошки ищут дом</b>
Актуальные объявления из канала

🐶 <b>Собаки ищут дом</b>
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
                    self.send_channel_posts(chat_id, 'cats')
                
                elif text == "🐶 Собаки ищут дом":
                    self.send_channel_posts(chat_id, 'dogs')
                
                elif text == "📝 Подать объявление":
                    info_text = f"""📝 <b>Подать объявление</b>

📢 <b>Каналы для объявлений:</b>
<a href="{self.parser.channels[0]['url']}">Лапки-ручки Ялта</a> (кошки)
<a href="{self.parser.channels[1]['url']}">Ялта Животные</a> (собаки)

✍️ <b>Как подать:</b>
1️⃣ Перейти в канал
2️⃣ Написать администраторам
3️⃣ Или связаться с координаторами:
   • Кошки: <a href="tel:+79781449070">+7 978 144-90-70</a>
   • Собаки: <a href="tel:+79780000002">+7 978 000-00-02</a>

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
🔹 Кошки: <a href="tel:+79781449070">+7 978 144-90-70</a>
🔹 Собаки: <a href="tel:+79780000002">+7 978 000-00-02</a>
🔹 Лечение: <a href="tel:+79780000003">+7 978 000-00-03</a>

🏥 <b>Клиники:</b>
🔹 "Айболит": <a href="tel:+79780000004">+7 978 000-00-04</a>
🔹 "ВетМир": <a href="tel:+79780000005">+7 978 000-00-05</a>

📱 <b>Социальные сети:</b>
🔹 Telegram: @yalta_animals
🔹 Instagram: @yalta_street_animals

📢 <b>Каналы:</b>
🔹 <a href="https://t.me/lapki_ruchki_yalta">Лапки-ручки Ялта</a>
🔹 <a href="https://t.me/yalta_aninmals">Ялта Животные</a>"""
                    
                    self.bot.send_message(chat_id, contacts_text, parse_mode="HTML")
                
                elif text == "ℹ️ О проекте":
                    about_text = """ℹ️ <b>О ПРОЕКТЕ</b>

🎯 <b>Миссия:</b>
Помощь бездомным животным Ялты

📊 <b>Достижения:</b>
🔹 Стерилизовано: 500+ кошек, 200+ собак
🔹 Пристроено: 200+ котят, 100+ щенков
🔹 Волонтеров: 50+ активных

💰 <b>Поддержать:</b>
Карта: 2202 2020 0000 0000
СБП: <a href="tel:+79781449070">+7 978 144-90-70</a>

🤝 <b>Стать волонтером:</b>
Пишите @animal_coordinator или <a href="tel:+79781449070">+7 978 144-90-70</a>

📞 <b>Экстренная помощь:</b>
<a href="tel:+79781449070">+7 978 144-90-70</a> (круглосуточно)"""
                    
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
                "status": "🤖 Animal Bot Running",
                "time": datetime.now().strftime('%H:%M:%S'),
                "users": len(self.stats["users"]),
                "messages": self.stats["messages"],
                "channels": [c['url'] for c in self.parser.channels]
            })
        
        @self.app.route('/posts')
        def posts_api():
            try:
                posts = self.parser.get_cached_posts()
                return jsonify({
                    "status": "ok",
                    "count": len(posts),
                    "posts": posts,
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
                logger.info(f"✅ Webhook установлен: {full_url}")
                return True
            else:
                logger.error("❌ Не удалось установить webhook")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка webhook: {e}")
            return False
    
    def run(self):
        """Запуск бота"""
        logger.info("🚀 Запуск AnimalBot...")
        
        try:
            posts = self.parser.get_cached_posts()
            logger.info(f"✅ Предзагружено {len(posts)} постов")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка предзагрузки: {e}")
        
        if self.setup_webhook():
            logger.info(f"🌐 Webhook сервер запущен на порту {self.port}")
            self.app.run(host='0.0.0.0', port=self.port)
        else:
            logger.info("🔃 Запуск в polling режиме")
            self.bot.polling(none_stop=True)

if __name__ == "__main__":
    # Создаем необходимые папки и файлы
    os.makedirs('assets/images', exist_ok=True)
    
    # Создаем файлы с информацией о стерилизации
    if not os.path.exists('assets/free_text.html'):
        with open('assets/free_text.html', 'w', encoding='utf-8') as f:
            f.write("""<b>🐾 БЕСПЛАТНАЯ СТЕРИЛИЗАЦИЯ</b>

🏥 <b>Программы:</b>
🔹 Муниципальная программа Ялты
🔹 Благотворительные фонды

📋 <b>Условия:</b>
✅ Бездомные животные
✅ Животные из малоимущих семей
✅ По направлению волонтеров

📞 <b>Контакты:</b>
🔹 Координатор: <a href="tel:+79780000010">+7 978 000-00-10</a>
🔹 Клиника "Айболит": <a href="tel:+79780000011">+7 978 000-00-11</a>

📍 <b>Адреса:</b>
ул. Кирова, 15 (пн-пт 9:00-18:00)

🔥 <b>ЭКСТРЕННАЯ ПОМОЩЬ:</b>
<a href="tel:+79781449070">+7 978 144-90-70</a> (круглосуточно)""")

    if not os.path.exists('assets/paid_text.html'):
        with open('assets/paid_text.html', 'w', encoding='utf-8') as f:
            f.write("""<b>💵 ПЛАТНАЯ СТЕРИЛИЗАЦИЯ</b>

🏥 <b>Клиники:</b>
🔹 "Айболит": от 3000₽ (кошки), от 5000₽ (собаки)
   📞 <a href="tel:+79780000012">+7 978 000-00-12</a>
🔹 "ВетМир": от 2500₽ (кошки), от 4500₽ (собаки)
   📞 <a href="tel:+79780000013">+7 978 000-00-13</a>

🌟 <b>Включено:</b>
✔️ Операция
✔️ Наркоз
✔️ Послеоперационный уход
✔️ Консультация

💡 <b>Скидки:</b>
🔸 Волонтерам - 20%
🔸 Многодетным семьям - 15%

📞 <b>Консультации:</b>
<a href="tel:+79781449070">+7 978 144-90-70</a>""")

    # Запуск бота
    try:
        bot = CatBotWithPhotos()
        bot.run()
    except Exception as e:
        logger.critical(f"🚨 Критическая ошибка при запуске бота: {e}")
