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

# Настройка логирования
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
                'title': 'Собаки Ялта (канал)'
            },
            {
                'username': 'dogs_yalta_group',
                'url': 'https://t.me/dogs_yalta_group',
                'type': 'dogs',
                'title': 'Собаки Ялта (группа)'
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
                    if post_data and self.is_animal_related(post_data.get('text', ''), channel_type):
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
                return title or ("Собака ищет дом" if animal_type == 'dogs' else "Котик ищет дом")
        return "Собака ищет дом" if animal_type == 'dogs' else "Котик ищет дом"
    
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
    
    def is_animal_related(self, text: str, animal_type: str = 'all') -> bool:
        """Проверяет, относится ли пост к животным"""
        if animal_type == 'cats':
            keywords = [
                'кот', 'кошк', 'котен', 'котик', 'мурз', 'мяу',
                'пристрой', 'дом', 'питомец', 'стерил', 'прививк',
                'потерял', 'нашел', 'пропал', 'найден', 'потеряшка'
            ]
        elif animal_type == 'dogs':
            keywords = [
                'собак', 'пес', 'щен', 'собач', 'лай',
                'пристрой', 'дом', 'питомец', 'стерил', 'прививк',
                'потерял', 'нашел', 'пропал', 'найден', 'потеряшка'
            ]
        else:
            keywords = [
                'кот', 'кошк', 'котен', 'котик', 'мурз', 'мяу',
                'собак', 'пес', 'щен', 'собач', 'лай',
                'пристрой', 'дом', 'питомец', 'стерил', 'прививк',
                'потерял', 'нашел', 'пропал', 'найден', 'потеряшка'
            ]
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in keywords)
    
    def get_mock_posts(self, channel_type: str = 'cats') -> List[Dict]:
        """Возвращает тестовые посты с фото"""
        if channel_type == 'dogs':
            return [
                {
                    'id': '2001',
                    'title': '🐕 Собака Рекс ищет дом',
                    'description': 'Возраст: 1 год, мальчик, смешанная порода. Здоров, привит, очень дружелюбный.',
                    'date': '03.08.2025 14:30',
                    'timestamp': time.time(),
                    'url': 'https://t.me/dogs_yalta/2001',
                    'contact': '@volunteer_dogs • +7 978 123-45-67',
                    'photo_url': 'https://via.placeholder.com/600x400?text=Собака+Рекс',
                    'video_url': None,
                    'has_media': True,
                    'type': 'dogs',
                    'channel': 'Собаки Ялта',
                    'channel_url': 'https://t.me/dogs_yalta'
                }
            ]
        else:
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
                }
            ]

