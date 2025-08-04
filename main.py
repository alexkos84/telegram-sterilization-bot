import os
import telebot
from telebot import types
from datetime import datetime
import time
import logging
import requests
from bs4 import BeautifulSoup
import re
from typing import List, Dict, Optional

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ChannelParser:
    """Парсер канала с фильтрацией по кошкам, собакам и товарам"""
    
    def __init__(self):
        self.channel_username = 'Lapki_ruchki_Yalta_help'
        self.channel_url = f'https://t.me/{self.channel_username}'
        self.web_url = f'https://t.me/s/{self.channel_username}'
        self.headers = {'User-Agent': 'Mozilla/5.0'}
        self.posts_cache = []
        self.last_update = None

    def get_posts(self, limit: int = 10) -> List[Dict]:
        """Получение и фильтрация постов"""
        try:
            if self._should_update_cache():
                response = requests.get(self.web_url, headers=self.headers, timeout=10)
                soup = BeautifulSoup(response.text, 'html.parser')
                self.posts_cache = [self._parse_post(post) for post in soup.find_all('div', class_='tgme_widget_message')[:20]]
                self.last_update = datetime.now()

            return self.posts_cache[:limit]

        except Exception as e:
            logger.error(f"Ошибка парсинга: {str(e)}")
            return self._get_mock_posts()

    def _should_update_cache(self) -> bool:
        """Нужно ли обновлять кэш"""
        return (not self.last_update or 
                (datetime.now() - self.last_update).seconds > 1800)

    def _parse_post(self, post) -> Optional[Dict]:
        """Парсинг одного поста"""
        try:
            text_div = post.find('div', class_='tgme_widget_message_text')
            if not text_div:
                return None

            text = text_div.get_text('\n').strip()
            photo_url = self._extract_photo_url(post)
            
            return {
                'text': text,
                'photo_url': photo_url,
                'is_cat': self._is_cat(text),
                'is_dog': self._is_dog(text),
                'is_free': self._is_free(text),
                'date': self._extract_date(post)
            }

        except Exception as e:
            logger.error(f"Ошибка парсинга поста: {str(e)}")
            return None

    def _extract_photo_url(self, post) -> Optional[str]:
        """Извлечение URL фото"""
        photo_div = post.find('a', class_='tgme_widget_message_photo_wrap')
        if photo_div and 'style' in photo_div.attrs:
            match = re.search(r"url\('(.*?)'\)", photo_div['style'])
            return match.group(1) if match else None
        return None

    def _extract_date(self, post) -> str:
        """Извлечение даты"""
        time_tag = post.find('time')
        if time_tag and 'datetime' in time_tag.attrs:
            return time_tag['datetime'][:10]
        return "Недавно"

    def _is_cat(self, text: str) -> bool:
        keywords = ['кот', 'кошк', 'котен', 'котик', 'мур', 'мяу']
        return any(word in text.lower() for word in keywords)

    def _is_dog(self, text: str) -> bool:
        keywords = ['собака', 'щен', 'пес', 'пёс', 'гав', 'лай']
        return any(word in text.lower() for word in keywords)

    def _is_free(self, text: str) -> bool:
        keywords = [
            'отдам', 'даром', 'бесплатно', 'лежанка', 'корм', 
            'лоток', 'поводок', 'ошейник', 'лекарств', 'шлейк'
        ]
        return any(word in text.lower() for word in keywords)

    def _get_mock_posts(self) -> List[Dict]:
        """Тестовые данные"""
        return [
            {
                'text': "Котенок Мурзик ищет дом. Возраст 2 месяца, игривый.",
                'photo_url': 'https://via.placeholder.com/600x400?text=Котенок',
                'is_cat': True,
                'is_dog': False,
                'is_free': False,
                'date': datetime.now().strftime('%Y-%m-%d')
            },
            {
                'text': "Пес Барсик. Взрослый, привит, ищет хозяина.",
                'photo_url': 'https://via.placeholder.com/600x400?text=Собака',
                'is_cat': False,
                'is_dog': True,
                'is_free': False,
                'date': datetime.now().strftime('%Y-%m-%d')
            },
            {
                'text': "Отдам даром лежанку для собаки. Состояние хорошее.",
                'photo_url': 'https://via.placeholder.com/600x400?text=Лежанка',
                'is_cat': False,
                'is_dog': False,
                'is_free': True,
                'date': datetime.now().strftime('%Y-%m-%d')
            }
        ]

