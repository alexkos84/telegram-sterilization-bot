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
        """Извлекает контактную информацию с поддержкой кликабельных телефонов"""
        # Улучшенный паттерн для номеров телефонов
        phone_patterns = [
            r'\+?7[\s\-]?9\d{2}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',  # +7 9XX XXX XX XX
            r'\+?7[\s\-]?\(9\d{2}\)[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',  # +7 (9XX) XXX XX XX
            r'8[\s\-]?9\d{2}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',  # 8 9XX XXX XX XX
            r'8[\s\-]?\(9\d{2}\)[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}',  # 8 (9XX) XXX XX XX
        ]
        
        phones = []
        for pattern in phone_patterns:
            found_phones = re.findall(pattern, text)
            phones.extend(found_phones)
        
        # Очищаем и форматируем номера
        formatted_phones = []
        for phone in phones[:2]:  # Максимум 2 телефона
            # Убираем лишние символы
            clean_phone = re.sub(r'[^\d+]', '', phone)
            if clean_phone.startswith('8'):
                clean_phone = '+7' + clean_phone[1:]
            elif clean_phone.startswith('7'):
                clean_phone = '+' + clean_phone
            elif not clean_phone.startswith('+7'):
                clean_phone = '+7' + clean_phone
            
            formatted_phones.append(clean_phone)
        
        # Находим никнеймы
        username_pattern = r'@\w+'
        usernames = re.findall(username_pattern, text)
        
        contacts = []
        if formatted_phones:
            contacts.extend(formatted_phones)
        if usernames:
            contacts.extend(usernames[:1])
            
        return ' • '.join(contacts) if contacts else "См. в канале"
    
    def is_animal_related(self, text: str, animal_type: str) -> bool:
        """Проверяет, относится ли пост к животным с улучшенными ключевыми словами"""
        text_lower = text.lower()
        
        if animal_type == 'cats':
            # Расширенные ключевые слова для кошек
            cat_keywords = [
                # Основные слова
                'кот', 'кошк', 'котен', 'котик', 'мурз', 'мяу',
                'котята', 'котёнок', 'котёнка', 'кошечка',
                # Действия и состояния
                'ищет дом', 'нужен дом', 'в добрые руки', 'пристрой',
                'требуется дом', 'ищем дом', 'нуждается в доме',
                'отдам', 'отдается', 'забрать', 'взять',
                # Медицинские термины
                'кастрир', 'стерил', 'привит', 'обработан', 'здоров',
                'вакцинир', 'чип', 'паспорт', 'ветеринар',
                # Характеристики
                'ласков', 'игрив', 'спокойн', 'дружелюбн', 'социализир',
                'к людям', 'к детям', 'к другим', 'характер',
                # Помощь
                'помощь', 'спас', 'волонтер', 'приют', 'передержка',
                'куратор', 'опека'
            ]
            
            # Исключающие слова (чтобы не попадали нерелевантные посты)
            exclusion_words = [
                'продам', 'продается', 'купл', 'цена', 'стоимость',
                'корм для', 'аксессуар', 'игрушк', 'товар'
            ]
            
        else:  # dogs
            # Расширенные ключевые слова для собак
            cat_keywords = [
                # Основные слова
                'собак', 'щен', 'пес', 'псин', 'лайк', 'дворняж',
                'щенок', 'щенки', 'собачк', 'песик',
                # Породы (основные)
                'овчарк', 'лабрадор', 'хаски', 'терьер', 'шпиц',
                'такс', 'чихуахуа', 'йорк', 'мопс', 'бульдог',
                'дог', 'ротвейлер', 'доберман', 'спаниель',
                # Действия и состояния  
                'ищет дом', 'нужен дом', 'в добрые руки', 'пристрой',
                'требуется дом', 'ищем дом', 'нуждается в доме',
                'отдам', 'отдается', 'забрать', 'взять',
                # Медицинские термины
                'кастрир', 'стерил', 'привит', 'обработан', 'здоров',
                'вакцинир', 'чип', 'паспорт', 'ветеринар',
                # Характеристики
                'добр', 'верн', 'послушн', 'активн', 'спокойн',
                'дружелюбн', 'социализир', 'к людям', 'к детям',
                'охранн', 'сторож', 'компаньон', 'характер',
                # Размер
                'крупн', 'средн', 'мелк', 'больш', 'маленьк',
                # Помощь
                'помощь', 'спас', 'волонтер', 'приют', 'передержка',
                'куратор', 'опека'
            ]
            
            exclusion_words = [
                'продам', 'продается', 'купл', 'цена', 'стоимость',
                'корм для', 'аксессуар', 'игрушк', 'товар', 'услуг'
            ]
        
        # Проверяем исключающие слова
        if any(excl_word in text_lower for excl_word in exclusion_words):
            return False
        
        # Проверяем наличие ключевых слов
        return any(keyword in text_lower for keyword in cat_keywords)
    
    def get_mock_posts(self, channel_type: str = 'cats') -> List[Dict]:
        """Возвращает тестовые посты с фото"""
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
        """Возвращает кэшированные или обновленные посты"""
        if (not self.last_update or 
            (datetime.now() - self.last_update).seconds > 1800):
            try:
                return self.get_channel_posts(channel_type)
            except:
                pass
        return [p for p in self.posts_cache if channel_type == 'all' or p['type'] == channel_type] or self.get_mock_posts(channel_type)

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
    
    def format_phone_links(self, text: str) -> str:
        """Делает телефоны в тексте кликабельными"""
        # Паттерны для поиска телефонов
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
        """Отправляет один пост с фото или текстом"""
        try:
            emoji = '🐱' if post['type'] == 'cats' else '🐶'
            
            # Форматируем контакты с кликабельными телефонами
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
        """Отправляет все посты с фото"""
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
            
            # Кликабельные телефоны в итоговом сообщении
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
        """Загружает HTML файл из папки assets"""
        try:
            with open(f'assets/{filename}', 'r', encoding='utf-8') as f:
                content = f.read()
                return self.format_phone_links(content)  # Делаем телефоны кликабельными
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки HTML: {e}")
            return f"⚠️ Информация временно недоступна ({filename})"

    def setup_handlers(self):
        """Обработчики сообщений"""
        
        @self.bot.message_handler(commands=['start'])
        def start_handler(message):
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
<a href="{self.parser.channels[1]['url']}">
