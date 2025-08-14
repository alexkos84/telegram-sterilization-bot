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

class AdvancedAnimalParser:
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
        self.posts_cache = {'cats': [], 'dogs': []}
        self.last_update = {'cats': None, 'dogs': None}
        
        # Ключевые слова для фильтрации
        self.animal_keywords = {
            'cats': [
                'кот', 'кошк', 'котен', 'котик', 'мурз', 'мяу',
                'киса', 'кис', 'мурка', 'васька', 'барсик',
                'кошачий', 'кошачья', 'кошачье'
            ],
            'dogs': [
                'собак', 'пес', 'псин', 'щен', 'гав',
                'лабрадор', 'овчарка', 'дворняжка', 'дворняга',
                'бобик', 'шарик', 'рекс', 'джек',
                'собачий', 'собачья', 'собачье'
            ]
        }
    
    def load_vet_clinics(self) -> Dict:
        """Загружает базу ветклиник из JSON"""
        try:
            with open('vet_clinics.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки ветклиник: {e}")
            return {"места": {}, "синонимы": {}}
    
    def get_channel_posts(self, animal_type: str = 'cats', limit: int = 5) -> List[Dict]:
        """Получает последние посты о конкретном типе животных"""
        try:
            posts = []
            relevant_channels = [ch for ch in self.channels if ch['type'] == animal_type]
            
            for channel in relevant_channels:
                web_url = f'https://t.me/s/{channel["username"]}'
                logger.info(f"🌐 Загрузка {animal_type} постов с {web_url}")
                
                try:
                    response = requests.get(web_url, headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }, timeout=15)
                    response.raise_for_status()
                    
                    soup = BeautifulSoup(response.content, 'html.parser')
                    message_divs = soup.find_all('div', class_='tgme_widget_message')
                    
                    for div in message_divs[:limit*2]:
                        post_data = self.parse_message_div(div, channel)
                        if post_data and self.is_animal_related(post_data.get('text', ''), animal_type):
                            posts.append(post_data)
                            if len(posts) >= limit:
                                break
                                
                except Exception as e:
                    logger.error(f"❌ Ошибка парсинга {channel['username']}: {e}")
                    continue
            
            # Сортируем по дате
            posts.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
            
            if posts:
                self.posts_cache[animal_type] = posts[:limit]
                self.last_update[animal_type] = datetime.now()
                logger.info(f"✅ Получено {len(posts)} {animal_type} постов")
            else:
                logger.warning(f"⚠️ Не найдено {animal_type} постов")
                
            return posts[:limit] or self.get_mock_posts(animal_type)
            
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга {animal_type}: {e}")
            return self.get_mock_posts(animal_type)
    
    def parse_message_div(self, div, channel) -> Optional[Dict]:
        """Парсит пост, извлекая текст и медиа"""
        try:
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
            
            # Медиа
            photo_url = None
            video_url = None
            
            photo_wrap = div.find('a', class_='tgme_widget_message_photo_wrap')
            if photo_wrap and photo_wrap.get('style'):
                match = re.search(r"background-image:url\('(.*?)'\)", photo_wrap['style'])
                if match:
                    photo_url = match.group(1)
            
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
        emoji = '🐱' if animal_type == 'cats' else '🐶'
        animal_name = 'котик' if animal_type == 'cats' else 'песик'
        
        lines = text.split('\n')
        for line in lines[:3]:
            line = line.strip()
            if line and len(line) > 5:
                title = re.sub(r'[^\w\s\-\.,!?а-яёА-ЯЁ]', '', line)
                if len(title) > 50:
                    title = title[:50] + "..."
                return f"{emoji} {title}" or f"{emoji} {animal_name.title()} ищет дом"
        return f"{emoji} {animal_name.title()} ищет дом"
    
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
        """Проверяет, относится ли пост к нужному типу животных"""
        keywords = self.animal_keywords.get(animal_type, [])
        keywords.extend([
            'пристрой', 'дом', 'питомец', 'стерил', 'прививк',
            'потерял', 'нашел', 'пропал', 'найден', 'потеряшка',
            'ищет', 'семью', 'хозяин', 'приют'
        ])
        
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in keywords)
    
    def get_mock_posts(self, animal_type: str = 'cats') -> List[Dict]:
        """Возвращает тестовые посты"""
        if animal_type == 'cats':
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
                    'has_media': True,
                    'type': 'cats',
                    'channel': 'Котики Ялта',
                    'channel_url': 'https://t.me/cats_yalta'
                }
            ]
        else:  # dogs
            return [
                {
                    'id': '2001',
                    'title': '🐶 Щенок Рекс ищет дом',
                    'description': 'Возраст: 3 месяца, мальчик, метис овчарки. Активный, дружелюбный.',
                    'date': '03.08.2025 15:20',
                    'timestamp': time.time(),
                    'url': 'https://t.me/dogs_yalta/2001',
                    'contact': '@volunteer2 • +7 978 765-43-21',
                    'photo_url': 'https://via.placeholder.com/600x400?text=Щенок+Рекс',
                    'has_media': True,
                    'type': 'dogs',
                    'channel': 'Собаки Ялта',
                    'channel_url': 'https://t.me/dogs_yalta'
                }
            ]
    
    def get_cached_posts(self, animal_type: str = 'cats') -> List[Dict]:
        """Возвращает кэшированные или обновленные посты"""
        if (not self.last_update.get(animal_type) or 
            (datetime.now() - self.last_update[animal_type]).seconds > 3600):
            try:
                return self.get_channel_posts(animal_type)
            except:
                pass
        return self.posts_cache.get(animal_type, []) or self.get_mock_posts(animal_type)

