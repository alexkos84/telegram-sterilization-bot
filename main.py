import os
import telebot
from telebot import types
from datetime import datetime
import time
import logging
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

class AnimalChannelParser:
    """Универсальный парсер для каналов о животных"""
    
    def __init__(self):
        self.channels = {
            'cats': {
                'username': 'Lapki_ruchki_Yalta_help',
                'url': 'https://t.me/Lapki_ruchki_Yalta_help',
                'keywords': ['кот', 'кошк', 'котен', 'котик', 'мурз', 'мяу', 'кастр', 'стерил']
            },
            'dogs': {
                'username': 'yalta_aninmals',
                'url': 'https://t.me/yalta_aninmals',
                'keywords': ['собак', 'щен', 'пёс', 'пес', 'гав', 'лайк', 'овчарк', 'дог', 'хаск']
            }
        }
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.posts_cache = {'cats': [], 'dogs': []}
        self.last_update = None
    
    def get_channel_posts(self, animal_type: str = 'cats', limit: int = 5) -> List[Dict]:
        """Получает последние посты для указанного типа животных"""
        try:
            if animal_type not in self.channels:
                raise ValueError(f"Unknown animal type: {animal_type}")
                
            channel = self.channels[animal_type]
            web_url = f'https://t.me/s/{channel["username"]}'
            
            logger.info(f"🌐 Загрузка постов для {animal_type} с {web_url}")
            response = requests.get(web_url, headers=self.headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            message_divs = soup.find_all('div', class_='tgme_widget_message')
            
            posts = []
            for div in message_divs[:limit*2]:  # Берем в 2 раза больше для фильтрации
                post_data = self.parse_message_div(div, channel)
                if post_data and self.is_animal_related(post_data.get('text', ''), channel['keywords']):
                    posts.append(post_data)
                    if len(posts) >= limit:
                        break
            
            if posts:
                self.posts_cache[animal_type] = posts
                self.last_update = datetime.now()
                logger.info(f"✅ Получено {len(posts)} постов для {animal_type}")
            else:
                logger.warning(f"⚠️ Не найдено подходящих постов для {animal_type}")
                posts = self.get_mock_posts(animal_type)
            
            return posts
            
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга для {animal_type}: {e}")
            return self.get_mock_posts(animal_type)
    
    def parse_message_div(self, div, channel_info) -> Optional[Dict]:
        """Парсит отдельный пост"""
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
            
            # Фото
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
                'url': f"{channel_info['url']}/{post_id}" if post_id else channel_info['url'],
                'title': self.extract_title(text),
                'description': self.extract_description(text),
                'contact': self.extract_contact(text),
                'photo_url': photo_url,
                'has_photo': bool(photo_url),
                'animal_type': 'cats' if 'Lapki' in channel_info['username'] else 'dogs'
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга div: {e}")
            return None
    
    def is_animal_related(self, text: str, keywords: List[str]) -> bool:
        """Проверяет, относится ли пост к животным"""
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in keywords)
    
    def get_mock_posts(self, animal_type: str) -> List[Dict]:
        """Возвращает тестовые данные"""
        if animal_type == 'cats':
            return [{
                'id': '1001',
                'title': '🐱 Котенок ищет дом',
                'description': 'Мальчик, 2 месяца, привит. Очень ласковый.',
                'date': '01.01.2023',
                'url': self.channels['cats']['url'],
                'contact': '@cat_help',
                'photo_url': 'https://via.placeholder.com/600x400?text=Котенок',
                'animal_type': 'cats'
            }]
        else:
            return [{
                'id': '2001',
                'title': '🐶 Щенок ищет дом',
                'description': 'Девочка, 3 месяца, здорова. Хорошо ладит с детьми.',
                'date': '01.01.2023',
                'url': self.channels['dogs']['url'],
                'contact': '@dog_help',
                'photo_url': 'https://via.placeholder.com/600x400?text=Щенок',
                'animal_type': 'dogs'
            }]
    
    def get_cached_posts(self, animal_type: str) -> List[Dict]:
        """Возвращает кэшированные или новые посты"""
        if (not self.last_update or 
            (datetime.now() - self.last_update).seconds > 3600 or
            not self.posts_cache.get(animal_type)):
            return self.get_channel_posts(animal_type)
        return self.posts_cache[animal_type]