class CatBotWithPhotos:
    """Бот для помощи животным Ялты - работает только через упоминания"""
    
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
        self.contacts = self.load_contacts()
        
        self.setup_handlers()
        self.setup_routes()
    
    def load_contacts(self) -> dict:
        """Загружает контакты из JSON-файла."""
        try:
            with open('assets/contacts.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки контактов: {e}")
            return {
                "контакты": {
                    "светлана": "+7 978 144-90-70",
                    "координатор": "+7 978 144-90-70",
                    "стерилизация": "+7 978 000-00-02",
                    "лечение": "+7 978 000-00-03",
                    "айболит": "+7 978 000-00-11",
                    "ветмир": "+7 978 000-00-13",
                    "волонтеры": "@cats_yalta_coordinator"
                },
                "синонимы": {
                    "света": "светлана",
                    "светка": "светлана",
                    "клиника": "айболит",
                    "ветклиника": "айболит",
                    "ветеринар": "айболит",
                    "врач": "айболит",
                    "стерил": "стерилизация",
                    "кастрация": "стерилизация"
                }
            }

    def send_post(self, chat_id: int, post: Dict, reply_to_message_id: int = None):
        """Отправляет один пост с медиа или текстом"""
        try:
            emoji = '🐱' if post['type'] == 'cats' else '🐕'
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
                        reply_to_message_id=reply_to_message_id,
                        reply_markup=types.InlineKeyboardMarkup().add(
                            types.InlineKeyboardButton("📢 Открыть пост", url=post['url'])
                        )
                    )
                    return
                except Exception as e:
                    logger.error(f"❌ Ошибка отправки фото: {e}")
            
            # Если не удалось отправить медиа, отправляем текст
            self.bot.send_message(
                chat_id,
                post_text,
                parse_mode="HTML",
                disable_web_page_preview=False,
                reply_to_message_id=reply_to_message_id,
                reply_markup=types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton("📢 Открыть пост", url=post['url'])
                )
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки поста: {e}")

    def send_channel_posts(self, chat_id: int, animal_type: str = 'cats', reply_to_message_id: int = None):
        """Отправляет все посты с медиа"""
        try:
            posts = self.parser.get_cached_posts(animal_type)
            
            if not posts:
                channels = [c for c in self.parser.channels if c['type'] == animal_type]
                animal_name = "котиков" if animal_type == 'cats' else "собак"
                self.bot.send_message(
                    chat_id,
                    f"😿 Сейчас нет актуальных объявлений о {animal_name}.\n\n"
                    f"📢 Проверьте группы:\n" +
                    '\n'.join([f"• {c['url']}" for c in channels]),
                    reply_to_message_id=reply_to_message_id
                )
                return
            
            animal_emoji = '🐱' if animal_type == 'cats' else '🐕'
            animal_name = "КОТИКИ" if animal_type == 'cats' else "СОБАКИ"
            
            self.bot.send_message(
                chat_id,
                f"{animal_emoji} <b>{animal_name} ИЩУТ ДОМ</b>\n\n"
                f"📢 Последние объявления из групп Ялты:",
                parse_mode="HTML",
                reply_to_message_id=reply_to_message_id
            )
            
            for post in posts:
                self.send_post(chat_id, post)
                time.sleep(0.7)  # Защита от флуда
            
            channels = [c for c in self.parser.channels if c['type'] == animal_type]
            self.bot.send_message(
                chat_id,
                "💡 <b>Как помочь?</b>\n\n"
                f"🏠 <b>Взять питомца:</b>\nСвяжитесь по контактам из объявления\n\n"
                f"📢 <b>Группы:</b>\n" +
                '\n'.join([f"• <a href='{c['url']}'>{c['title']}</a>" for c in channels]) +
                "\n\n🤝 <b>Стать волонтером:</b>\nНапишите в группу",
                parse_mode="HTML"
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки постов: {e}")
            animal_name = "котиков" if animal_type == 'cats' else "собак"
            channels = [c for c in self.parser.channels if c['type'] == animal_type]
            self.bot.send_message(
                chat_id,
                f"⚠️ Ошибка загрузки объявлений о {animal_name}\n\n"
                f"Попробуйте позже или посетите группы:\n" +
                '\n'.join([f"• {c['url']}" for c in channels]),
                reply_to_message_id=reply_to_message_id
            )

    def parse_command(self, text: str) -> dict:
        """Парсит команду из упоминания бота"""
        # Убираем упоминание бота
        clean_text = re.sub(r'@catYalta_bot\s*', '', text, flags=re.IGNORECASE).strip().lower()
        
        # Определяем тип команды
        result = {
            'action': 'unknown',
            'params': {},
            'text': clean_text
        }
        
        # Поиск контактов
        if any(word in clean_text for word in ['номер', 'телефон', 'контакт', 'связаться', 'позвонить']):
            result['action'] = 'contact'
            return result
        
        # Информация о стерилизации
        if any(word in clean_text for word in ['стерилизация', 'кастрация', 'стерил', 'операция']):
            result['action'] = 'sterilization'
            if any(word in clean_text for word in ['бесплатн', 'даром', 'free']):
                result['params']['type'] = 'free'
            elif any(word in clean_text for word in ['платн', 'paid', 'цена', 'стоимость']):
                result['params']['type'] = 'paid'
            return result
        
        # Пристройство животных
        if any(word in clean_text for word in ['пристрой', 'дом', 'взять', 'усынов', 'найти']):
            result['action'] = 'adoption'
            if any(word in clean_text for word in ['собак', 'пес', 'щен']):
                result['params']['animal'] = 'dogs'
            else:
                result['params']['animal'] = 'cats'  # по умолчанию котики
            return result
        
        # Подача объявления
        if any(word in clean_text for word in ['подать', 'разместить', 'объявление', 'пристроить']):
            result['action'] = 'post_ad'
            return result
        
        # О проекте
        if any(word in clean_text for word in ['проект', 'о нас', 'информация', 'about']):
            result['action'] = 'about'
            return result
        
        # Помощь
        if any(word in clean_text for word in ['помощь', 'help', 'команды', 'что умеешь']):
            result['action'] = 'help'
            return result
        
        return result

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
            # Только в приватных чатах показываем приветствие
            if message.chat.type == 'private':
                self.stats["users"].add(message.from_user.id)
                self.stats["messages"] += 1
                
                welcome_text = """👋 <b>Добро пожаловать в "Животные Ялты"!</b>

🐾 Для работы с ботом используйте упоминания @catYalta_bot в любом чате или группе.

📝 <b>Примеры команд:</b>
• @catYalta_bot номер Светланы
• @catYalta_bot котики ищут дом  
• @catYalta_bot собаки ищут дом
• @catYalta_bot стерилизация
• @catYalta_bot подать объявление
• @catYalta_bot помощь

🔒 <b>Конфиденциальность:</b> Ответы бота видны только вам (в группах)."""
                
                self.bot.send_message(
                    message.chat.id, 
                    welcome_text, 
                    parse_mode="HTML"
                )
        
        @self.bot.message_handler(func=lambda m: m.text and '@catYalta_bot' in m.text)
        def handle_mentions(message):
            """Обработка упоминаний бота в любом чате"""
            try:
                self.stats["users"].add(message.from_user.id)
                self.stats["messages"] += 1
                
                command = self.parse_command(message.text)
                
                if command['action'] == 'contact':
                    # Ищем контакт в тексте
                    query = command['text']
                    contacts = self.contacts["контакты"]
                    synonyms = self.contacts["синонимы"]
                    response = None
                    
                    # Проверяем прямые совпадения
                    for keyword in contacts:
                        if keyword in query:
                            contact_info = contacts[keyword]
                            if contact_info.startswith('@'):
                                response = f"📱 {keyword.capitalize()}: {contact_info}"
                            else:
                                response = f"📞 {keyword.capitalize()}: {contact_info}"
                            break
                    
                    # Проверяем синонимы
                    if not response:
                        for syn, original in synonyms.items():
                            if syn in query:
                                contact_info = contacts[original]
                                if contact_info.startswith('@'):
                                    response = f"📱 {original.capitalize()}: {contact_info}"
                                else:
                                    response = f"📞 {original.capitalize()}: {contact_info}"
                                break
                    
                    if not response:
                        response = (
                            "📞 <b>Доступные контакты:</b>\n\n"
                            "🔹 Светлана (координатор): +7 978 144-90-70\n"
                            "🔹 Стерилизация: +7 978 000-00-02\n"
                            "🔹 Лечение: +7 978 000-00-03\n"
                            "🔹 Клиника Айболит: +7 978 000-00-11\n"
                            "🔹 Клиника ВетМир: +7 978 000-00-13\n"
                            "🔹 Волонтеры: @cats_yalta_coordinator\n\n"
                            "<i>Пример: @catYalta_bot номер Светланы</i>"
                        )
                
                elif command['action'] == 'adoption':
                    animal_type = command['params'].get('animal', 'cats')
                    self.send_channel_posts(message.chat.id, animal_type, message.message_id)
                    return  # Выходим, чтобы не отправлять дополнительный ответ
                
                elif command['action'] == 'sterilization':
                    steril_type = command['params'].get('type')
                    if steril_type == 'free':
                        response = self.load_html_file('free_text.html')
                    elif steril_type == 'paid':
                        response = self.load_html_file('paid_text.html')
                    else:
                        response = """🏥 <b>СТЕРИЛИЗАЦИЯ ЖИВОТНЫХ</b>

💰 <b>Платная стерилизация:</b>
• Клиника "Айболит": от 3000₽ (+7 978 000-00-11)
• Клиника "ВетМир": от 2500₽ (+7 978 000-00-13)

🆓 <b>Бесплатная стерилизация:</b>
• Для бездомных животных
• Координатор: +7 978 144-90-70

<i>Подробнее: @catYalta_bot платная стерилизация</i>
<i>или: @catYalta_bot бесплатная стерилизация</i>"""
                
                elif command['action'] == 'post_ad':
                    channels_cats = [c for c in self.parser.channels if c['type'] == 'cats']
                    channels_dogs = [c for c in self.parser.channels if c['type'] == 'dogs']
                    
                    response = f"""📝 <b>ПОДАТЬ ОБЪЯВЛЕНИЕ</b>

📢 <b>Группы для котиков:</b>
{chr(10).join([f'• <a href="{c["url"]}">{c["title"]}</a>' for c in channels_cats])}

📢 <b>Группы для собак:</b>
{chr(10).join([f'• <a href="{c["url"]}">{c["title"]}</a>' for c in channels_dogs])}

✍️ <b>Как подать:</b>
1️⃣ Перейти в соответствующую группу
2️⃣ Написать администраторам
3️⃣ Или связаться с координатором: +7 978 144-90-70

📋 <b>Нужная информация:</b>
🔹 Фото животного
🔹 Возраст, пол, окрас/порода
🔹 Характер
🔹 Здоровье (прививки, стерилизация)
🔹 Ваши контакты"""
                
                elif command['action'] == 'about':
                    response = """ℹ️ <b>О ПРОЕКТЕ "ЖИВОТНЫЕ ЯЛТЫ"</b>

🎯 <b>Миссия:</b>
Помощь бездомным кошкам и собакам Ялты

📊 <b>Достижения:</b>
🔹 Стерилизовано: 500+ животных
🔹 Пристроено: 300+ котят и щенков
🔹 Волонтеров: 30+ активных

💰 <b>Поддержать:</b>
Карта: 2202 2020 0000 0000

🤝 <b>Стать волонтером:</b>
Координатор: +7 978 144-90-70
Telegram: @cats_yalta_coordinator"""
