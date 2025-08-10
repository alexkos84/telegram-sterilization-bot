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
import concurrent.futures
from threading import Lock

# 🔧 Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MultiChannelParser:
    """Парсер множественных каналов с животными"""
    
    def __init__(self):
        # 📋 Список каналов для парсинга
        self.channels = [
            {
                'username': 'Котики_Ялта',
                'url': 'https://t.me/cats_yalta',
                'type': 'cats',  # кошки
                'priority': 1  # приоритет (1 - высокий)
            },
            {
                'username': 'dogs_yalta_official',
                'url': 'https://t.me/dogs_yalta_official', 
                'type': 'dogs',  # собаки
                'priority': 1
            },
            {
                'username': 'yalta_animals_help',
                'url': 'https://t.me/yalta_animals_help',
                'type': 'all',  # все животные
                'priority': 2
            },
            {
                'username': 'crimea_pets_adoption',
                'url': 'https://t.me/crimea_pets_adoption',
                'type': 'all',
                'priority': 2
            },
            {
                'username': 'yalta_street_cats',
                'url': 'https://t.me/yalta_street_cats',
                'type': 'cats',
                'priority': 3
            }
        ]
        
        self.posts_cache = {
            'cats': [],
            'dogs': [],
            'all': []
        }
        self.last_update = {}
        self.update_lock = Lock()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
    
    def parse_single_channel(self, channel: Dict) -> List[Dict]:
        """Парсит один канал"""
        try:
            web_url = f'https://t.me/s/{channel["username"]}'
            logger.info(f"🌐 Парсинг канала: {channel['username']} ({channel['type']})")
            
            response = self.session.get(web_url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            message_divs = soup.find_all('div', class_='tgme_widget_message')
            
            posts = []
            for div in message_divs[:10]:  # Увеличили лимит для каждого канала
                post_data = self.parse_message_div(div, channel)
                if post_data and self.is_animal_related(post_data.get('text', '')):
                    # Определяем тип животного если канал смешанный
                    if channel['type'] == 'all':
                        post_data['type'] = self.detect_animal_type(post_data.get('text', ''))
                    else:
                        post_data['type'] = channel['type']
                    
                    post_data['source_channel'] = channel['username']
                    post_data['channel_priority'] = channel['priority']
                    posts.append(post_data)
            
            logger.info(f"✅ {channel['username']}: найдено {len(posts)} постов")
            return posts
            
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга {channel['username']}: {e}")
            return []
    
    def get_channel_posts(self, channel_type: str = 'all', limit: int = 6) -> List[Dict]:
        """Получает посты из всех каналов параллельно"""
        try:
            all_posts = []
            
            # Определяем какие каналы парсить
            channels_to_parse = []
            if channel_type == 'all':
                channels_to_parse = self.channels
            else:
                channels_to_parse = [c for c in self.channels 
                                   if c['type'] == channel_type or c['type'] == 'all']
            
            logger.info(f"🔍 Парсинг {len(channels_to_parse)} каналов для типа '{channel_type}'")
            
            # Параллельный парсинг каналов
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                future_to_channel = {
                    executor.submit(self.parse_single_channel, channel): channel 
                    for channel in channels_to_parse
                }
                
                for future in concurrent.futures.as_completed(future_to_channel):
                    channel = future_to_channel[future]
                    try:
                        posts = future.result()
                        all_posts.extend(posts)
                    except Exception as e:
                        logger.error(f"❌ Ошибка получения постов из {channel['username']}: {e}")
            
            # Фильтруем и сортируем посты
            filtered_posts = self.filter_and_sort_posts(all_posts, channel_type, limit)
            
            # Кэшируем результаты
            with self.update_lock:
                self.posts_cache[channel_type] = filtered_posts
                self.last_update[channel_type] = datetime.now()
            
            logger.info(f"✅ Всего получено {len(filtered_posts)} постов типа '{channel_type}'")
            return filtered_posts
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка парсинга: {e}")
            return self.get_mock_posts(channel_type)
    
    def filter_and_sort_posts(self, posts: List[Dict], channel_type: str, limit: int) -> List[Dict]:
        """Фильтрует, дедуплицирует и сортирует посты"""
        if not posts:
            return []
        
        # Фильтрация по типу
        if channel_type != 'all':
            posts = [p for p in posts if p.get('type') == channel_type]
        
        # Дедупликация по тексту (простая)
        seen_texts = set()
        unique_posts = []
        for post in posts:
            text_hash = hash(post.get('text', '')[:100])  # Хэш первых 100 символов
            if text_hash not in seen_texts:
                seen_texts.add(text_hash)
                unique_posts.append(post)
        
        # Сортировка по приоритету канала и времени
        unique_posts.sort(key=lambda x: (
            x.get('channel_priority', 999),  # Приоритет канала
            -self.extract_timestamp(x.get('date', ''))  # Время (новые сначала)
        ))
        
        # Приоритизируем посты с фото
        posts_with_photos = [p for p in unique_posts if p.get('has_photo')]
        posts_without_photos = [p for p in unique_posts if not p.get('has_photo')]
        
        result = posts_with_photos + posts_without_photos
        return result[:limit]
    
    def extract_timestamp(self, date_str: str) -> int:
        """Извлекает timestamp из строки даты для сортировки"""
        try:
            if 'Недавно' in date_str:
                return int(time.time())
            # Попытка парсинга формата "03.08.2025 14:30"
            dt = datetime.strptime(date_str, '%d.%m.%Y %H:%M')
            return int(dt.timestamp())
        except:
            return 0
    
    def detect_animal_type(self, text: str) -> str:
        """Определяет тип животного (кошка/собака) по тексту"""
        text_lower = text.lower()
        
        # Расширенные ключевые слова
        cat_keywords = [
            'кот', 'кошк', 'котен', 'котик', 'мурз', 'мяу', 'киска', 'кися',
            'персидск', 'сиамск', 'британск', 'шотландск', 'мейн-кун'
        ]
        dog_keywords = [
            'собак', 'щен', 'пес', 'гав', 'лайк', 'овчарк', 'дворняж', 'метис',
            'хаски', 'лабрадор', 'ретривер', 'терьер', 'шпиц', 'бульдог'
        ]
        
        cat_count = sum(1 for word in cat_keywords if word in text_lower)
        dog_count = sum(1 for word in dog_keywords if word in text_lower)
        
        if cat_count > dog_count:
            return 'cats'
        elif dog_count > cat_count:
            return 'dogs'
        else:
            # Если неясно, проверяем длину слов (коты чаще упоминаются короче)
            if any(word in text_lower for word in ['кот', 'мяу']):
                return 'cats'
            return 'dogs'
    
    def parse_message_div(self, div, channel) -> Optional[Dict]:
        """Парсит отдельный пост"""
        try:
            # ID поста
            post_id = div.get('data-post', '').split('/')[-1] or str(int(time.time()))
            
            # Текст поста
            text_div = div.find('div', class_='tgme_widget_message_text')
            text = text_div.get_text(strip=True) if text_div else ""
            
            if not text:
                return None
            
            # Дата
            date_elem = div.find('time', datetime=True)
            date_str = self.parse_date(date_elem)
            
            # Фото
            photo_url = self.extract_photo_url(div)
            
            # Дополнительная информация
            title = self.extract_title(text)
            description = self.extract_description(text)
            contact = self.extract_contact(text)
            
            return {
                'id': f"{channel['username']}_{post_id}",
                'text': text,
                'date': date_str,
                'url': f"{channel['url']}/{post_id}",
                'title': title,
                'description': description,
                'contact': contact,
                'photo_url': photo_url,
                'has_photo': bool(photo_url),
                'type': channel.get('type', 'all'),
                'source_channel': channel['username']
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга поста: {e}")
            return None
    
    def parse_date(self, date_elem) -> str:
        """Парсит дату из элемента"""
        if not date_elem:
            return "Недавно"
        
        try:
            dt = datetime.fromisoformat(date_elem['datetime'].replace('Z', '+00:00'))
            return dt.strftime('%d.%m.%Y %H:%M')
        except:
            return "Недавно"
    
    def extract_photo_url(self, div) -> Optional[str]:
        """Извлекает URL фото из поста"""
        # Основное фото
        photo_wrap = div.find('a', class_='tgme_widget_message_photo_wrap')
        if photo_wrap and photo_wrap.get('style'):
            match = re.search(r"background-image:url\('(.*?)'\)", photo_wrap['style'])
            if match:
                return match.group(1)
        
        # Альтернативные способы поиска фото
        img_tags = div.find_all('img')
        for img in img_tags:
            src = img.get('src', '')
            if 'photo' in src or 'image' in src:
                return src
        
        return None
    
    def extract_title(self, text: str) -> str:
        """Извлекает заголовок из текста поста"""
        lines = text.split('\n')
        for line in lines[:3]:
            line = line.strip()
            if line and len(line) > 10:
                # Очистка от эмодзи и лишних символов
                title = re.sub(r'[^\w\s\-\.,!?а-яёА-ЯЁ]', '', line)
                if len(title) > 60:
                    title = title[:60] + "..."
                return title or "Животное ищет дом"
        
        # Если не нашли хороший заголовок, генерируем базовый
        if any(word in text.lower() for word in ['кот', 'кошк', 'котен']):
            return "🐱 Кошка ищет дом"
        elif any(word in text.lower() for word in ['собак', 'щен', 'пес']):
            return "🐶 Собака ищет дом"
        else:
            return "🐾 Животное ищет дом"
    
    def extract_description(self, text: str) -> str:
        """Извлекает описание из текста"""
        # Удаляем контакты и ссылки
        clean_text = re.sub(r'@\w+|https?://\S+|\+?\d[\d\s\-\(\)]+', '', text)
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        
        if len(clean_text) > 250:
            return clean_text[:250] + "..."
        return clean_text
    
    def extract_contact(self, text: str) -> str:
        """Извлекает контактную информацию"""
        # Телефоны
        phone_pattern = r'\+?[78][\s\-]?\(?9\d{2}\)?\s?[\d\s\-]{7,10}'
        phones = re.findall(phone_pattern, text)
        
        # Юзернеймы
        username_pattern = r'@\w+'
        usernames = re.findall(username_pattern, text)
        
        contacts = []
        if phones:
            contacts.extend(phones[:2])  # Берем до 2 телефонов
        if usernames:
            contacts.extend(usernames[:2])  # Берем до 2 юзернеймов
        
        return ' • '.join(contacts) if contacts else "См. в канале"
    
    def is_animal_related(self, text: str) -> bool:
        """Проверяет, относится ли пост к животным"""
        animal_keywords = [
            # Животные
            'кот', 'кошк', 'котен', 'котик', 'киса',
            'собак', 'щен', 'пес', 'песик', 'дворняж',
            'животн', 'питомец', 'зверь',
            # Действия
            'пристрой', 'дом', 'семь', 'хозя', 'усынов', 'взять',
            'найден', 'потеря', 'ищет', 'ищу', 'нужен',
            # Уход
            'стерил', 'прививк', 'лечени', 'ветеринар',
            'корм', 'уход', 'содержан'
        ]
        
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in animal_keywords)
    
    def get_cached_posts(self, channel_type: str = 'all') -> List[Dict]:
        """Возвращает кэшированные или обновленные посты"""
        with self.update_lock:
            last_update = self.last_update.get(channel_type)
            
            # Обновляем если кэш пустой или старый (30 минут)
            if (not last_update or 
                (datetime.now() - last_update).seconds > 1800 or
                not self.posts_cache.get(channel_type)):
                
                logger.info(f"🔄 Обновление кэша для типа '{channel_type}'")
                try:
                    return self.get_channel_posts(channel_type)
                except Exception as e:
                    logger.error(f"❌ Ошибка обновления кэша: {e}")
                    return self.posts_cache.get(channel_type, []) or self.get_mock_posts(channel_type)
            
            return self.posts_cache.get(channel_type, [])
    
    def get_mock_posts(self, channel_type: str = 'cats') -> List[Dict]:
        """Возвращает тестовые посты"""
        base_posts = {
            'cats': [
                {
                    'id': 'mock_cat_1',
                    'title': '🐱 Рыжий котенок Мурзик ищет дом',
                    'description': 'Возраст: 2 месяца, мальчик, рыжий окрас. Здоров, привит, игривый и ласковый.',
                    'date': datetime.now().strftime('%d.%m.%Y %H:%M'),
                    'url': 'https://t.me/cats_yalta/1001',
                    'contact': '@yalta_cats • +7 978 123-45-67',
                    'photo_url': 'https://via.placeholder.com/600x400/FF6B35/FFFFFF?text=🐱+Котенок+Мурзик',
                    'has_photo': True,
                    'type': 'cats',
                    'source_channel': 'Котики_Ялта'
                },
                {
                    'id': 'mock_cat_2', 
                    'title': '🐱 Трехцветная кошечка Маша',
                    'description': 'Возраст: 1 год, девочка, стерилизована, привита. Спокойная, ласковая.',
                    'date': datetime.now().strftime('%d.%m.%Y %H:%M'),
                    'url': 'https://t.me/yalta_animals_help/2002',
                    'contact': '@animal_volunteer • +7 978 234-56-78',
                    'photo_url': 'https://via.placeholder.com/600x400/8B4513/FFFFFF?text=🐱+Кошечка+Маша',
                    'has_photo': True,
                    'type': 'cats',
                    'source_channel': 'yalta_animals_help'
                }
            ],
            'dogs': [
                {
                    'id': 'mock_dog_1',
                    'title': '🐶 Щенок Бобик ищет семью',
                    'description': 'Возраст: 4 месяца, мальчик, черно-белый окрас. Здоров, активный, дружелюбный.',
                    'date': datetime.now().strftime('%d.%m.%Y %H:%M'),
                    'url': 'https://t.me/dogs_yalta_official/3001',
                    'contact': '@dog_volunteers • +7 978 345-67-89',
                    'photo_url': 'https://via.placeholder.com/600x400/4682B4/FFFFFF?text=🐶+Щенок+Бобик',
                    'has_photo': True,
                    'type': 'dogs',
                    'source_channel': 'dogs_yalta_official'
                }
            ]
        }
        
        if channel_type == 'all':
            return base_posts['cats'] + base_posts['dogs']
        
        return base_posts.get(channel_type, base_posts['cats'])
    
    def get_stats(self) -> Dict:
        """Возвращает статистику парсера"""
        return {
            'channels_total': len(self.channels),
            'channels_active': len([c for c in self.channels if c['priority'] <= 2]),
            'cache_status': {
                'cats': len(self.posts_cache.get('cats', [])),
                'dogs': len(self.posts_cache.get('dogs', [])),
                'all': len(self.posts_cache.get('all', []))
            },
            'last_updates': {
                k: v.strftime('%H:%M:%S') if v else 'Не обновлялось' 
                for k, v in self.last_update.items()
            }
        }

# Обновляем основной класс бота
class CatBotWithPhotos:
    """Бот с поддержкой множественных каналов"""
    
    def __init__(self):
        self.token = os.environ.get('TOKEN')
        if not self.token:
            logger.error("❌ TOKEN не найден!")
            exit(1)
        
        self.bot = telebot.TeleBot(self.token)
        self.parser = MultiChannelParser()  # Используем новый парсер
        self.app = Flask(__name__)
        self.port = int(os.environ.get('PORT', 8080))
        self.webhook_url = os.environ.get('WEBHOOK_URL')
        self.stats = {"users": set(), "messages": 0}
        
        self.setup_handlers()
        self.setup_routes()
    
    def send_post(self, chat_id: int, post: Dict):
        """Отправляет один пост с указанием источника"""
        try:
            emoji = '🐱' if post['type'] == 'cats' else '🐶'
            source = post.get('source_channel', 'Неизвестный канал')
            
            post_text = (
                f"{emoji} <b>{post['title']}</b>\n\n"
                f"{post['description']}\n\n"
                f"📅 {post['date']}\n"
                f"📞 {post['contact']}\n"
                f"📺 Источник: {source}\n"
                f"🔗 <a href='{post['url']}'>Открыть пост</a>"
            )
            
            if len(post_text) > 1024:
                post_text = post_text[:1000] + "..."
            
            # Пытаемся отправить с фото
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
            
            # Отправляем текстом
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
        """Отправляет все посты из всех каналов"""
        try:
            posts = self.parser.get_cached_posts(animal_type)
            
            if not posts:
                channels_text = '\n'.join([
                    f"• {c['url']}" for c in self.parser.channels 
                    if c['type'] == animal_type or c['type'] == 'all'
                ])
                
                self.bot.send_message(
                    chat_id,
                    f"😿 Сейчас нет актуальных объявлений.\n\n"
                    f"📢 Проверьте каналы:\n{channels_text}"
                )
                return
            
            # Заголовок с информацией о каналах
            stats = self.parser.get_stats()
            header_text = (
                f"{'🐱 КОШКИ' if animal_type == 'cats' else '🐶 СОБАКИ'} ИЩУТ ДОМ\n\n"
                f"📊 Найдено объявлений: {len(posts)}\n"
                f"📺 Активных каналов: {stats['channels_active']}\n"
                f"🔄 Обновлено: {stats['last_updates'].get(animal_type, 'Недавно')}"
            )
            
            self.bot.send_message(chat_id, header_text, parse_mode="HTML")
            
            # Отправляем посты
            for i, post in enumerate(posts):
                self.send_post(chat_id, post)
                time.sleep(0.7)  # Небольшая пауза между постами
                
                # Промежуточное сообщение каждые 3 поста
                if i > 0 and (i + 1) % 3 == 0 and i < len(posts) - 1:
                    remaining = len(posts) - i - 1
                    self.bot.send_message(
                        chat_id, 
                        f"📍 Показано {i + 1} из {len(posts)} объявлений\n"
                        f"⏳ Загружаем еще {remaining}...",
                        parse_mode="HTML"
                    )
                    time.sleep(1)
            
            # Итоговое сообщение
            channels_links = '\n'.join([
                f"• <a href='{c['url']}'>{c['username']}</a>" 
                for c in self.parser.channels 
                if c['type'] == animal_type or c['type'] == 'all'
            ])
            
            self.bot.send_message(
                chat_id,
                f"✅ <b>Показаны все актуальные объявления!</b>\n\n"
                f"💡 <b>Как помочь:</b>\n"
                f"🏠 <b>Взять {'кошку' if animal_type == 'cats' else 'собаку'}:</b> "
                f"Свяжитесь по контактам из объявления\n\n"
                f"📢 <b>Наши каналы:</b>\n{channels_links}\n\n"
                f"🤝 <b>Стать волонтером:</b> Напишите в любой канал",
                parse_mode="HTML"
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки постов: {e}")
            self.bot.send_message(
                chat_id,
                f"⚠️ Ошибка загрузки объявлений\n\n"
                f"Попробуйте позже или посетите каналы напрямую."
            )

    # Остальные методы остаются без изменений...
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
            
            welcome_text = """👋 <b>Добро пожаловать!</b>

🐾 Помощник по уличным животным Ялты
📺 Мониторим множественные каналы

Выберите раздел:
🏥 <b>Стерилизация</b> - информация о программах
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
            """Принудительное обновление постов"""
            try:
                self.bot.send_message(message.chat.id, "🔄 Обновляю посты из всех каналов...")
                
                # Очищаем кэш
                with self.parser.update_lock:
                    self.parser.posts_cache = {'cats': [], 'dogs': [], 'all': []}
                    self.parser.last_update = {}
                
                # Обновляем все типы
                cats_posts = self.parser.get_channel_posts('cats')
                dogs_posts = self.parser.get_channel_posts('dogs')
                
                stats = self.parser.get_stats()
                
                result_text = (
                    f"✅ <b>Обновление завершено!</b>\n\n"
                    f"🐱 Кошки: {len(cats_posts)} объявлений\n"
                    f"🐶 Собаки: {len(dogs_posts)} объявлений\n"
                    f"📺 Каналов проверено: {stats['channels_total']}\n"
                    f"🔄 Время: {datetime.now().strftime('%H:%M:%S')}"
                )
                
                self.bot.send_message(message.chat.id, result_text, parse_mode="HTML")
                
            except Exception as e:
                logger.error(f"❌ Ошибка обновления: {e}")
                self.bot.send_message(
                    message.chat.id, 
                    f"❌ Ошибка обновления: {str(e)}\n\nПопробуйте позже."
                )
        
        @self.bot.message_handler(commands=['stats'])
        def stats_handler(message):
            """Статистика парсера"""
            try:
                stats = self.parser.get_stats()
                
                stats_text = (
                    f"📊 <b>СТАТИСТИКА КАНАЛОВ</b>\n\n"
                    f"📺 Всего каналов: {stats['channels_total']}\n"
                    f"✅ Активных: {stats['channels_active']}\n\n"
                    f"📋 <b>Кэш объявлений:</b>\n"
                    f"🐱 Кошки: {stats['cache_status']['cats']}\n"
                    f"🐶 Собаки: {stats['cache_status']['dogs']}\n"
                    f"🔄 Общий: {stats['cache_status']['all']}\n\n"
                    f"⏰ <b>Последние обновления:</b>\n"
                )
                
                for type_name, time_str in stats['last_updates'].items():
                    emoji = '🐱' if type_name == 'cats' else ('🐶' if type_name == 'dogs' else '🔄')
                    stats_text += f"{emoji} {type_name}: {time_str}\n"
                
                # Список каналов
                stats_text += "\n📺 <b>Отслеживаемые каналы:</b>\n"
                for i, channel in enumerate(self.parser.channels, 1):
                    priority_emoji = "⭐" * (4 - channel['priority'])
                    type_emoji = '🐱' if channel['type'] == 'cats' else ('🐶' if channel['type'] == 'dogs' else '🐾')
                    stats_text += f"{i}. {type_emoji} {channel['username']} {priority_emoji}\n"
                
                self.bot.send_message(message.chat.id, stats_text, parse_mode="HTML")
                
            except Exception as e:
                logger.error(f"❌ Ошибка получения статистики: {e}")
                self.bot.send_message(message.chat.id, "❌ Ошибка получения статистики")
        
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
                    stats = self.parser.get_stats()
                    info_text = f"""🏠 <b>Пристройство животных</b>

📺 Мониторим {stats['channels_active']} активных каналов
🔄 Обновление каждые 30 минут

Выберите действие:

🐱 <b>Кошки ищут дом</b>
Актуальные объявления из всех каналов

🐶 <b>Собаки ищут дом</b>
Актуальные объявления из всех каналов

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
                    channels_list = []
                    for channel in self.parser.channels:
                        type_name = {"cats": "кошки", "dogs": "собаки", "all": "все животные"}[channel['type']]
                        channels_list.append(f"• <a href='{channel['url']}'>{channel['username']}</a> ({type_name})")
                    
                    info_text = f"""📝 <b>Подать объявление</b>

📺 <b>Наши каналы:</b>
{chr(10).join(channels_list)}

✍️ <b>Как подать объявление:</b>
1️⃣ Выберите подходящий канал
2️⃣ Перейдите в канал
3️⃣ Свяжитесь с администраторами
4️⃣ Или используйте координаторов:
   • Общие вопросы: @yalta_animals_coordinator
   • Кошки: +7 978 144-90-70
   • Собаки: +7 978 000-00-02

📋 <b>Информация для объявления:</b>
🔹 Качественные фото животного
🔹 Возраст, пол, окрас, размер
🔹 Характер и особенности
🔹 Здоровье (прививки, стерилизация)
🔹 История (найден, от хозяев и т.д.)
🔹 Ваши контакты для связи

💡 <b>Советы:</b>
• Добавьте несколько фото
• Опишите характер подробно
• Укажите, подходит ли для семей с детьми
• Напишите о совместимости с другими животными"""
                    
                    self.bot.send_message(chat_id, info_text, parse_mode="HTML")
                
                elif text == "📞 Контакты":
                    contacts_text = """📞 <b>КОНТАКТЫ ВОЛОНТЕРОВ</b>

👥 <b>Основные координаторы:</b>
🔹 Общие вопросы: @yalta_animals_main
🔹 Кошки: +7 978 144-90-70
🔹 Собаки: +7 978 234-56-78
🔹 Экстренное лечение: +7 978 345-67-89

🏥 <b>Партнерские клиники:</b>
🔹 "Айболит": +7 978 456-78-90
🔹 "ВетМир": +7 978 567-89-01
🔹 "Зоолекарь": +7 978 678-90-12

📱 <b>Социальные сети:</b>
🔹 Instagram: @yalta_street_animals
🔹 ВКонтакте: vk.com/yalta_animals
🔹 Facebook: fb.com/yalta.animals.help

⏰ <b>Время работы:</b>
Координаторы: ежедневно 9:00-21:00
Экстренные случаи: круглосуточно"""
                    
                    self.bot.send_message(chat_id, contacts_text, parse_mode="HTML")
                
                elif text == "ℹ️ О проекте":
                    stats = self.parser.get_stats()
                    about_text = f"""ℹ️ <b>О ПРОЕКТЕ "ЛАПКИ-РУЧКИ ЯЛТА"</b>

🎯 <b>Наша миссия:</b>
Системная помощь бездомным животным Ялты через координацию волонтеров и информационную поддержку

📊 <b>Наши достижения за 2024-2025:</b>
🔹 Стерилизовано: 500+ кошек, 200+ собак
🔹 Пристроено в семьи: 300+ котят, 150+ щенков
🔹 Вылечено: 400+ животных
🔹 Активных волонтеров: 50+
🔹 Отслеживаем каналов: {stats['channels_total']}

🤝 <b>Как мы работаем:</b>
• Мониторинг множественных каналов
• Координация между волонтерами
• Помощь в поиске домов
• Организация лечения и стерилизации
• Информационная поддержка

💰 <b>Поддержать проект:</b>
Сбербанк: 2202 2020 1234 5678
ЮMoney: 4100 1234 5678 9012
PayPal: donate@yalta-animals.org

🤝 <b>Стать волонтером:</b>
• Временная передержка
• Помощь в транспортировке  
• Фотосъемка для объявлений
• Поиск хозяев в соцсетях
• Сбор средств на лечение

Пишите: @yalta_volunteer_coordinator"""
                    
                    self.bot.send_message(chat_id, about_text, parse_mode="HTML")
                
                elif text == "🔙 Назад":
                    self.bot.send_message(
                        chat_id, 
                        "🏠 Главное меню:", 
                        reply_markup=self.get_main_keyboard()
                    )
                
                else:
                    help_text = """❓ <b>Доступные команды:</b>

🔘 Используйте кнопки меню для навигации

📱 <b>Дополнительные команды:</b>
/start - главное меню
/update - обновить объявления  
/stats - статистика каналов

💡 <b>Подсказка:</b>
Выберите нужный раздел из меню ниже ⬇️"""
                    
                    self.bot.send_message(
                        chat_id,
                        help_text,
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
                logger.error(f"❌ Webhook ошибка: {e}")
                return 'Internal error', 500
        
        @self.app.route('/')
        def home():
            stats = self.parser.get_stats()
            return jsonify({
                "status": "🤖 Multi-Channel Animal Bot Running",
                "time": datetime.now().strftime('%d.%m.%Y %H:%M:%S'),
                "bot_stats": {
                    "users": len(self.stats["users"]),
                    "messages": self.stats["messages"]
                },
                "parser_stats": stats,
                "channels": [
                    {
                        "name": c['username'],
                        "url": c['url'],
                        "type": c['type'],
                        "priority": c['priority']
                    } for c in self.parser.channels
                ]
            })
        
        @self.app.route('/posts')
        def posts_api():
            """API для получения всех постов"""
            try:
                animal_type = request.args.get('type', 'all')
                limit = int(request.args.get('limit', 10))
                
                posts = self.parser.get_cached_posts(animal_type)[:limit]
                stats = self.parser.get_stats()
                
                return jsonify({
                    "status": "ok",
                    "type": animal_type,
                    "count": len(posts),
                    "total_channels": stats['channels_total'],
                    "posts": posts,
                    "cache_info": stats['cache_status'],
                    "last_update": stats['last_updates'].get(animal_type, 'Never')
                })
            except Exception as e:
                logger.error(f"❌ Ошибка API постов: {e}")
                return jsonify({"status": "error", "message": str(e)}), 500
        
        @self.app.route('/channels')
        def channels_api():
            """API информации о каналах"""
            try:
                return jsonify({
                    "status": "ok",
                    "channels": [
                        {
                            "username": c['username'],
                            "url": c['url'],
                            "type": c['type'],
                            "priority": c['priority']
                        } for c in self.parser.channels
                    ],
                    "stats": self.parser.get_stats()
                })
            except Exception as e:
                return jsonify({"status": "error", "message": str(e)}), 500
        
        @self.app.route('/force-update')
        def force_update():
            """Принудительное обновление через API"""
            try:
                # Очистка кэша
                with self.parser.update_lock:
                    self.parser.posts_cache = {'cats': [], 'dogs': [], 'all': []}
                    self.parser.last_update = {}
                
                # Обновление
                cats_posts = self.parser.get_channel_posts('cats', limit=5)
                dogs_posts = self.parser.get_channel_posts('dogs', limit=5)
                
                return jsonify({
                    "status": "ok",
                    "message": "Update completed",
                    "results": {
                        "cats": len(cats_posts),
                        "dogs": len(dogs_posts)
                    },
                    "timestamp": datetime.now().isoformat()
                })
            except Exception as e:
                logger.error(f"❌ Ошибка принудительного обновления: {e}")
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
            logger.error(f"❌ Ошибка настройки webhook: {e}")
            return False
    
    def run(self):
        """Запуск многоканального бота"""
        logger.info("🚀 Запуск Multi-Channel Animal Bot...")
        
        # Информация о каналах
        logger.info(f"📺 Настроено каналов: {len(self.parser.channels)}")
        for channel in self.parser.channels:
            logger.info(f"   • {channel['username']} ({channel['type']}) - приоритет {channel['priority']}")
        
        # Предварительная загрузка постов
        try:
            logger.info("🔄 Предзагрузка постов...")
            cats_posts = self.parser.get_cached_posts('cats')
            dogs_posts = self.parser.get_cached_posts('dogs')
            logger.info(f"✅ Предзагружено: 🐱{len(cats_posts)} кошек, 🐶{len(dogs_posts)} собак")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка предзагрузки: {e}")
        
        # Запуск
        if self.setup_webhook():
            logger.info(f"🌐 Сервер запущен на порту {self.port}")
            self.app.run(host='0.0.0.0', port=self.port)
        else:
            logger.info("📱 Запуск в режиме polling...")
            self.bot.polling(none_stop=True, interval=1)

if __name__ == "__main__":
    # Создание необходимых папок и файлов
    os.makedirs('assets/images', exist_ok=True)
    
    # Создание файлов с информацией о стерилизации (если их нет)
    if not os.path.exists('assets/free_text.html'):
        with open('assets/free_text.html', 'w', encoding='utf-8') as f:
            f.write("""<b>🆓 БЕСПЛАТНАЯ СТЕРИЛИЗАЦИЯ</b>

🏥 <b>Программы помощи:</b>
🔹 Муниципальная программа г. Ялта
🔹 Благотворительный фонд "Лапки-ручки"
🔹 Программа "Добрые сердца"

📋 <b>Кто может получить:</b>
✅ Владельцы бездомных животных
✅ Малоимущие семьи (справка о доходах)
✅ Пенсионеры (удостоверение)
✅ Волонтеры по направлению координаторов

📞 <b>Подача заявок:</b>
🔹 Координатор программы: +7 978 123-45-10
🔹 Клиника "Айболит": +7 978 123-45-11
🔹 Онлайн заявка: yalta-animals.org/free

📍 <b>Где проводится:</b>
• Ветклиника "Айболит" - ул. Кирова, 15
• Ветклиника "Добрый доктор" - ул. Ленина, 23

⏰ <b>График работы:</b>
Понедельник-пятница: 9:00-18:00
Суббота: 9:00-14:00

📋 <b>Необходимые документы:</b>
• Паспорт заявителя
• Справка о доходах (для льготников)
• Ветпаспорт животного (если есть)""")

    if not os.path.exists('assets/paid_text.html'):
        with open('assets/paid_text.html', 'w', encoding='utf-8') as f:
            f.write("""<b>💰 ПЛАТНАЯ СТЕРИЛИЗАЦИЯ</b>

🏥 <b>Ветеринарные клиники:</b>

🔹 <b>"Айболит"</b> - ул. Кирова, 15
   • Кошки: от 2800₽ • Собаки: от 4500₽
   • Телефон: +7 978 123-45-12
   
🔹 <b>"ВетМир"</b> - ул. Ленина, 45  
   • Кошки: от 2500₽ • Собаки: от 4200₽
   • Телефон: +7 978 123-45-13

🔹 <b>"Зоолекарь"</b> - ул. Садовая, 8
   • Кошки: от 3000₽ • Собаки: от 4800₽
   • Телефон: +7 978 123-45-14

🌟 <b>Включено в стоимость:</b>
✔️ Предоперационный осмотр
✔️ Операция полостная
✔️ Общий наркоз
✔️ Послеоперационная обработка
✔️ Консультации в течение недели

💊 <b>Дополнительно оплачивается:</b>
• Анализы крови: от 800₽
• Кардиообследование: от 600₽  
• Послеоперационная попона: 300₽
• Обезболивающие препараты: от 400₽

💡 <b>Скидки и акции:</b>
🔸 Волонтерам нашего проекта - 20%
🔸 При стерилизации 2+ животных - 15%
🔸 Пенсионерам - 10%
🔸 Акция "Ответственный хозяин" - до 25%

📞 <b>Запись на операцию:</b>
Звоните заранее, запись ведется на 1-2 недели вперед""")

    # Запуск бота
    try:
        bot = CatBotWithPhotos()
        bot.run()
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"🚨 Критическая ошибка запуска: {e}")
        raise