class PetsBot:
    def __init__(self):
        self.token = os.getenv('TOKEN')
        if not self.token:
            logger.error("Токен не найден!")
            exit(1)
            
        self.bot = telebot.TeleBot(self.token)
        self.parser = ChannelParser()
        
        # Регистрация обработчиков
        self.bot.message_handler(commands=['start'])(self.send_welcome)
        self.bot.message_handler(func=lambda m: m.text in ['🐱 Кошки', '🐶 Собаки', '🎁 Отдам даром'])(self.handle_category)
        self.bot.message_handler(func=lambda m: m.text == '🔙 Назад')(self.send_welcome)

    def _create_keyboard(self, include_back: bool = True) -> types.ReplyKeyboardMarkup:
        """Создание клавиатуры"""
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add('🐱 Кошки', '🐶 Собаки', '🎁 Отдам даром')
        if include_back:
            markup.add('🔙 Назад')
        return markup

    def send_welcome(self, message):
        """Приветственное сообщение"""
        self.bot.send_message(
            message.chat.id,
            "🐾 <b>Помощник для животных Ялты</b>\n\n"
            "Выберите категорию:",
            parse_mode="HTML",
            reply_markup=self._create_keyboard(include_back=False)
        )

    def handle_category(self, message):
        """Обработчик категорий"""
        if message.text == '🐱 Кошки':
            self._send_posts(message.chat.id, 'кошек', lambda p: p['is_cat'])
        elif message.text == '🐶 Собаки':
            self._send_posts(message.chat.id, 'собак', lambda p: p['is_dog'])
        elif message.text == '🎁 Отдам даром':
            self._send_posts(message.chat.id, 'товаров', lambda p: p['is_free'])

    def _send_posts(self, chat_id: int, category: str, filter_func):
        """Отправка отфильтрованных постов"""
        posts = [p for p in self.parser.get_posts() if filter_func(p)][:3]
        
        if not posts:
            self.bot.send_message(
                chat_id,
                f"😿 Нет объявлений в категории '{category}'. Попробуйте позже!",
                reply_markup=self._create_keyboard()
            )
            return

        # Отправка заголовка
        emoji = '🐱' if category == 'кошек' else '🐶' if category == 'собак' else '🎁'
        self.bot.send_message(
            chat_id,
            f"{emoji} <b>Последние объявления о {category}:</b>",
            parse_mode="HTML",
            reply_markup=self._create_keyboard()
        )

        # Отправка постов
        for post in posts:
            try:
                if post['photo_url']:
                    self.bot.send_photo(
                        chat_id,
                        post['photo_url'],
                        caption=self._format_post(post),
                        parse_mode="HTML"
                    )
                else:
                    self.bot.send_message(
                        chat_id,
                        self._format_post(post),
                        parse_mode="HTML"
                    )
                time.sleep(1)
            except Exception as e:
                logger.error(f"Ошибка отправки поста: {str(e)}")

    def _format_post(self, post: Dict) -> str:
        """Форматирование текста поста"""
        return (
            f"{post['text']}\n\n"
            f"📅 <i>{post['date']}</i>\n"
            f"🔗 <a href='{self.parser.channel_url}'>Перейти в канал</a>"
        )

    def run(self):
        """Запуск бота"""
        logger.info("Бот запущен!")
        self.bot.polling(none_stop=True)

if __name__ == '__main__':
    bot = PetsBot()
    bot.run()
