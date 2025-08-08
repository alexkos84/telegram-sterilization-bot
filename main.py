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

class GroupParser:
    """Парсер публичных Telegram групп"""
    
    def __init__(self):
        self.groups = [
            {
                'username': 'lapki_ruchki_yalta',
                'url': 'https://t.me/lapki_ruchki_yalta',
                'type': 'cats',
                'is_public': True
            },
            {
                'username': 'yalta_aninmals',
                'url': 'https://t.me/yalta_aninmals',
                'type': 'dogs',
                'is_public': True
            }
        ]
        self.posts_cache = []
        self.last_update = None
    
    def get_group_posts(self, group_type: str = 'all', limit: int = 3) -> List[Dict]:
        """Получает последние посты из групп"""
        try:
            posts = []
            for group in self.groups:
                if group_type != 'all' and group['type'] != group_type:
                    continue
                    
                if not group['is_public']:
                    logger.warning(f"Группа {group['username']} приватная, пропускаем")
                    continue
                    
                web_url = f'https://t.me/s/{group["username"]}'
                logger.info(f"Парсим группу: {web_url}")
                
                try:
                    response = requests.get(web_url, headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                    }, timeout=15)
                    response.raise_for_status()
                    
                    # Проверка что это действительно группа
                    if "This is a private Telegram group" in response.text:
                        logger.error(f"Группа {group['username']} приватная!")
                        continue
                        
                    soup = BeautifulSoup(response.text, 'html.parser')
                    messages = soup.find_all('div', class_='tgme_widget_message')
                    
                    for msg in messages[:limit]:
                        post = self.parse_message(msg, group)
                        if post:
                            posts.append(post)
                            
                except Exception as e:
                    logger.error(f"Ошибка парсинга группы {group['username']}: {str(e)}")
                    continue
            
            if posts:
                self.posts_cache = posts
                self.last_update = datetime.now()
                logger.info(f"Успешно получено {len(posts)} постов")
            else:
                logger.warning("Не найдено подходящих постов, используем мок-данные")
                posts = self.get_mock_posts(group_type)
                
            return posts
            
        except Exception as e:
            logger.error(f"Критическая ошибка: {str(e)}")
            return self.get_mock_posts(group_type)
    
    def parse_message(self, message_div, group) -> Optional[Dict]:
        """Парсит отдельное сообщение из группы"""
        try:
            # Базовые данные
            post_id = message_div.get('data-post', '').split('/')[-1]
            text_div = message_div.find('div', class_='tgme_widget_message_text')
            text = text_div.get_text('\n', strip=True) if text_div else ""
            
            # Дата
            date_elem = message_div.find('time', {'datetime': True})
            post_date = "Недавно"
            if date_elem:
                try:
                    dt = datetime.strptime(date_elem['datetime'], '%Y-%m-%dT%H:%M:%S%z')
                    post_date = dt.strftime('%d.%m.%Y %H:%M')
                except:
                    pass
            
            # Фото/медиа
            photo_url = None
            photo_wrap = message_div.find('a', class_='tgme_widget_message_photo_wrap')
            if photo_wrap and 'style' in photo_wrap.attrs:
                match = re.search(r"background-image:url\('(.*?)'\)", photo_wrap['style'])
                if match:
                    photo_url = match.group(1)
            
            if not text:
                return None
                
            return {
                'id': post_id,
                'text': text,
                'date': post_date,
                'url': f"{group['url']}/{post_id}" if post_id else group['url'],
                'title': self._extract_title(text, group['type']),
                'description': self._extract_description(text),
                'contact': self._extract_contact(text),
                'photo_url': photo_url,
                'has_photo': bool(photo_url),
                'type': group['type']
            }
            
        except Exception as e:
            logger.error(f"Ошибка парсинга сообщения: {str(e)}")
            return None
    
    def _extract_title(self, text: str, animal_type: str) -> str:
        """Извлекает заголовок из текста"""
        first_line = text.split('\n')[0].strip()
        if len(first_line) > 5:  # Минимальная длина заголовка
            return first_line[:100] + ('...' if len(first_line) > 100 else '')
        return "Кошка ищет дом" if animal_type == 'cats' else "Собака ищет дом"
    
    def _extract_description(self, text: str) -> str:
        """Извлекает основное описание"""
        clean_text = re.sub(r'(@\w+|https?://\S+|#\w+)', '', text)
        return clean_text[:300] + ('...' if len(clean_text) > 300 else '')
    
    def _extract_contact(self, text: str) -> str:
        """Извлекает контакты с кликабельными ссылками"""
        contacts = []
        
        # Телефоны
        phones = re.findall(r'(\+?[78][\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2})', text)
        for phone in phones[:2]:  # Максимум 2 телефона
            clean_phone = re.sub(r'[^\d+]', '', phone)
            contacts.append(f"<a href='tel:{clean_phone}'>{phone}</a>")
        
        # Юзернеймы
        usernames = re.findall(r'@(\w+)', text)
        for username in usernames[:2]:  # Максимум 2 юзернейма
            contacts.append(f"<a href='https://t.me/{username}'>@{username}</a>")
        
        return ', '.join(contacts) if contacts else "Контакты в группе"
    
    def get_mock_posts(self, group_type: str) -> List[Dict]:
        """Возвращает тестовые данные"""
        mock = []
        if group_type == 'cats':
            mock.append({
                'id': 'mock1',
                'title': 'Котенок ищет дом',
                'description': 'Милый котенок 2 месяца, ищет добрые руки.',
                'date': datetime.now().strftime('%d.%m.%Y %H:%M'),
                'url': 'https://t.me/lapki_ruchki_yalta',
                'contact': '<a href="tel:+79780000001">+7 978 000-00-01</a>',
                'photo_url': 'https://via.placeholder.com/600x400?text=Котенок',
                'has_photo': True,
                'type': 'cats'
            })
        else:
            mock.append({
                'id': 'mock2',
                'title': 'Щенок ищет дом',
                'description': 'Активный щенок 3 месяца, привит.',
                'date': datetime.now().strftime('%d.%m.%Y %H:%M'),
                'url': 'https://t.me/yalta_aninmals',
                'contact': '<a href="tel:+79780000002">+7 978 000-00-02</a>',
                'photo_url': 'https://via.placeholder.com/600x400?text=Щенок',
                'has_photo': True,
                'type': 'dogs'
            })
        return mock
    
    def get_cached_posts(self, group_type: str = 'all') -> List[Dict]:
        """Возвращает кэшированные посты"""
        if not self.last_update or (datetime.now() - self.last_update).seconds > 3600:
            return self.get_group_posts(group_type)
        return [p for p in self.posts_cache if group_type == 'all' or p['type'] == group_type]

