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
from enum import Enum

# 🔧 Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class PostCategory(Enum):
    CATS = "cats"
    DOGS = "dogs"
    FREE_ITEMS = "free_items"
    LOST_PETS = "lost_pets"

class EnhancedChannelParser:
    """Улучшенный парсер канала с поддержкой разных категорий"""
    
    def __init__(self):
        self.channel_username = 'Lapki_ruchki_Yalta_help'
        self.channel_url = 'https://t.me/Lapki_ruchki_Yalta_help'
        self.web_url = f'https://t.me/s/{self.channel_username}'
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.posts_cache = {category.value: [] for category in PostCategory}
        self.last_update = None
        
        # Ключевые слова для категорий
        self.keywords = {
            PostCategory.CATS: [
                'кот', 'кошк', 'котен', 'котик', 'мурз', 'мяу',
                'кастр', 'стерил', 'привит', 'пристрой', 'котята', 
                'мама-кошка', 'беременная', 'трёхцветная', 'рыжий',
                'черный кот', 'белая кошка', 'полосатый', 'пушистый'
            ],
            PostCategory.DOGS: [
                'собак', 'щенок', 'пес', 'песик', 'щен', 'собачк',
                'лабрадор', 'овчарка', 'дворняг', 'метис', 'хаски',
                'йорк', 'такс', 'чихуахуа', 'бульдог', 'шпиц',
                'ротвейлер', 'питбуль', 'стафф', 'дог', 'мопс'
            ],
            PostCategory.FREE_ITEMS: [
                'отдам', 'даром', 'бесплатно', 'шлейка', 'поводок',
                'лоток', 'корм', 'миск', 'переноска', 'домик',
                'когтеточка', 'игрушк', 'лекарств', 'витамин',
                'наполнитель', 'подстилка', 'одеяло', 'клетка'
            ],
            PostCategory.LOST_PETS: [
                'потерял', 'потеряш', 'найден', 'ищу', 'пропал',
                'убежал', 'сбежал', 'найдите', 'помогите найти',
                'видели', 'последний раз', 'район', 'вознаграждение',
                'верните', 'откликнитесь'
            ]
        }
    
    def get_channel_posts(self, category: PostCategory = None, limit: int = 5) -> List[Dict]:
        """Получает посты определенной категории или все"""
        try:
            logger.info(f"🌐 Загрузка постов с {self.web_url}")
            response = requests.get(self.web_url, headers=self.headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            message_divs = soup.find_all('div', class_='tgme_widget_message')
            
            # Очищаем кэш для обновления
            if category:
                self.posts_cache[category.value] = []
            else:
                for cat in PostCategory:
                    self.posts_cache[cat.value] = []
            
            # Парсим посты
            for div in message_divs[:limit*3]:  # Берем больше для фильтрации
                post_data = self.parse_message_div(div)
                if post_data:
                    post_category = self.categorize_post(post_data.get('text', ''))
                    if post_category:
                        post_data['category'] = post_category.value
                        post_data['category_emoji'] = self.get_category_emoji(post_category)
                        
                        if not category or category == post_category:
                            self.posts_cache[post_category.value].append(post_data)
            
            # Ограничиваем количество постов в каждой категории
            for cat in PostCategory:
                self.posts_cache[cat.value] = self.posts_cache[cat.value][:limit]
            
            self.last_update = datetime.now()
            
            if category:
                posts = self.posts_cache[category.value]
                logger.info(f"✅ Получено {len(posts)} постов категории {category.value}")
                return posts or self.get_mock_posts(category)
            else:
                total_posts = sum(len(posts) for posts in self.posts_cache.values())
                logger.info(f"✅ Получено {total_posts} постов всех категорий")
                return self.posts_cache
                
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга: {e}")
            return self.get_mock_posts(category) if category else self.get_all_mock_posts()
    
    def categorize_post(self, text: str) -> Optional[PostCategory]:
        """Определяет категорию поста по ключевым словам"""
        text_lower = text.lower()
        
        # Подсчитываем совпадения для каждой категории
        category_scores = {}
        for category, keywords in self.keywords.items():
            score = sum(1 for keyword in keywords if keyword in text_lower)
            if score > 0:
                category_scores[category] = score
        
        # Возвращаем категорию с наибольшим количеством совпадений
        if category_scores:
            return max(category_scores.items(), key=lambda x: x[1])[0]
        
        return None
    
    def get_category_emoji(self, category: PostCategory) -> str:
        """Возвращает эмодзи для категории"""
        emoji_map = {
            PostCategory.CATS: "🐱",
            PostCategory.DOGS: "🐶",
            PostCategory.FREE_ITEMS: "🎁",
            PostCategory.LOST_PETS: "🔍"
        }
        return emoji_map.get(category, "📋")
    
    def parse_message_div(self, div) -> Optional[Dict]:
        """Парсит пост, извлекая всю информацию"""
        try:
            # Базовые данные
            post_id = div.get('data-post', '').split('/')[-1] or f"post_{int(time.time())}"
            text_div = div.find('div', class_='tgme_widget_message_text')
            text = text_div.get_text(strip=True) if text_div else ""
            
            if not text or len(text) < 20:  # Фильтруем слишком короткие посты
                return None
            
            # Дата
            date_elem = div.find('time', datetime=True)
            date_str = "Недавно"
            if date_elem:
                try:
                    dt = datetime.fromisoformat(date_elem['datetime'].replace('Z', '+00:00'))
                    date_str = dt.strftime('%d.%m.%Y %H:%M')
                except:
                    pass
            
            # Фото
            photo_url = None
            photo_wrap = div.find('a', class_='tgme_widget_message_photo_wrap')
            if photo_wrap and photo_wrap.get('style'):
                match = re.search(r"background-image:url\('(.*?)'\)", photo_wrap['style'])
                if match:
                    photo_url = match.group(1)
            
            # Дополнительные фото в альбоме
            additional_photos = []
            photo_album = div.find('div', class_='tgme_widget_message_grouped')
            if photo_album:
                album_photos = photo_album.find_all('a', class_='tgme_widget_message_photo_wrap')
                for photo in album_photos[:3]:  # Максимум 3 дополнительных фото
                    if photo.get('style'):
                        match = re.search(r"background-image:url\('(.*?)'\)", photo['style'])
                        if match:
                            additional_photos.append(match.group(1))
            
            return {
                'id': post_id,
                'text': text,
                'date': date_str,
                'url': f"{self.channel_url}/{post_id}",
                'title': self.extract_title(text),
                'description': self.extract_description(text),
                'contact': self.extract_contact(text),
                'photo_url': photo_url,
                'additional_photos': additional_photos,
                'has_photo': bool(photo_url or additional_photos),
                'urgency': self.detect_urgency(text),
                'location': self.extract_location(text)
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга div: {e}")
            return None
    
    def extract_title(self, text: str) -> str:
        """Извлекает заголовок из текста поста"""
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        # Ищем первую содержательную строку
        for line in lines[:3]:
            if len(line) > 15 and not line.startswith(('http', '@', '+')):
                # Очищаем от эмодзи для определения длины
                clean_line = re.sub(r'[^\w\s\-\.,!?а-яёА-ЯЁ]', '', line)
                if len(clean_line) > 10:
                    title = line[:60] + "..." if len(line) > 60 else line
                    return title
        
        return text[:50] + "..." if len(text) > 50 else text
    
    def extract_description(self, text: str) -> str:
        """Извлекает описание из текста"""
        # Убираем контакты и ссылки
        clean_text = re.sub(r'@\w+|https?://\S+|\+?\d[\d\s\-\(\)]{7,}', '', text)
        # Убираем множественные пробелы и переносы
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        
        if len(clean_text) > 150:
            return clean_text[:150] + "..."
        return clean_text
    
    def extract_contact(self, text: str) -> str:
        """Извлекает контактную информацию"""
        contacts = []
        
        # Телефоны
        phone_patterns = [
            r'\+?[78][\s\-]?\(?9\d{2}\)?\s?[\d\s\-]{7,10}',
            r'\+?[78][\s\-]?\d{3}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}'
        ]
        
        for pattern in phone_patterns:
            phones = re.findall(pattern, text)
            contacts.extend(phones[:1])  # Берем только первый номер
        
        # Telegram username
        usernames = re.findall(r'@\w+', text)
        contacts.extend(usernames[:1])
        
        return ' • '.join(contacts) if contacts else "📞 См. в канале"
    
    def extract_location(self, text: str) -> str:
        """Извлекает информацию о местоположении"""
        location_keywords = [
            'ялта', 'алушта', 'гурзуф', 'форос', 'симеиз', 'кореиз',
            'ливадия', 'массандра', 'никита', 'партенит', 'центр',
            'район', 'набережная', 'парк', 'дворец', 'санаторий'
        ]
        
        text_lower = text.lower()
        found_locations = [loc for loc in location_keywords if loc in text_lower]
        
        if found_locations:
            return f"📍 {found_locations[0].title()}"
        return ""
    
    def detect_urgency(self, text: str) -> str:
        """Определяет срочность объявления"""
        urgent_keywords = [
            'срочно', 'очень срочно', 'умирает', 'критическое состояние',
            'нужна операция', 'помогите срочно', 'сегодня', 'завтра'
        ]
        
        text_lower = text.lower()
        if any(keyword in text_lower for keyword in urgent_keywords):
            return "🔥 СРОЧНО"
        return ""
    
    def get_mock_posts(self, category: PostCategory) -> List[Dict]:
        """Возвращает тестовые посты для категории"""
        mock_data = {
            PostCategory.CATS: [
                {
                    'id': '1001',
                    'title': '🐱 Котенок Мурзик ищет любящий дом',
                    'description': 'Возраст: 2 месяца, мальчик, рыжий окрас. Здоров, привит, очень игривый и ласковый.',
                    'date': '04.08.2025 14:30',
                    'url': f'{self.channel_url}/1001',
                    'contact': '@volunteer1 • +7 978 123-45-67',
                    'photo_url': 'https://via.placeholder.com/600x400/FF6B35/FFFFFF?text=🐱+Котенок+Мурзик',
                    'additional_photos': [],
                    'has_photo': True,
                    'category': 'cats',
                    'category_emoji': '🐱',
                    'urgency': '',
                    'location': '📍 Ялта'
                }
            ],
            PostCategory.DOGS: [
                {
                    'id': '2001',
                    'title': '🐶 Щенок Рекс в добрые руки',
                    'description': 'Возраст: 3 месяца, мальчик, метис овчарки. Привит, здоров, очень умный.',
                    'date': '04.08.2025 13:15',
                    'url': f'{self.channel_url}/2001',
                    'contact': '@dog_volunteer • +7 978 987-65-43',
                    'photo_url': 'https://via.placeholder.com/600x400/4ECDC4/FFFFFF?text=🐶+Щенок+Рекс',
                    'additional_photos': [],
                    'has_photo': True,
                    'category': 'dogs',
                    'category_emoji': '🐶',
                    'urgency': '',
                    'location': '📍 Алушта'
                }
            ],
            PostCategory.FREE_ITEMS: [
                {
                    'id': '3001',
                    'title': '🎁 Отдам корм для кошек и лоток',
                    'description': 'Сухой корм Whiskas 3кг (осталось много), лоток с высокими бортиками, наполнитель.',
                    'date': '04.08.2025 12:00',
                    'url': f'{self.channel_url}/3001',
                    'contact': '@free_items • +7 978 111-22-33',
                    'photo_url': 'https://via.placeholder.com/600x400/45B7D1/FFFFFF?text=🎁+Корм+и+лоток',
                    'additional_photos': [],
                    'has_photo': True,
                    'category': 'free_items',
                    'category_emoji': '🎁',
                    'urgency': '',
                    'location': '📍 Ялта'
                }
            ],
            PostCategory.LOST_PETS: [
                {
                    'id': '4001',
                    'title': '🔍 Потерялся кот Барсик!',
                    'description': 'Серый полосатый кот, пропал 2 августа в районе набережной. Очень скучаем!',
                    'date': '04.08.2025 10:30',
                    'url': f'{self.channel_url}/4001',
                    'contact': '@lost_pet_owner • +7 978 555-44-33',
                    'photo_url': 'https://via.placeholder.com/600x400/F38BA8/FFFFFF?text=🔍+Кот+Барсик',
                    'additional_photos': [],
                    'has_photo': True,
                    'category': 'lost_pets',
                    'category_emoji': '🔍',
                    'urgency': '🔥 СРОЧНО',
                    'location': '📍 Набережная'
                }
            ]
        }
        
        return mock_data.get(category, [])
    
    def get_all_mock_posts(self) -> Dict:
        """Возвращает все тестовые посты"""
        return {category.value: self.get_mock_posts(category) for category in PostCategory}
    
    def get_cached_posts(self, category: PostCategory = None) -> List[Dict]:
        """Возвращает кэшированные или обновленные посты"""
        if (not self.last_update or 
            (datetime.now() - self.last_update).seconds > 1800):  # 30 минут
            try:
                return self.get_channel_posts(category)
            except:
                pass
        
        if category:
            return self.posts_cache.get(category.value, []) or self.get_mock_posts(category)
        return self.posts_cache

class PetBotEnhanced:
    """Расширенный бот для животных с поддержкой категорий"""
    
    def __init__(self):
        self.token = os.environ.get('TOKEN')
        if not self.token:
            logger.error("❌ TOKEN не найден!")
            exit(1)
        
        self.bot = telebot.TeleBot(self.token)
        self.parser = EnhancedChannelParser()
        self.app = Flask(__name__)
        self.port = int(os.environ.get('PORT', 8080))
        self.webhook_url = os.environ.get('WEBHOOK_URL')
        self.stats = {"users": set(), "messages": 0}
        
        self.setup_handlers()
        self.setup_routes()
    
    def send_post(self, chat_id: int, post: Dict):
        """Отправляет красиво оформленный пост"""
        try:
            # Формируем красивый текст поста
            post_text = f"{'=' * 30}\n"
            
            # Заголовок с эмодзи категории
            if post.get('category_emoji'):
                post_text += f"{post['category_emoji']} "
            
            post_text += f"<b>{post['title']}</b>\n"
            
            # Срочность
            if post.get('urgency'):
                post_text += f"{post['urgency']}\n"
            
            post_text += f"{'=' * 30}\n\n"
            
            # Описание
            post_text += f"📝 <b>Описание:</b>\n{post['description']}\n\n"
            
            # Локация
            if post.get('location'):
                post_text += f"{post['location']}\n"
            
            # Дата и контакты
            post_text += f"📅 <b>Дата:</b> {post['date']}\n"
            post_text += f"📞 <b>Контакт:</b> {post['contact']}\n\n"
            
            # Кнопки
            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.add(
                types.InlineKeyboardButton("📢 Открыть в канале", url=post['url']),
                types.InlineKeyboardButton("📱 Поделиться", switch_inline_query=post['title'][:50])
            )
            
            if len(post_text) > 1024:
                post_text = post_text[:1000] + "...\n\n📢 Полный текст в канале"
            
            # Отправляем с фото или без
            if post.get('photo_url'):
                try:
                    self.bot.send_photo(
                        chat_id,
                        post['photo_url'],
                        caption=post_text,
                        parse_mode="HTML",
                        reply_markup=markup
                    )
                    
                    # Дополнительные фото
                    if post.get('additional_photos'):
                        media_group = []
                        for photo_url in post['additional_photos'][:3]:
                            media_group.append(types.InputMediaPhoto(photo_url))
                        
                        if media_group:
                            self.bot.send_media_group(chat_id, media_group)
                    
                    return
                except Exception as e:
                    logger.error(f"❌ Ошибка отправки фото: {e}")
            
            # Отправляем текстом
            self.bot.send_message(
                chat_id,
                post_text,
                parse_mode="HTML",
                disable_web_page_preview=False,
                reply_markup=markup
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки поста: {e}")

    def send_category_posts(self, chat_id: int, category: PostCategory):
        """Отправляет посты определенной категории"""
        try:
            posts = self.parser.get_cached_posts(category)
            
            if not posts:
                category_names = {
                    PostCategory.CATS: "кошек",
                    PostCategory.DOGS: "собак", 
                    PostCategory.FREE_ITEMS: "бесплатных предметов",
                    PostCategory.LOST_PETS: "потерянных животных"
                }
                
                self.bot.send_message(
                    chat_id,
                    f"😿 Сейчас нет актуальных объявлений о {category_names[category]}.\n\n"
                    f"📢 Проверьте канал: {self.parser.channel_url}"
                )
                return
            
            # Заголовок категории
            category_headers = {
                PostCategory.CATS: "🐱 <b>КОШКИ ИЩУТ ДОМ</b>",
                PostCategory.DOGS: "🐶 <b>СОБАКИ ИЩУТ ДОМ</b>",
                PostCategory.FREE_ITEMS: "🎁 <b>ОТДАМ ДАРОМ</b>",
                PostCategory.LOST_PETS: "🔍 <b>ПОТЕРЯННЫЕ ЖИВОТНЫЕ</b>"
            }
            
            self.bot.send_message(
                chat_id,
                f"{category_headers[category]}\n\n"
                f"📢 Последние объявления из канала:\n"
                f"<a href='{self.parser.channel_url}'>Лапки-ручки Ялта</a>\n\n"
                f"📊 Найдено объявлений: <b>{len(posts)}</b>",
                parse_mode="HTML"
            )
            
            # Отправляем посты
            for i, post in enumerate(posts, 1):
                self.bot.send_message(
                    chat_id, 
                    f"📋 <b>Объявление {i} из {len(posts)}</b>",
                    parse_mode="HTML"
                )
                self.send_post(chat_id, post)
                time.sleep(1)  # Пауза между постами
            
            # Подсказки
            tips = {
                PostCategory.CATS: "🏠 <b>Хотите взять кошку?</b>\nСвяжитесь по контактам из объявления",
                PostCategory.DOGS: "🏠 <b>Хотите взять собаку?</b>\nСвяжитесь по контактам из объявления", 
                PostCategory.FREE_ITEMS: "🎁 <b>Нужны предметы?</b>\nСвяжитесь с авторами объявлений",
                PostCategory.LOST_PETS: "🔍 <b>Видели животное?</b>\nОбязательно свяжитесь с владельцами!"
            }
            
            self.bot.send_message(
                chat_id,
                f"💡 <b>Полезная информация:</b>\n\n"
                f"{tips[category]}\n\n"
                f"📢 <b>Канал:</b> @Lapki_ruchki_Yalta_help\n"
                f"🤝 <b>Стать волонтером:</b> Напишите в канал",
                parse_mode="HTML"
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки постов категории {category}: {e}")
            self.bot.send_message(
                chat_id,
                f"⚠️ Ошибка загрузки объявлений\n\n"
                f"Попробуйте позже или посетите канал:\n"
                f"{self.parser.channel_url}"
            )

    def get_main_keyboard(self):
        """Главная клавиатура"""
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add("🐱 Кошки", "🐶 Собаки")
        markup.add("🎁 Отдам даром", "🔍 Потеряшки")
        markup.add("🏥 Стерилизация", "📞 Контакты")
        markup.add("ℹ️ О проекте")
        return markup
    
    def get_back_keyboard(self):
        """Клавиатура "Назад" """
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("🔙 Назад в меню")
        return markup
    
    def setup_handlers(self):
        """Обработчики сообщений"""
        
        @self.bot.message_handler(commands=['start'])
        def start_handler(message):
            self.stats["users"].add(message.from_user.id)
            self.stats["messages"] += 1
            
            welcome_text = """🌟 <b>Добро пожаловать в помощник по животным Ялты!</b>
            
🐾 Здесь вы найдете:

🐱 <b>Кошки</b> - пристройство кошек и котят
🐶 <b>Собаки</b> - пристройство собак и щенков  
🎁 <b>Отдам даром</b> - корм, аксессуары, лекарства
🔍 <b>Потеряшки</b> - потерянные и найденные животные

🏥 <b>Стерилизация</b> - информация о программах
📞 <b>Контакты</b> - связь с волонтерами
ℹ️ <b>О проекте</b> - наша деятельность

Выберите нужный раздел в меню ⬇️"""
            
            self.bot.send_message(
                message.chat.id, 
                welcome_text, 
                parse_mode="HTML",
                reply_markup=self.get_main_keyboard()
            )
        
        @self.bot.message_handler(commands=['update'])
        def update_handler(message):
            """Обновление постов (для админов)"""
            self.parser.posts_cache = {category.value: [] for category in PostCategory}
            self.parser.last_update = None
            self.bot.send_message(message.chat.id, "🔄 Обновляю все посты...")
            
            all_posts = self.parser.get_channel_posts()
            total = sum(len(posts) for posts in all_posts.values()) if isinstance(all_posts, dict) else 0
            
            self.bot.send_message(
                message.chat.id, 
                f"✅ Обновлено: {total} постов\n"
                f"🐱 Кошки: {len(all_posts.get('cats', []))}\n"
                f"🐶 Собаки: {len(all_posts.get('dogs', []))}\n"
                f"🎁 Отдам даром: {len(all_posts.get('free_items', []))}\n"
                f"🔍 Потеряшки: {len(all_posts.get('lost_pets', []))}"
            )
        
        @self.bot.message_handler(func=lambda m: True)
        def message_handler(message):
            self.stats["users"].add(message.from_user.id)
            self.stats["messages"] += 1
            
            text = message.text
            chat_id = message.chat.id
            
            try:
                if text == "🐱 Кошки":
                    self.bot.send_message(
                        chat_id,
                        "🐱 <b>Загружаю объявления о кошках...</b>\n\n"
                        "⏳ Это может занять несколько секунд",
                        parse_mode="HTML",
                        reply_markup=self.get_back_keyboard()
                    )
                    self.send_category_posts(chat_id, PostCategory.CATS)
                
                elif text == "🐶 Собаки":
                    self.bot.send_message(
                        chat_id,
                        "🐶 <b>Загружаю объявления о собаках...</b>\n\n"
                        "⏳ Это может занять несколько секунд",
                        parse_mode="HTML",
                        reply_markup=self.get_back_keyboard()
                    )
                    self.send_category_posts(chat_id, PostCategory.DOGS)
                
                elif text == "🎁 Отдам даром":
                    self.bot.send_message(
                        chat_id,
                        "🎁 <b>Загружаю объявления \"Отдам даром\"...</b>\n\n"
                        "⏳ Это может занять несколько секунд",
                        parse_mode="HTML",
                        reply_markup=self.get_back_keyboard()
                    )
                    self.send_category_posts(chat_id, PostCategory.FREE_ITEMS)
                
                elif text == "🔍 Потеряшки":
                    self.bot.send_message(
                        chat_id,
                        "🔍 <b>Загружаю объявления о потерянных животных...</b>\n\n"
                        "⏳ Это может занять несколько секунд",
                        parse_mode="HTML",
                        reply_markup=self.get_back_keyboard()
                    )
                    self.send_category_posts(chat_id, PostCategory.LOST_PETS)
                
                elif text == "🏥 Стерилизация":
                    sterilization_text = """🏥 <b>ПРОГРАММА СТЕРИЛИЗАЦИИ</b>

🎯 <b>Цель программы:</b>
Контроль численности бездомных животных

💰 <b>Стоимость:</b>
🔹 Кошки: 1500-2000 руб
🔹 Собаки: 2500-4000 руб
🔹 <b>Льготы:</b> Пенсионерам скидка 20%

📋 <b>Что входит:</b>
✅ Операция стерилизации/кастрации
✅ Обезболивание
✅ Антибиотики
✅ Послеоперационный уход

🏥 <b>Партнерские клиники:</b>
🔹 "Айболит": +7 978 144-90-70
🔹 "ВетМир": +7 978 555-33-22
🔹 "Доктор Зоо": +7 978 777-88-99

📞 <b>Записаться:</b>
Координатор программы: +7 978 144-90-70

💡 <b>Важно:</b>
Запись ведется заранее, места ограничены"""
                    
                    self.bot.send_message(
                        chat_id, 
                        sterilization_text, 
                        parse_mode="HTML",
                        reply_markup=self.get_back_keyboard()
                    )
                
                elif text == "📞 Контакты":
                    contacts_text = """📞 <b>КОНТАКТНАЯ ИНФОРМАЦИЯ</b>

👥 <b>Координаторы программ:</b>
🐱 Пристройство кошек: +7 978 144-90-70
🐶 Пристройство собак: +7 978 888-77-66
🎁 Отдам даром: +7 978 333-22-11
🔍 Потеряшки: +7 978 999-88-77

🏥 <b>Ветеринарные клиники:</b>
🔹 "Айболит" - +7 978 144-90-70
   📍 ул. Московская, 12
🔹 "ВетМир" - +7 978 555-33-22  
   📍 ул. Кирова, 8
🔹 "Доктор Зоо" - +7 978 777-88-99
   📍 ул. Чехова, 15

🚑 <b>Экстренная помощь:</b>
Дежурный ветеринар: +7 978 911-00-11

📱 <b>Социальные сети:</b>
🔹 Telegram: @yalta_animals_help
🔹 Instagram: @yalta_street_animals
🔹 ВКонтакте: vk.com/yalta_pets

⏰ <b>Время работы:</b>
Ежедневно с 9:00 до 21:00"""
                    
                    self.bot.send_message(
                        chat_id, 
                        contacts_text, 
                        parse_mode="HTML",
                        reply_markup=self.get_back_keyboard()
                    )
                
                elif text == "ℹ️ О проекте":
                    about_text = """ℹ️ <b>О ПРОЕКТЕ "ЛАПКИ-РУЧКИ ЯЛТА"</b>

🎯 <b>Наша миссия:</b>
Помощь бездомным животным Ялты и окрестностей

📊 <b>Наши достижения за 2024-2025:</b>
🐱 Стерилизовано кошек: <b>650+</b>
🐶 Стерилизовано собак: <b>180+</b>
🏠 Пристроено животных: <b>320+</b>
👥 Активных волонтеров: <b>75+</b>

🎯 <b>Направления работы:</b>
🔹 Программа стерилизации
🔹 Пристройство животных
🔹 Лечение и реабилитация
🔹 Просветительская работа
🔹 Помощь владельцам в трудной ситуации

💰 <b>Поддержать проект:</b>
💳 Сбербанк: 2202 2020 1234 5678
💳 Тинькофф: 5536 9137 8765 4321
🪙 Криптовалюты: BTC, ETH (запросить реквизиты)

🤝 <b>Стать волонтером:</b>
📧 Email: volunteer@yaltapets.org
📱 Telegram: @volunteer_coordinator_yt
📞 Телефон: +7 978 100-20-30

🌟 <b>Партнеры:</b>
🏢 Администрация г. Ялта
🏥 Сеть ветклиник "Айболит"
🏪 Зоомагазины "ЗооЛэнд"
📺 Местные СМИ

💝 <b>Спасибо всем неравнодушным!</b>
Вместе мы делаем мир добрее! 🐾"""
                    
                    self.bot.send_message(
                        chat_id, 
                        about_text, 
                        parse_mode="HTML",
                        reply_markup=self.get_back_keyboard()
                    )
                
                elif text == "🔙 Назад в меню":
                    self.bot.send_message(
                        chat_id, 
                        "🏠 <b>Главное меню</b>\n\nВыберите нужный раздел:", 
                        parse_mode="HTML",
                        reply_markup=self.get_main_keyboard()
                    )
                
                else:
                    # Обработка текстовых запросов
                    if any(word in text.lower() for word in ['кот', 'кошк', 'котен']):
                        self.bot.send_message(
                            chat_id,
                            "🐱 Ищете информацию о кошках? Нажмите кнопку \"🐱 Кошки\"",
                            reply_markup=self.get_main_keyboard()
                        )
                    elif any(word in text.lower() for word in ['собак', 'щенок', 'пес']):
                        self.bot.send_message(
                            chat_id,
                            "🐶 Ищете информацию о собаках? Нажмите кнопку \"🐶 Собаки\"", 
                            reply_markup=self.get_main_keyboard()
                        )
                    elif any(word in text.lower() for word in ['потерял', 'найден', 'пропал']):
                        self.bot.send_message(
                            chat_id,
                            "🔍 Потеряли или нашли животное? Нажмите кнопку \"🔍 Потеряшки\"",
                            reply_markup=self.get_main_keyboard()
                        )
                    elif any(word in text.lower() for word in ['отдам', 'даром', 'корм', 'лоток']):
                        self.bot.send_message(
                            chat_id,
                            "🎁 Хотите что-то отдать или найти? Нажмите кнопку \"🎁 Отдам даром\"",
                            reply_markup=self.get_main_keyboard()
                        )
                    else:
                        self.bot.send_message(
                            chat_id,
                            "❓ <b>Не понял ваш запрос</b>\n\n"
                            "Используйте кнопки меню для навигации\n"
                            "Или введите /start для возврата в главное меню",
                            parse_mode="HTML",
                            reply_markup=self.get_main_keyboard()
                        )
                    
            except Exception as e:
                logger.error(f"❌ Ошибка обработки сообщения: {e}")
                self.bot.send_message(
                    chat_id, 
                    "⚠️ Произошла ошибка. Попробуйте /start",
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
            all_posts = self.parser.get_cached_posts()
            total_posts = sum(len(posts) for posts in all_posts.values()) if isinstance(all_posts, dict) else 0
            
            return jsonify({
                "status": "🤖 Enhanced Pet Bot Running",
                "time": datetime.now().strftime('%H:%M:%S %d.%m.%Y'),
                "users": len(self.stats["users"]),
                "messages": self.stats["messages"],
                "total_posts": total_posts,
                "categories": {
                    "cats": len(all_posts.get('cats', [])),
                    "dogs": len(all_posts.get('dogs', [])), 
                    "free_items": len(all_posts.get('free_items', [])),
                    "lost_pets": len(all_posts.get('lost_pets', []))
                },
                "channel": self.parser.channel_url,
                "last_update": self.parser.last_update.strftime('%H:%M:%S %d.%m.%Y') if self.parser.last_update else "Never"
            })
        
        @self.app.route('/posts')
        def posts_api():
            try:
                all_posts = self.parser.get_cached_posts()
                return jsonify({
                    "status": "ok",
                    "data": all_posts,
                    "channel": self.parser.channel_url,
                    "last_update": self.parser.last_update.isoformat() if self.parser.last_update else None
                })
            except Exception as e:
                return jsonify({"status": "error", "message": str(e)}), 500
        
        @self.app.route('/posts/<category>')
        def category_posts_api(category):
            try:
                category_map = {
                    'cats': PostCategory.CATS,
                    'dogs': PostCategory.DOGS,
                    'free': PostCategory.FREE_ITEMS,
                    'lost': PostCategory.LOST_PETS
                }
                
                if category not in category_map:
                    return jsonify({"status": "error", "message": "Invalid category"}), 400
                
                posts = self.parser.get_cached_posts(category_map[category])
                return jsonify({
                    "status": "ok",
                    "category": category,
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
                logger.info(f"✅ Webhook установлен: {full_url}")
                return True
            else:
                logger.error("❌ Не удалось установить webhook")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка установки webhook: {e}")
            return False
    
    def run(self):
        """Запуск расширенного бота"""
        logger.info("🚀 Запуск Enhanced Pet Bot...")
        
        # Предзагрузка постов всех категорий
        try:
            all_posts = self.parser.get_cached_posts()
            total = sum(len(posts) for posts in all_posts.values()) if isinstance(all_posts, dict) else 0
            logger.info(f"✅ Предзагружено {total} постов всех категорий")
            
            for category in PostCategory:
                count = len(all_posts.get(category.value, []))
                emoji = self.parser.get_category_emoji(category)
                logger.info(f"  {emoji} {category.value}: {count} постов")
                
        except Exception as e:
            logger.warning(f"⚠️ Ошибка предзагрузки: {e}")
        
        # Запуск бота
        if self.setup_webhook():
            logger.info(f"🌐 Запуск Flask сервера на порту {self.port}")
            self.app.run(host='0.0.0.0', port=self.port)
        else:
            logger.warning("🔄 Запуск в polling режиме...")
            try:
                self.bot.polling(none_stop=True, interval=1, timeout=60)
            except Exception as e:
                logger.error(f"🚨 Ошибка polling: {e}")

if __name__ == "__main__":
    try:
        bot = PetBotEnhanced()
        bot.run()
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"🚨 Критическая ошибка: {e}")
        exit(1)
