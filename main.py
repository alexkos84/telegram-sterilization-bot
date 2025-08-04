import os
import telebot
from telebot import types
from datetime import datetime
import time
import logging
import requests
from bs4 import BeautifulSoup
import re

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ChannelParser:
    """Парсер канала для кошек и собак"""
    def __init__(self):
        self.channel_username = 'Lapki_ruchki_Yalta_help'
        self.channel_url = f'https://t.me/{self.channel_username}'
        self.web_url = f'https://t.me/s/{self.channel_username}'
        self.headers = {'User-Agent': 'Mozilla/5.0'}
        self.posts_cache = []
    
    def get_posts(self, limit=5):
        """Получение постов с фильтрацией"""
        try:
            response = requests.get(self.web_url, headers=self.headers)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            posts = []
            for message in soup.find_all('div', class_='tgme_widget_message')[:limit*2]:
                post = self._parse_message(message)
                if post:
                    posts.append(post)
            
            self.posts_cache = posts
            return posts
        
        except Exception as e:
            logger.error(f"Ошибка парсинга: {str(e)}")
            return self._get_mock_posts()

    def _parse_message(self, message):
        """Парсинг одного сообщения"""
        try:
            text_div = message.find('div', class_='tgme_widget_message_text')
            if not text_div:
                return None
                
            text = text_div.get_text('\n').strip()
            is_cat = self._is_cat(text)
            is_dog = self._is_dog(text)
            
            if not (is_cat or is_dog):
                return None
                
            # Парсинг фото
            photo_style = message.find('a', class_='tgme_widget_message_photo_wrap').get('style', '')
            photo_url = re.search(r"url\('(.*?)'\)", photo_style).group(1) if photo_style else None
            
            return {
                'text': text,
                'photo_url': photo_url,
                'is_cat': is_cat,
                'is_dog': is_dog,
                'date': message.find('time')['datetime'][:10]
            }
            
        except Exception as e:
            logger.error(f"Ошибка парсинга сообщения: {str(e)}")
            return None
    
    def _is_cat(self, text):
        keywords = ['кот', 'кошк', 'котен', 'котик', 'мяу']
        return any(word in text.lower() for word in keywords)
    
    def _is_dog(self, text):
        keywords = ['собака', 'щен', 'пес', 'пёс', 'гав']
        return any(word in text.lower() for word in keywords)
    
    def _get_mock_posts(self):
        """Тестовые данные"""
        return [
            {
                'text': "Котенок Мурзик ищет дом. Возраст 2 месяца.",
                'photo_url': 'https://via.placeholder.com/600x400?text=Котенок',
                'is_cat': True,
                'is_dog': False,
                'date': datetime.now().strftime('%Y-%m-%d')
            },
            {
                'text': "Пес Барсик ищет хозяина. Взрослый, добрый.",
                'photo_url': 'https://via.placeholder.com/600x400?text=Собака',
                'is_cat': False,
                'is_dog': True,
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
        self.bot.message_handler(func=lambda m: m.text == '🐱 Кошки')(self.send_cats)
        self.bot.message_handler(func=lambda m: m.text == '🐶 Собаки')(self.send_dogs)
        
    def send_welcome(self, message):
        """Приветственное сообщение"""
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add('🐱 Кошки', '🐶 Собаки')
        self.bot.send_message(
            message.chat.id,
            "🐾 Выберите раздел:",
            reply_markup=markup
        )
    
    def send_animal_posts(self, chat_id, is_cat=True):
        """Отправка постов с животными"""
        animal_type = 'кошек' if is_cat else 'собак'
        posts = [p for p in self.parser.get_posts() if p['is_cat'] == is_cat]
        
        if not posts:
            self.bot.send_message(
                chat_id,
                f"😿 Нет объявлений о {animal_type}. Попробуйте позже!"
            )
            return
            
        self.bot.send_message(
            chat_id,
            f"🐱 Последние объявления о {animal_type}:" if is_cat else f"🐶 Последние объявления о {animal_type}:"
        )
        
        for post in posts[:3]:  # Ограничим 3 постами
            if post['photo_url']:
                try:
                    self.bot.send_photo(
                        chat_id,
                        post['photo_url'],
                        caption=f"{post['text']}\n\n📅 {post['date']}"
                    )
                except Exception as e:
                    logger.error(f"Ошибка отправки фото: {str(e)}")
                    self._send_text_post(chat_id, post)
            else:
                self._send_text_post(chat_id, post)
            
            time.sleep(1)  # Задержка между отправками
    
    def _send_text_post(self, chat_id, post):
        """Отправка текстового поста"""
        self.bot.send_message(
            chat_id,
            f"{post['text']}\n\n📅 {post['date']}"
        )
    
    def send_cats(self, message):
        """Обработчик для кошек"""
        self.send_animal_posts(message.chat.id, is_cat=True)
    
    def send_dogs(self, message):
        """Обработчик для собак"""
        self.send_animal_posts(message.chat.id, is_cat=False)
    
    def run(self):
        """Запуск бота"""
        logger.info("Бот запущен!")
        self.bot.polling(none_stop=True)

if __name__ == '__main__':
    bot = PetsBot()
    bot.run()