class AnimalBot:
    """Бот для помощи животным"""
    
    def __init__(self):
        self.token = os.getenv('TELEGRAM_TOKEN')
        if not self.token:
            raise ValueError("Не задан TELEGRAM_TOKEN!")
            
        self.bot = telebot.TeleBot(self.token)
        self.parser = GroupParser()
        self.setup_handlers()
        
    def send_group_posts(self, chat_id: int, animal_type: str):
        """Отправляет посты из групп"""
        posts = self.parser.get_cached_posts(animal_type)
        
        if not posts:
            self.bot.send_message(
                chat_id,
                "😿 Нет свежих объявлений. Попробуйте позже.",
                reply_markup=self.main_keyboard()
            )
            return
            
        # Отправляем каждый пост
        for post in posts:
            try:
                caption = (
                    f"🐾 <b>{post['title']}</b>\n\n"
                    f"{post['description']}\n\n"
                    f"📅 {post['date']}\n"
                    f"📞 {post['contact']}\n"
                    f"🔗 <a href='{post['url']}'>Открыть в группе</a>"
                )
                
                if post.get('photo_url'):
                    self.bot.send_photo(
                        chat_id,
                        post['photo_url'],
                        caption=caption,
                        parse_mode='HTML'
                    )
                else:
                    self.bot.send_message(
                        chat_id,
                        caption,
                        parse_mode='HTML'
                    )
                    
                time.sleep(1)  # Задержка между сообщениями
                
            except Exception as e:
                logger.error(f"Ошибка отправки поста: {str(e)}")
                continue
                
        # Финальное сообщение
        group_url = next(
            (g['url'] for g in self.parser.groups if g['type'] == animal_type),
            'https://t.me/lapki_ruchki_yalta'
        )
        
        self.bot.send_message(
            chat_id,
            f"💬 Все объявления из группы: {group_url}",
            reply_markup=self.main_keyboard()
        )
    
    def main_keyboard(self):
        """Основная клавиатура"""
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.row("🐱 Кошки", "🐶 Собаки")
        markup.row("📞 Контакты", "ℹ️ Помощь")
        return markup
    
    def setup_handlers(self):
        """Настройка обработчиков команд"""
        
        @self.bot.message_handler(commands=['start'])
        def start(message):
            self.bot.send_message(
                message.chat.id,
                "🐾 Привет! Я помогу найти дом животным из Ялты.\n"
                "Выберите категорию:",
                reply_markup=self.main_keyboard()
            )
        
        @self.bot.message_handler(func=lambda m: m.text in ["🐱 Кошки", "Кошки"])
        def cats(message):
            self.send_group_posts(message.chat.id, 'cats')
        
        @self.bot.message_handler(func=lambda m: m.text in ["🐶 Собаки", "Собаки"])
        def dogs(message):
            self.send_group_posts(message.chat.id, 'dogs')
        
        @self.bot.message_handler(func=lambda m: m.text in ["📞 Контакты", "Контакты"])
        def contacts(message):
            self.bot.send_message(
                message.chat.id,
                "📞 <b>Контакты для связи:</b>\n\n"
                "🐱 Кошки: <a href='https://t.me/lapki_ruchki_yalta'>@lapki_ruchki_yalta</a>\n"
                "🐶 Собаки: <a href='https://t.me/yalta_aninmals'>@yalta_aninmals</a>\n\n"
                "☎ Телефоны:\n"
                "<a href='tel:+79781449070'>+7 978 144-90-70</a> (кошки)\n"
                "<a href='tel:+79780000002'>+7 978 000-00-02</a> (собаки)",
                parse_mode='HTML',
                reply_markup=self.main_keyboard()
            )
        
        @self.bot.message_handler(func=lambda m: m.text in ["ℹ️ Помощь", "Помощь"])
        def help(message):
            self.bot.send_message(
                message.chat.id,
                "ℹ️ <b>Как использовать бота:</b>\n\n"
                "1. Выберите 🐱 Кошки или 🐶 Собаки\n"
                "2. Бот покажет последние объявления\n"
                "3. Используйте контакты для связи\n\n"
                "Если объявлений нет - проверьте группы напрямую.",
                parse_mode='HTML',
                reply_markup=self.main_keyboard()
            )
    
    def run(self):
        """Запуск бота"""
        logger.info("Бот запущен!")
        self.bot.polling(none_stop=True)

if __name__ == '__main__':
    bot = AnimalBot()
    bot.run()
