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

class ChannelParser:
    """Парсер для канала lapki_ruchki_yalta с поддержкой фото и кликабельных номеров"""
    
    def __init__(self):
        self.channel = {
            'username': 'lapki_ruchki_yalta',
            'url': 'https://t.me/lapki_ruchki_yalta',
            'web_url': 'https://t.me/s/lapki_ruchki_yalta'
        }
        self.posts_cache = []
        self.last_update = None
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
    
    def get_channel_posts(self, animal_type: str = 'all', limit: int = 10) -> List[Dict]:
        """Получает последние посты из канала lapki_ruchki_yalta"""
        try:
            logger.info(f"🌐 Загрузка постов с {self.channel['web_url']}")
            
            response = requests.get(
                self.channel['web_url'], 
                headers=self.headers, 
                timeout=15,
                allow_redirects=True
            )
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            message_divs = soup.find_all('div', class_='tgme_widget_message')
            
            logger.info(f"📄 Найдено {len(message_divs)} сообщений")
            
            posts = []
            for div in message_divs:
                post_data = self.parse_message_div(div)
                if post_data and self.filter_animal_post(post_data, animal_type):
                    posts.append(post_data)
                    
                if len(posts) >= limit:
                    break
            
            if posts:
                self.posts_cache = posts
                self.last_update = datetime.now()
                logger.info(f"✅ Получено {len(posts)} постов (с фото: {sum(1 for p in posts if p['photo_url'])})")
            else:
                logger.warning("⚠️ Не найдено подходящих постов")
                
            return posts or self.get_mock_posts(animal_type)
            
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга: {e}")
            return self.get_mock_posts(animal_type)
    
    def parse_message_div(self, div) -> Optional[Dict]:
        """Парсит отдельное сообщение из канала"""
        try:
            # ID поста
            post_id = div.get('data-post', '').split('/')[-1] or str(int(time.time()))
            
            # Текст сообщения
            text_div = div.find('div', class_='tgme_widget_message_text')
            if not text_div:
                return None
                
            text = text_div.get_text('\n', strip=True)
            if not text or len(text) < 10:
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
            
            # Поиск фото
            photo_url = None
            
            # Попытка 1: фото в обертке
            photo_wrap = div.find('a', class_='tgme_widget_message_photo_wrap')
            if photo_wrap and photo_wrap.get('style'):
                match = re.search(r"background-image:url\('(.*?)'\)", photo_wrap['style'])
                if match:
                    photo_url = match.group(1)
            
            # Попытка 2: видео превью
            if not photo_url:
                video_wrap = div.find('a', class_='tgme_widget_message_video_wrap')
                if video_wrap and video_wrap.get('style'):
                    match = re.search(r"background-image:url\('(.*?)'\)", video_wrap['style'])
                    if match:
                        photo_url = match.group(1)
            
            # Попытка 3: обычные изображения
            if not photo_url:
                img_tag = div.find('img')
                if img_tag and img_tag.get('src'):
                    photo_url = img_tag['src']
            
            # Определение типа животного
            animal_type = self.detect_animal_type(text)
            
            return {
                'id': post_id,
                'text': text,
                'date': date_str,
                'url': f"{self.channel['url']}/{post_id}",
                'title': self.extract_title(text, animal_type),
                'description': self.clean_description(text),
                'contact': self.extract_contact(text),
                'phone_numbers': self.extract_phone_numbers(text),
                'photo_url': photo_url,
                'has_photo': bool(photo_url),
                'type': animal_type
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга сообщения: {e}")
            return None
    
    def detect_animal_type(self, text: str) -> str:
        """Определяет тип животного по тексту"""
        text_lower = text.lower()
        
        cat_keywords = [
            'кот', 'кошк', 'котен', 'котик', 'мурз', 'мяу', 'киса', 'кися',
            'котята', 'мама-кошка', 'беременная кошка', 'кастрир', 'стерилиз'
        ]
        
        dog_keywords = [
            'собак', 'щен', 'пес', 'собачк', 'щенок', 'лайк', 'овчарк',
            'дог', 'терьер', 'бульдог', 'хаски', 'лабрадор', 'дворняжка'
        ]
        
        cat_score = sum(1 for keyword in cat_keywords if keyword in text_lower)
        dog_score = sum(1 for keyword in dog_keywords if keyword in text_lower)
        
        if cat_score > dog_score:
            return 'cats'
        elif dog_score > cat_score:
            return 'dogs'
        else:
            return 'cats'  # По умолчанию кошки
    
    def filter_animal_post(self, post: Dict, animal_type: str) -> bool:
        """Фильтрует посты по типу животного"""
        if animal_type == 'all':
            return True
        return post['type'] == animal_type
    
    def extract_title(self, text: str, animal_type: str) -> str:
        """Извлекает заголовок из текста"""
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        # Ищем первую содержательную строку
        for line in lines[:3]:
            if len(line) > 15 and not line.startswith('http') and '@' not in line[:20]:
                # Очищаем от лишних символов
                title = re.sub(r'[🐱🐶🏠❤️💕🙏✨🌟⭐️🔥💫🎯📢📣‼️❗️⚡️💯]', '', line)
                title = re.sub(r'\s+', ' ', title).strip()
                
                if len(title) > 50:
                    title = title[:50] + "..."
                
                if title:
                    return title
        
        # Резервный заголовок
        emoji = '🐱' if animal_type == 'cats' else '🐶'
        return f"{emoji} {'Кошка' if animal_type == 'cats' else 'Собака'} ищет дом"
    
    def clean_description(self, text: str) -> str:
        """Очищает и форматирует описание"""
        # Удаляем номера телефонов из описания (они будут отдельно)
        clean_text = re.sub(r'(\+?[78][\s\-]?\(?9\d{2}\)?\s?[\d\s\-]{7,10})', '', text)
        
        # Удаляем username'ы
        clean_text = re.sub(r'@\w+', '', clean_text)
        
        # Удаляем ссылки
        clean_text = re.sub(r'https?://\S+', '', clean_text)
        
        # Удаляем лишние пробелы и переносы
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        
        # Ограничиваем длину
        if len(clean_text) > 300:
            clean_text = clean_text[:300] + "..."
        
        return clean_text
    
    def extract_contact(self, text: str) -> str:
        """Извлекает контактную информацию (не кликабельную)"""
        contacts = []
        
        # Username'ы
        usernames = re.findall(r'@\w+', text)
        if usernames:
            contacts.extend(usernames[:2])
        
        # Прочие контакты (не номера)
        if not contacts:
            contacts.append("См. в канале")
        
        return ' • '.join(contacts)
    
    def extract_phone_numbers(self, text: str) -> List[str]:
        """Извлекает номера телефонов для кликабельных ссылок"""
        # Расширенный паттерн для российских номеров
        patterns = [
            r'\+?7[\s\-]?\(?9\d{2}\)?\s?[\d\s\-]{7,10}',  # +7 9xx
            r'\+?8[\s\-]?\(?9\d{2}\)?\s?[\d\s\-]{7,10}',  # 8 9xx  
            r'9\d{2}[\s\-]?[\d\s\-]{7,10}',               # 9xx
        ]
        
        phones = []
        for pattern in patterns:
            found = re.findall(pattern, text)
            for phone in found:
                # Очищаем номер от лишних символов
                clean_phone = re.sub(r'[\s\-\(\)]', '', phone)
                if len(clean_phone) >= 10:  # Минимальная длина номера
                    # Приводим к стандартному виду
                    if clean_phone.startswith('8'):
                        clean_phone = '7' + clean_phone[1:]
                    elif not clean_phone.startswith('7'):
                        clean_phone = '7' + clean_phone
                    
                    phones.append(clean_phone)
        
        # Убираем дубликаты
        return list(set(phones))[:2]  # Максимум 2 номера
    
    def get_mock_posts(self, animal_type: str = 'cats') -> List[Dict]:
        """Возвращает тестовые посты"""
        if animal_type == 'dogs':
            return [
                {
                    'id': '2001',
                    'title': '🐶 Щенок ищет дом',
                    'description': 'Очень активный и дружелюбный щенок, возраст около 3 месяцев.',
                    'date': datetime.now().strftime('%d.%m.%Y %H:%M'),
                    'url': f'{self.channel["url"]}/2001',
                    'contact': 'См. в канале',
                    'phone_numbers': ['79780001122'],
                    'photo_url': 'https://via.placeholder.com/600x400/4A90E2/FFFFFF?text=Щенок',
                    'has_photo': True,
                    'type': 'dogs'
                }
            ]
        else:
            return [
                {
                    'id': '1001',
                    'title': '🐱 Котенок ищет дом',
                    'description': 'Милый котенок, очень ласковый и игривый, возраст около 2 месяцев.',
                    'date': datetime.now().strftime('%d.%m.%Y %H:%M'),
                    'url': f'{self.channel["url"]}/1001',
                    'contact': 'См. в канале',
                    'phone_numbers': ['79780001111'],
                    'photo_url': 'https://via.placeholder.com/600x400/FF6B6B/FFFFFF?text=Котенок',
                    'has_photo': True,
                    'type': 'cats'
                }
            ]
    
    def get_cached_posts(self, animal_type: str = 'all') -> List[Dict]:
        """Возвращает кэшированные или свежие посты"""
        # Обновляем кэш каждые 30 минут
        if (not self.last_update or 
            (datetime.now() - self.last_update).seconds > 1800):
            try:
                return self.get_channel_posts(animal_type)
            except:
                pass
        
        # Фильтруем кэшированные посты
        filtered_posts = [
            p for p in self.posts_cache 
            if animal_type == 'all' or p['type'] == animal_type
        ]
        
        return filtered_posts or self.get_mock_posts(animal_type)

class AnimalBot:
    """Основной класс бота с поддержкой кликабельных номеров"""
    
    def __init__(self):
        self.token = os.environ.get('TOKEN')
        if not self.token:
            logger.error("❌ TOKEN не найден в переменных окружения!")
            exit(1)
        
        self.bot = telebot.TeleBot(self.token)
        self.parser = ChannelParser()
        self.app = Flask(__name__)
        self.port = int(os.environ.get('PORT', 8080))
        self.webhook_url = os.environ.get('WEBHOOK_URL')
        self.stats = {"users": set(), "messages": 0}
        
        self.setup_handlers()
        self.setup_routes()
    
    def format_phone_for_telegram(self, phone: str) -> str:
        """Форматирует номер для отображения в Telegram"""
        if len(phone) == 11 and phone.startswith('7'):
            return f"+{phone[0]} ({phone[1:4]}) {phone[4:7]}-{phone[7:9]}-{phone[9:11]}"
        return phone
    
    def send_post(self, chat_id: int, post: Dict):
        """Отправляет пост с кликабельными номерами"""
        try:
            emoji = '🐱' if post['type'] == 'cats' else '🐶'
            
            # Формируем кликабельные номера
            phone_buttons = []
            phone_text = ""
            
            if post.get('phone_numbers'):
                for phone in post['phone_numbers']:
                    formatted_phone = self.format_phone_for_telegram(phone)
                    phone_text += f"📞 {formatted_phone}\n"
                    phone_buttons.append(
                        types.InlineKeyboardButton(
                            f"📞 {formatted_phone}", 
                            url=f"tel:+{phone}"
                        )
                    )
            
            # Текст поста
            post_text = (
                f"{emoji} <b>{post['title']}</b>\n\n"
                f"{post['description']}\n\n"
                f"📅 {post['date']}\n"
            )
            
            if phone_text:
                post_text += f"\n{phone_text}"
            
            if post.get('contact') and post['contact'] != "См. в канале":
                post_text += f"💬 {post['contact']}\n"
            
            post_text += f"\n🔗 <a href='{post['url']}'>Открыть в канале</a>"
            
            # Ограничиваем длину
            if len(post_text) > 1024:
                post_text = post_text[:1000] + "...\n\n🔗 <a href='{post['url']}'>Подробнее в канале</a>"
            
            # Создаем клавиатуру
            keyboard = types.InlineKeyboardMarkup(row_width=1)
            
            # Добавляем кнопки с номерами
            for button in phone_buttons:
                keyboard.add(button)
            
            # Добавляем кнопку канала
            keyboard.add(
                types.InlineKeyboardButton("📢 Открыть в канале", url=post['url'])
            )
            
            # Отправляем с фото или без
            if post.get('photo_url'):
                try:
                    self.bot.send_photo(
                        chat_id,
                        post['photo_url'],
                        caption=post_text,
                        parse_mode="HTML",
                        reply_markup=keyboard
                    )
                    return
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось загрузить фото: {e}")
            
            # Отправляем текстом
            self.bot.send_message(
                chat_id,
                post_text,
                parse_mode="HTML",
                disable_web_page_preview=False,
                reply_markup=keyboard
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки поста: {e}")
            self.bot.send_message(
                chat_id,
                f"❌ Ошибка отправки объявления.\n\n📢 Посетите канал: {self.parser.channel['url']}"
            )

    def send_channel_posts(self, chat_id: int, animal_type: str = 'cats'):
        """Отправляет все посты выбранного типа"""
        try:
            posts = self.parser.get_cached_posts(animal_type)
            
            if not posts:
                self.bot.send_message(
                    chat_id,
                    f"😿 Сейчас нет актуальных объявлений.\n\n"
                    f"📢 Проверьте канал: {self.parser.channel['url']}"
                )
                return
            
            # Заголовок
            animal_name = "КОШКИ" if animal_type == 'cats' else "СОБАКИ"
            emoji = '🐱' if animal_type == 'cats' else '🐶'
            
            self.bot.send_message(
                chat_id,
                f"{emoji} <b>{animal_name} ИЩУТ ДОМ</b>\n\n"
                f"📢 Свежие объявления из канала:\n"
                f"<a href='{self.parser.channel['url']}'>Лапки-ручки Ялта</a>\n\n"
                f"👇 Нажмите на номер телефона для звонка",
                parse_mode="HTML"
            )
            
            # Отправляем посты
            for i, post in enumerate(posts):
                self.send_post(chat_id, post)
                if i < len(posts) - 1:  # Пауза между постами (кроме последнего)
                    time.sleep(1)
            
            # Финальное сообщение
            self.bot.send_message(
                chat_id,
                f"💡 <b>Как помочь?</b>\n\n"
                f"🏠 <b>Взять {'кошку' if animal_type == 'cats' else 'собаку'}:</b>\n"
                f"Нажмите на номер телефона в объявлении\n\n"
                f"📢 <b>Канал:</b> {self.parser.channel['url']}\n\n"
                f"🤝 <b>Стать волонтером:</b>\nНапишите в канал или администраторам",
                parse_mode="HTML"
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки постов: {e}")
            self.bot.send_message(
                chat_id,
                f"⚠️ Ошибка загрузки объявлений\n\n"
                f"Попробуйте позже или посетите канал:\n"
                f"{self.parser.channel['url']}"
            )

    def get_main_keyboard(self):
        """Главная клавиатура"""
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add("🏠 Пристройство", "🏥 Стерилизация")
        markup.add("📞 Контакты", "ℹ️ О проекте")
        return markup
    
    def get_adoption_keyboard(self):
        """Клавиатура пристройства"""
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add("🐱 Кошки", "🐶 Собаки")
        markup.add("📝 Подать объявление", "🔙 Назад")
        return markup
    
    def get_sterilization_keyboard(self):
        """Клавиатура стерилизации"""
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("💰 Платная", "🆓 Бесплатная")
        markup.add("🔙 Назад")
        return markup

    def setup_handlers(self):
        """Настройка обработчиков сообщений"""
        
        @self.bot.message_handler(commands=['start'])
        def start_handler(message):
            self.stats["users"].add(message.from_user.id)
            self.stats["messages"] += 1
            
            welcome_text = """👋 <b>Добро пожаловать!</b>

🐾 <b>Лапки-ручки Ялта</b> - помощь животным

Что вас интересует:
🏠 <b>Пристройство</b> - кошки и собаки ищут дом
🏥 <b>Стерилизация</b> - информация о программах
📞 <b>Контакты</b> - связь с координаторами
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
            self.bot.send_message(message.chat.id, "🔄 Обновляю данные...")
            
            self.parser.posts_cache = []
            self.parser.last_update = None
            posts = self.parser.get_channel_posts()
            
            self.bot.send_message(
                message.chat.id, 
                f"✅ Обновлено!\n\n"
                f"📄 Постов: {len(posts)}\n"
                f"🖼 С фото: {sum(1 for p in posts if p['photo_url'])}\n"
                f"🐱 Кошек: {len([p for p in posts if p['type'] == 'cats'])}\n"
                f"🐶 Собак: {len([p for p in posts if p['type'] == 'dogs'])}"
            )
        
        @self.bot.message_handler(func=lambda m: True)
        def message_handler(message):
            self.stats["users"].add(message.from_user.id)
            self.stats["messages"] += 1
            
            text = message.text
            chat_id = message.chat.id
            
            try:
                if text == "🏠 Пристройство":
                    self.bot.send_message(
                        chat_id,
                        "🏠 <b>Животные ищут дом</b>\n\n"
                        "Выберите категорию:\n\n"
                        "🐱 <b>Кошки</b> - котята и взрослые кошки\n"
                        "🐶 <b>Собаки</b> - щенки и взрослые собаки\n\n"
                        "📝 <b>Подать объявление</b> - как разместить",
                        parse_mode="HTML",
                        reply_markup=self.get_adoption_keyboard()
                    )
                
                elif text in ["🐱 Кошки", "🐱 Кошки ищут дом"]:
                    self.send_channel_posts(chat_id, 'cats')
                
                elif text in ["🐶 Собаки", "🐶 Собаки ищут дом"]:
                    self.send_channel_posts(chat_id, 'dogs')
                
                elif text == "📝 Подать объявление":
                    self.bot.send_message(
                        chat_id,
                        f"📝 <b>Как подать объявление</b>\n\n"
                        f"📢 <b>Канал:</b> <a href='{self.parser.channel['url']}'>Лапки-ручки Ялта</a>\n\n"
                        f"✍️ <b>Способы подачи:</b>\n"
                        f"1️⃣ Написать в комментариях к постам канала\n"
                        f"2️⃣ Связаться с администраторами канала\n"
                        f"3️⃣ Позвонить координаторам (см. раздел Контакты)\n\n"
                        f"📋 <b>Что указать в объявлении:</b>\n"
                        f"🔹 Фото животного (желательно несколько)\n"
                        f"🔹 Возраст, пол, размер\n"
                        f"🔹 Характер и особенности\n"
                        f"🔹 Состояние здоровья\n"
                        f"🔹 Ваш контактный телефон\n"
                        f"🔹 Город/район",
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )
                
                elif text == "🏥 Стерилизация":
                    self.bot.send_message(
                        chat_id,
                        "🏥 <b>Стерилизация животных</b>\n\n"
                        "Выберите программу:\n\n"
                        "💰 <b>Платная</b> - коммерческие клиники\n"
                        "🆓 <b>Бесплатная</b> - благотворительные программы",
                        parse_mode="HTML",
                        reply_markup=self.get_sterilization_keyboard()
                    )
                
                elif text == "💰 Платная":
                    self.bot.send_message(
                        chat_id,
                        "💰 <b>ПЛАТНАЯ СТЕРИЛИЗАЦИЯ</b>\n\n"
                        "🏥 <b>Ветклиники в Ялте:</b>\n"
                        "• Клиника 1: от 2500₽ (кошки), от 4000₽ (собаки)\n"
                        "• Клиника 2: от 3000₽ (кошки), от 5000₽ (собаки)\n\n"
                        "🌟 <b>В стоимость входит:</b>\n"
                        "✅ Операция\n"
                        "✅ Наркоз\n"
                        "✅ Послеоперационный уход\n"
                        "✅ Консультация врача\n\n"
                        "💡 <b>Скидки:</b>\n