class ImprovedPetBot:
    """Улучшенный бот для помощи животным Ялты"""
    
    def __init__(self):
        self.token = os.environ.get('TOKEN')
        if not self.token:
            logger.error("❌ TOKEN не найден!")
            exit(1)
        
        self.bot = telebot.TeleBot(self.token)
        self.parser = AdvancedAnimalParser()
        self.app = Flask(__name__)
        self.port = int(os.environ.get('PORT', 8080))
        self.webhook_url = os.environ.get('WEBHOOK_URL')
        self.stats = {"users": set(), "messages": 0}
        
        self.setup_handlers()
        self.setup_routes()
    
    def send_post(self, chat_id: int, post: Dict):
        """Отправляет один пост с медиа"""
        try:
            emoji = '🐱' if post['type'] == 'cats' else '🐶'
            post_text = (
                f"{emoji} <b>{post['title']}</b>\n\n"
                f"{post['description']}\n\n"
                f"📅 {post['date']}\n"
                f"📞 {post['contact']}\n"
                f"📢 <a href='{post['channel_url']}'>{post['channel']}</a>"
            )
            
            if len(post_text) > 1024:
                post_text = post_text[:1000] + "..."
            
            # Отправка медиа
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
            
            # Текстовое сообщение
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

    def send_animal_posts(self, chat_id: int, animal_type: str = 'cats'):
        """Отправляет посты о конкретном типе животных"""
        try:
            posts = self.parser.get_cached_posts(animal_type)
            
            if not posts:
                animal_name = 'котики' if animal_type == 'cats' else 'собаки'
                emoji = '😿' if animal_type == 'cats' else '😔'
                channels = [ch['url'] for ch in self.parser.channels if ch['type'] == animal_type]
                
                self.bot.send_message(
                    chat_id,
                    f"{emoji} Сейчас нет актуальных объявлений о {animal_name}.\n\n"
                    f"📢 Проверьте группы:\n" + 
                    '\n'.join(f"• {url}" for url in channels)
                )
                return
            
            animal_name_caps = 'КОТИКИ' if animal_type == 'cats' else 'СОБАКИ'
            emoji = '🐱' if animal_type == 'cats' else '🐶'
            
            self.bot.send_message(
                chat_id,
                f"{emoji} <b>{animal_name_caps} ИЩУТ ДОМ</b>\n\n"
                f"📢 Последние объявления из групп Ялты:",
                parse_mode="HTML"
            )
            
            for post in posts:
                self.send_post(chat_id, post)
                time.sleep(0.7)
            
            channels = [ch for ch in self.parser.channels if ch['type'] == animal_type]
            channels_text = '\n'.join(f"• <a href='{ch['url']}'>{ch['title']}</a>" for ch in channels)
            
            self.bot.send_message(
                chat_id,
                f"💡 <b>Как помочь?</b>\n\n"
                f"🏠 <b>Взять питомца:</b>\nСвяжитесь по контактам из объявления\n\n"
                f"📢 <b>Группы:</b>\n{channels_text}\n\n"
                "🤝 <b>Стать волонтером:</b>\nНапишите в группу",
                parse_mode="HTML"
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки {animal_type} постов: {e}")
            animal_name = 'котиков' if animal_type == 'cats' else 'собак'
            channels = [ch['url'] for ch in self.parser.channels if ch['type'] == animal_type]
            
            self.bot.send_message(
                chat_id,
                f"⚠️ Ошибка загрузки объявлений о {animal_name}\n\n"
                f"Попробуйте позже или посетите группы:\n" + 
                '\n'.join(f"• {url}" for url in channels)
            )

    def get_main_keyboard(self):
        """Главная клавиатура"""
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add("🏥 Стерилизация", "🏠 Пристройство")
        markup.add("🏥 Ветклиники", "📞 Контакты")
        markup.add("ℹ️ О проекте")
        return markup
    
    def get_adoption_keyboard(self):
        """Клавиатура пристройства"""
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
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

    def send_vet_clinics(self, chat_id: int, city: str = 'ялта'):
        """Отправляет список ветклиник"""
        try:
            clinics_data = self.parser.load_vet_clinics()
            city_clinics = clinics_data.get('места', {}).get(city, {})
            
            if not city_clinics:
                self.bot.send_message(
                    chat_id,
                    f"⚠️ Информация о ветклиниках в городе '{city}' не найдена."
                )
                return
            
            self.bot.send_message(
                chat_id,
                f"🏥 <b>ВЕТКЛИНИКИ {city.upper()}</b>\n\n"
                f"📍 Найдено клиник: {len(city_clinics)}",
                parse_mode="HTML"
            )
            
            for clinic_name, info in city_clinics.items():
                clinic_text = f"🏥 <b>{clinic_name.upper()}</b>\n\n"
                
                if 'адрес' in info:
                    clinic_text += f"📍 {info['адрес']}\n"
                if 'время' in info:
                    clinic_text += f"🕒 {info['время']}\n"
                if 'телефон' in info:
                    phones = info['телефон'] if isinstance(info['телефон'], list) else [info['телефон']]
                    clinic_text += f"📞 {' • '.join(phones)}\n"
                if 'врачи' in info:
                    clinic_text += "👨‍⚕️ Врачи:\n"
                    for doctor in info['врачи']:
                        if 'имя' in doctor:
                            clinic_text += f"  • {doctor['имя']}"
                            if 'тел' in doctor:
                                clinic_text += f" - {doctor['тел']}"
                            clinic_text += "\n"
                if 'услуги' in info:
                    clinic_text += f"🔬 Услуги: {', '.join(info['услуги'])}\n"
                if 'выезд' in info and info['выезд']:
                    if isinstance(info['выезд'], dict) and 'стоимость' in info['выезд']:
                        clinic_text += f"🚗 Выезд: {info['выезд']['стоимость']}\n"
                    else:
                        clinic_text += "🚗 Выезд: да\n"
                
                if 'ссылка' in info:
                    clinic_text += f"🌐 <a href='{info['ссылка']}'>Подробнее</a>\n"
                
                self.bot.send_message(chat_id, clinic_text, parse_mode="HTML")
                time.sleep(0.5)
                
        except Exception as e:
            logger.error(f"❌ Ошибка отправки ветклиник: {e}")
            self.bot.send_message(
                chat_id,
                "⚠️ Ошибка загрузки информации о ветклиниках"
            )

    def setup_handlers(self):
        """Обработчики сообщений"""
        
        @self.bot.message_handler(commands=['start'])
        def start_handler(message):
            self.stats["users"].add(message.from_user.id)
            self.stats["messages"] += 1
            
            welcome_text = """👋 <b>Добро пожаловать в помощника по животным Ялты!</b>

🐾 Что умеет бот:

🏥 <b>Стерилизация</b> - информация и цены
🏠 <b>Пристройство</b> - кошки и собаки ищут дом  
🏥 <b>Ветклиники</b> - адреса и контакты
📞 <b>Контакты</b> - связь с волонтерами
ℹ️ <b>О проекте</b> - наша деятельность"""
            
            self.bot.send_message(
                message.chat.id, 
                welcome_text, 
                parse_mode="HTML",
                reply_markup=self.get_main_keyboard()
            )
        
        @self.bot.message_handler(commands=['update_cats', 'update_dogs'])
        def update_handler(message):
            """Обновление постов (для админов)"""
            if message.from_user.id not in [123456789]:  # Замените на ваш ID
                return
            
            animal_type = 'cats' if 'cats' in message.text else 'dogs'
            self.parser.posts_cache[animal_type] = []
            self.parser.last_update[animal_type] = None
            
            self.bot.send_message(message.chat.id, f"🔄 Обновляю {animal_type} посты...")
            posts = self.parser.get_channel_posts(animal_type)
            self.bot.send_message(
                message.chat.id, 
                f"✅ Обновлено: {len(posts)} {animal_type} постов"
            )
        
        # Основные обработчики
        @self.bot.message_handler(func=lambda m: m.text == "🏥 Стерилизация")
        def sterilization_handler(message):
            self.bot.send_message(
                message.chat.id,
                "🏥 <b>Стерилизация животных</b>\n\nВыберите вариант:",
                parse_mode="HTML",
                reply_markup=self.get_sterilization_keyboard()
            )
        
        @self.bot.message_handler(func=lambda m: m.text == "🏠 Пристройство")
        def adoption_handler(message):
            self.bot.send_message(
                message.chat.id,
                "🏠 <b>Пристройство животных</b>\n\nВыберите тип животного:",
                parse_mode="HTML",
                reply_markup=self.get_adoption_keyboard()
            )
        
        @self.bot.message_handler(func=lambda m: m.text == "🐱 Кошки ищут дом")
        def cats_adoption_handler(message):
            self.send_animal_posts(message.chat.id, 'cats')
        
        @self.bot.message_handler(func=lambda m: m.text == "🐶 Собаки ищут дом")
        def dogs_adoption_handler(message):
            self.send_animal_posts(message.chat.id, 'dogs')
        
        @self.bot.message_handler(func=lambda m: m.text == "🏥 Ветклиники")
        def vet_clinics_handler(message):
            self.send_vet_clinics(message.chat.id)
        
        @self.bot.message_handler(func=lambda m: m.text == "📞 Контакты")
        def contacts_handler(message):
            contacts_text = """📞 <b>КОНТАКТЫ ВОЛОНТЕРОВ</b>

👥 <b>Координаторы:</b>
🐱 По кошкам: +7 978 144-90-70
🐶 По собакам: +7 978 000-00-02
💉 По стерилизации: +7 978 000-00-03
🚑 Срочная помощь: +7 978 000-00-04

📱 <b>Социальные сети:</b>
🐱 Telegram: @cats_yalta
🐶 Telegram: @dogs_yalta
📷 Instagram: @yalta_animals"""
            
            self.bot.send_message(message.chat.id, contacts_text, parse_mode="HTML")
        
        @self.bot.message_handler(func=lambda m: m.text == "ℹ️ О проекте")
        def about_handler(message):
            about_text = """ℹ️ <b>О ПРОЕКТЕ "ЖИВОТНЫЕ ЯЛТЫ"</b>

🎯 <b>Миссия:</b>
Помощь бездомным кошкам и собакам Ялты

📊 <b>Наши достижения:</b>
🐱 Стерилизовано кошек: 500+
🐶 Стерилизовано собак: 200+
🏠 Пристроено животных: 800+
👥 Активных волонтеров: 50+

💰 <b>Поддержать проект:</b>
Карта Сбербанк: 2202 2020 0000 0000
Карта Тинькофф: 5536 9137 0000 0000

🤝 <b>Стать волонтером:</b>
Напишите @animals_yalta_coordinator

🌐 <b>Наши ресурсы:</b>
• Telegram-каналы с объявлениями
• База ветеринарных клиник
• Координация помощи животным
• Информационная поддержка"""
            
            self.bot.send_message(message.chat.id, about_text, parse_mode="HTML")
        
        @self.bot.message_handler(func=lambda m: m.text == "💰 Платная стерилизация")
        def paid_sterilization_handler(message):
            paid_text = """💵 <b>ПЛАТНАЯ СТЕРИЛИЗАЦИЯ</b>

🏥 <b>Рекомендуемые клиники:</b>

🔹 <b>Клиника "Айболит"</b>
📍 ул. Васильева-Тренёва, 3/7
💰 Кошки: от 3000₽, Собаки: от 4500₽
📞 +7 (978) 869-73-80

🔹 <b>Клиника "Доверие"</b>
📍 ул. Халтурина, 52А
💰 Кошки: от 2800₽, Собаки: от 4000₽
📞 +7 (978) 256-15-01

🔹 <b>Ветцентр "Хатико"</b>
📍 ул. Московская, 59
💰 Кошки: от 3200₽, Собаки: от 4800₽
📞 +7 (978) 725-91-59

🌟 <b>В стоимость включено:</b>
✅ Операция под наркозом
✅ Послеоперационный уход
✅ Медикаменты
✅ Консультация врача

💡 <b>Скидки для волонтеров:</b>
🔸 При предъявлении волонтерского удостоверения - 20%
🔸 При стерилизации нескольких животных - 15%

📞 Запись по телефонам клиник"""
            
            self.bot.send_message(message.chat.id, paid_text, parse_mode="HTML")
        
        @self.bot.message_handler(func=lambda m: m.text == "🆓 Бесплатная стерилизация")
        def free_sterilization_handler(message):
            free_text = """🆓 <b>БЕСПЛАТНАЯ СТЕРИЛИЗАЦИЯ</b>

🏛️ <b>Муниципальная программа:</b>
✅ Для бездомных животных
✅ По направлению волонтеров
✅ Ограниченное количество мест

📋 <b>Требования:</b>
🔹 Справка о статусе (бездомное животное)
🔹 Предварительная запись
🔹 Базовые анализы за свой счет

🏥 <b>Участвующие клиники:</b>
• Муниципальная ветклиника
📍 ул. Саханя, 5
📞 +7 (978) 860-36-98
🕒 Пн-Пт: 8:00-16:00

• По программе "Забота"
📍 Кореиз, ул. Маяковского, 2Б  
📞 +7 (978) 651-07-47
💰 Льготная стерилизация

📞 <b>Координация:</b>
Куратор программы: +7 978 144-90-70

⚠️ <b>Важно:</b>
Места ограничены, запись обязательна!
Приоритет - уличные животные и животные из приютов."""
            
            self.bot.send_message(message.chat.id, free_text, parse_mode="HTML")
        
        @self.bot.message_handler(func=lambda m: m.text == "📝 Подать объявление")
        def submit_ad_handler(message):
            submit_text = """📝 <b>КАК ПОДАТЬ ОБЪЯВЛЕНИЕ</b>

📢 <b>Каналы для размещения:</b>

🐱 <b>Для кошек:</b>
• <a href="https://t.me/cats_yalta">Котики Ялта (канал)</a>
• <a href="https://t.me/cats_yalta_group">Котики Ялта (группа)</a>

🐶 <b>Для собак:</b>
• <a href="https://t.me/dogs_yalta">Собаки Ялта (канал)</a>
• <a href="https://t.me/dogs_yalta_group">Собаки Ялта (группа)</a>

✍️ <b>Способы подачи:</b>
1️⃣ Написать в группу напрямую
2️⃣ Связаться с администраторами
3️⃣ Координатор: +7 978 144-90-70

📋 <b>Обязательная информация:</b>
📷 Качественные фото животного
🎂 Возраст и пол
🎨 Окрас и особые приметы
😺 Характер и особенности
💉 Состояние здоровья (прививки, стерилизация)
📞 Контакты для связи
📍 Район (желательно)

💡 <b>Советы для успешного пристройства:</b>
• Делайте хорошие фото при дневном свете
• Честно описывайте характер
• Указывайте все особенности здоровья
• Будьте на связи для ответов

🚫 <b>Запрещено:</b>
• Продажа животных
• Недостоверная информация
• Реклама коммерческих услуг"""
            
            self.bot.send_message(message.chat.id, submit_text, parse_mode="HTML")
        
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
            
            # Проверка на поиск ветклиники
            text = message.text.lower()
            if any(word in text for word in ['клиника', 'ветеринар', 'врач', 'лечение']):
                self.send_vet_clinics(message.chat.id)
            else:
                self.bot.send_message(
                    message.chat.id,
                    "❓ Используйте кнопки меню для навигации\n\n"
                    "Или введите /start для возврата в главное меню",
                    reply_markup=self.get_main_keyboard()
                )
    
    def setup_routes(self):
        """Flask маршруты для мониторинга"""
        
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
                "status": "🐾 Animals Bot Running",
                "time": datetime.now().strftime('%H:%M:%S'),
                "users": len(self.stats["users"]),
                "messages": self.stats["messages"],
                "channels": {
                    "cats": [c['url'] for c in self.parser.channels if c['type'] == 'cats'],
                    "dogs": [c['url'] for c in self.parser.channels if c['type'] == 'dogs']
                },
                "last_update": {
                    "cats": self.parser.last_update['cats'].isoformat() if self.parser.last_update['cats'] else None,
                    "dogs": self.parser.last_update['dogs'].isoformat() if self.parser.last_update['dogs'] else None
                }
            })
        
        @self.app.route('/posts/<animal_type>')
        def posts_api(animal_type):
            try:
                if animal_type not in ['cats', 'dogs']:
                    return jsonify({"error": "Invalid animal type"}), 400
                    
                posts = self.parser.get_cached_posts(animal_type)
                return jsonify({
                    "status": "ok",
                    "animal_type": animal_type,
                    "count": len(posts),
                    "posts": [{
                        "title": p["title"],
                        "url": p["url"],
                        "date": p["date"],
                        "channel": p["channel"],
                        "has_media": p["has_media"]
                    } for p in posts],
                    "channels": [c['url'] for c in self.parser.channels if c['type'] == animal_type]
                })
            except Exception as e:
                return jsonify({"status": "error", "message": str(e)}), 500
        
        @self.app.route('/clinics')
        def clinics_api():
            try:
                clinics_data = self.parser.load_vet_clinics()
                return jsonify({
                    "status": "ok",
                    "data": clinics_data
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
            logger.error(f"❌ Ошибка настройки webhook: {e}")
            return False
    
    def run(self):
        """Запуск бота"""
        logger.info("🚀 Запуск улучшенного бота для животных Ялты...")
        
        # Предзагрузка данных
        try:
            cats_posts = self.parser.get_cached_posts('cats')
            dogs_posts = self.parser.get_cached_posts('dogs')
            logger.info(f"✅ Предзагружено: {len(cats_posts)} кошек, {len(dogs_posts)} собак")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка предзагрузки: {e}")
        
        if self.setup_webhook():
            logger.info(f"🌐 Сервер запущен на порту {self.port}")
            self.app.run(host='0.0.0.0', port=self.port, debug=False)
        else:
            logger.error("🚨 Ошибка webhook, запуск в polling режиме...")
            try:
                self.bot.polling(none_stop=True, interval=0, timeout=20)
            except Exception as e:
                logger.error(f"❌ Ошибка polling: {e}")

def create_vet_clinics_file():
    """Создает файл с ветклиниками из JSON"""
    vet_data = {
        "места": {
            "ялта": {
                "айболит": {
                    "адрес": "ул. Васильева-Тренёва, 3/7",
                    "время": "Пн–Пт: 9:00–19:00; Сб–Вс: 9:00–17:00",
                    "ветаптека": "+7 (978) 869-73-80",
                    "врачи": [
                        {"имя": "Роман Леонидович", "тел": "+7 (978) 761-66-52"},
                        {"имя": "Наталья Георгиевна", "тел": "+7 (978) 869-70-09"},
                        {"тел": "+7 (978) 761-65-79"}
                    ],
                    "выезд": False,
                    "ссылка": "https://vk.com/zoovet1"
                },
                "здоровейко": {
                    "адрес": "ул. Красноармейская, 6",
                    "время": "Пн–Пт: 9:00–17:00",
                    "ветаптека": True,
                    "выезд": {"стоимость": "1500 руб."},
                    "врачи": [
                        {"имя": "Юлия Викторовна", "тел": "+7 (978) 782-46-81"},
                        {"тел": "+7 (978) 782-46-82"}
                    ],
                    "ссылка": "https://vk.com/vet.zdoroveyko"
                },
                "доверие": {
                    "адрес": "ул. Халтурина, 52А",
                    "время": "Пн–Вс: 9:00–21:00",
                    "услуги": ["стационар", "зоогостиница", "донорская база", "УЗИ", "ЭХО сердца", "рентген"],
                    "экзотика": True,
                    "выезд": False,
                    "телефон": ["+7 (978) 256-15-01", "+7 (978) 976-84-34"],
                    "ссылка": "https://vk.com/doverieyalta"
                },
                "хатико": {
                    "адрес": "ул. Московская, 59 (ост. Автовокзал)",
                    "время": "Пн–Вс: 9:00–21:00",
                    "ветаптека": True,
                    "услуги": ["УЗИ", "рентген", "анализ крови"],
                    "экзотика": True,
                    "выезд": {"стоимость": "2000 руб."},
                    "телефон": ["+7 (978) 725-91-59", "+7 (978) 106-72-06"]
                }
            },
            "алупка": {
                "дай лапу": {
                    "адрес": "ул. Западная, 22Б",
                    "время": "Пн–Сб: 9:00–18:00; Вс: выходной",
                    "телефон": "+7 (978) 083-90-99"
                }
            }
        },
        "синонимы": {
            "доверие": "доверие",
            "хатико": "хатико", 
            "айболит": "айболит"
        }
    }
    
    try:
        with open('vet_clinics.json', 'w', encoding='utf-8') as f:
            json.dump(vet_data, f, ensure_ascii=False, indent=2)
        logger.info("✅ Создан файл vet_clinics.json")
    except Exception as e:
        logger.error(f"❌ Ошибка создания файла ветклиник: {e}")

if __name__ == "__main__":
    # Создание необходимых файлов
    os.makedirs('assets/images', exist_ok=True)
    create_vet_clinics_file()
    
    # Запуск бота
    bot = ImprovedPetBot()
    bot.run()