class AnimalAdoptionBot:
    """Бот для пристройства животных"""
    
    def __init__(self):
        self.token = os.environ.get('TELEGRAM_TOKEN')
        if not self.token:
            logger.error("❌ Токен бота не найден!")
            exit(1)
        
        self.bot = telebot.TeleBot(self.token)
        self.parser = AnimalChannelParser()
        
        # Загрузка текстов из файлов
        self.sterilization_texts = {
            'free': self.load_text('assets/free_sterilization.html'),
            'paid': self.load_text('assets/paid_sterilization.html')
        }
        
        self.setup_handlers()
    
    def load_text(self, file_path: str) -> str:
        """Загружает текст из файла"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки файла {file_path}: {e}")
            return f"<b>Информация временно недоступна</b>\n\nОшибка загрузки файла: {file_path}"
    
    def send_animal_posts(self, chat_id: int, animal_type: str):
        """Отправляет посты о животных"""
        try:
            posts = self.parser.get_cached_posts(animal_type)
            emoji = '🐱' if animal_type == 'cats' else '🐶'
            name = 'кошек' if animal_type == 'cats' else 'собак'
            
            if not posts:
                self.bot.send_message(
                    chat_id,
                    f"😢 Сейчас нет актуальных объявлений о {name}.\n"
                    f"Попробуйте позже или посетите канал: {self.parser.channels[animal_type]['url']}",
                    parse_mode="HTML"
                )
                return
            
            self.bot.send_message(
                chat_id,
                f"{emoji} <b>ПОСЛЕДНИЕ ОБЪЯВЛЕНИЯ</b>\n\n"
                f"Актуальные объявления о {name} из канала:",
                parse_mode="HTML"
            )
            
            for post in posts:
                self.send_post(chat_id, post)
                time.sleep(0.7)  # Чтобы не попасть в лимиты Telegram
            
            self.bot.send_message(
                chat_id,
                f"💬 <b>Как помочь?</b>\n\n"
                f"🏠 <b>Взять животное:</b> Свяжитесь по указанным контактам\n"
                f"📢 <b>Поделиться:</b> Помогите найти дом - расскажите друзьям\n"
                f"🤝 <b>Стать волонтером:</b> Напишите в канал",
                parse_mode="HTML",
                reply_markup=self.get_main_keyboard()
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки постов: {e}")
            self.bot.send_message(
                chat_id,
                "⚠️ Произошла ошибка при загрузке объявлений. Попробуйте позже.",
                reply_markup=self.get_main_keyboard()
            )
    
    def send_post(self, chat_id: int, post: Dict):
        """Отправляет один пост с кнопкой поделиться"""
        try:
            animal_emoji = '🐱' if post['animal_type'] == 'cats' else '🐶'
            post_text = (
                f"{animal_emoji} <b>{post['title']}</b>\n\n"
                f"{post['description']}\n\n"
                f"📅 {post['date']}\n"
                f"📞 {post['contact']}"
            )
            
            if len(post_text) > 1024:
                post_text = post_text[:1000] + "..."
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(
                "📢 Поделиться", 
                url=f"https://t.me/share/url?url={post['url']}&text=Помогите найти дом!"
            ))
            
            if post.get('photo_url'):
                self.bot.send_photo(
                    chat_id,
                    post['photo_url'],
                    caption=post_text,
                    parse_mode="HTML",
                    reply_markup=markup
                )
            else:
                self.bot.send_message(
                    chat_id,
                    post_text,
                    parse_mode="HTML",
                    reply_markup=markup
                )
                
        except Exception as e:
            logger.error(f"❌ Ошибка отправки поста: {e}")

    # ... (остальные методы клавиатур и обработчиков остаются аналогичными, 
    # но с учетом двух типов животных)

    def run(self):
        """Запускает бота"""
        logger.info("🐾 Запуск бота для пристройства животных...")
        try:
            self.bot.polling(none_stop=True)
        except Exception as e:
            logger.error(f"❌ Ошибка в работе бота: {e}")
            time.sleep(15)
            self.run()

if __name__ == "__main__":
    bot = AnimalAdoptionBot()
    bot.run()
