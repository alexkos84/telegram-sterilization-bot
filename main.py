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
                'title': 'Котики Ялта'
            },
            {
                'username': 'dogs_yalta',
                'url': 'https://t.me/dogs_yalta',
                'type': 'dogs',
                'title': 'Собаки Ялта'
            }
        ]
        self.posts_cache = []
        self.last_update = None
    
    def get_channel_posts(self, channel_type: str = 'all', limit: int = 5) -> List[Dict]:
        """Получает последние посты из каналов"""
        try:
            posts = []
            for channel in self.channels:
                if channel_type != 'all' and channel['type'] != channel_type:
                    continue
                    
                web_url = f'https://t.me/s/{channel["username"]}'
                logger.info(f"Загрузка постов с {web_url}")
                response = requests.get(web_url, timeout=15)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.content, 'html.parser')
                message_divs = soup.find_all('div', class_='tgme_widget_message')
                
                for div in message_divs[:limit*2]:
                    post_data = self.parse_message_div(div, channel)
                    if post_data:
                        posts.append(post_data)
                        if len(posts) >= limit:
                            break
            
            posts.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
            return posts[:limit]
            
        except Exception as e:
            logger.error(f"Ошибка парсинга: {e}")
            return []

    def parse_message_div(self, div, channel) -> Optional[Dict]:
        """Парсит пост"""
        try:
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
            
            # Медиа
            photo_url = None
            photo_wrap = div.find('a', class_='tgme_widget_message_photo_wrap')
            if photo_wrap and photo_wrap.get('style'):
                match = re.search(r"background-image:url\('(.*?)'\)", photo_wrap['style'])
                if match:
                    photo_url = match.group(1)
            
            return {
                'id': post_id,
                'text': text,
                'date': date_str,
                'url': f"{channel['url']}/{post_id}",
                'channel': channel['title'],
                'channel_url': channel['url'],
                'photo_url': photo_url
            }
            
        except Exception as e:
            logger.error(f"Ошибка парсинга: {e}")
            return None

class AnimalBot:
    """Бот для помощи животным в Ялте"""
    
    def __init__(self):
        self.token = os.environ.get('TOKEN')
        if not self.token:
            logger.error("❌ TOKEN не найден!")
            exit(1)
        
        self.bot = telebot.TeleBot(self.token)
        self.parser = AdvancedChannelParser()
        self.contacts = self.load_contacts()
        
        self.setup_handlers()
    
    def load_contacts(self) -> dict:
        """Загружает контакты из JSON"""
        try:
            with open('assets/contacts.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки контактов: {e}")
            return {
                "контакты": {
                    "светлана": "+7 978 123-45-67",
                    "ветклиника": "ул. Кирова, 15",
                    "собаки": "@dogs_yalta"
                },
                "синонимы": {
                    "света": "светлана",
                    "клиника": "ветклиника"
                }
            }

    def setup_handlers(self):
        """Настройка обработчиков"""
        
        @self.bot.message_handler(func=lambda m: m.text and '@catYalta_bot' in m.text)
        def handle_mention(message):
            try:
                query = message.text.lower().replace('@catyalta_bot', '').strip()
                contacts = self.contacts["контакты"]
                synonyms = self.contacts["синонимы"]
                
                # Поиск контакта
                response = None
                for name, contact in contacts.items():
                    if name in query:
                        response = f"📞 {name.capitalize()}: {contact}"
                        break
                
                # Проверка синонимов
                if not response:
                    for syn, original in synonyms.items():
                        if syn in query:
                            response = f"📞 {original.capitalize()}: {contacts[original]}"
                            break
                
                if not response:
                    response = "🤷 Контакт не найден. Попробуйте: 'Светлана', 'Ветклиника'"
                
                # Отправляем ответ только автору
                self.bot.reply_to(
                    message,
                    response,
                    disable_notification=True
                )
                
            except Exception as e:
                logger.error(f"Ошибка: {e}")
                self.bot.reply_to(message, "⚠️ Ошибка обработки запроса")

    def run(self):
        """Запуск бота"""
        logger.info("🚀 Бот запущен")
        self.bot.polling()

if __name__ == "__main__":
    # Создаем папку assets если её нет
    os.makedirs('assets', exist_ok=True)
    
    # Создаем файл контактов если его нет
    if not os.path.exists('assets/contacts.json'):
        with open('assets/contacts.json', 'w', encoding='utf-8') as f:
            json.dump({
                "контакты": {
                    "светлана": "+7 978 123-45-67 (координатор)",
                    "ветклиника": "ул. Кирова, 15, тел. +7 978 000-11-22",
                    "собаки": "@dogs_yalta (группа по собакам)"
                },
                "синонимы": {
                    "света": "светлана",
                    "клиника": "ветклиника"
                }
            }, f, ensure_ascii=False, indent=4)

    bot = AnimalBot()
    bot.run()
