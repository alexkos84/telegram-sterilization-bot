import os
import telebot
from telebot import types
from flask import Flask, request, jsonify
from datetime import datetime, timedelta
import time
import logging
import json
import requests
from bs4 import BeautifulSoup
import re
from typing import Dict, List, Optional
import random
from urllib.parse import quote_plus
import cloudscraper
import html

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class AnimalNewsParser:
    """Парсер новостей о животных с улучшенным извлечением медиа"""
    
    def __init__(self):
        self.channels = [
            {
                'username': 'yalta_podslushano',
                'url': 'https://t.me/yalta_podslushano',
                'name': 'Ялта Подслушано'
            },
            {
                'username': 'vet_yalta',
                'url': 'https://t.me/vet_yalta',
                'name': 'ВетЯлта'
            },
            {
                'username': 'yaltaya',
                'url': 'https://t.me/yaltaya',
                'name': 'Ялтая'
            }
        ]
        
        self.animal_keywords = [
            'кошк', 'кот', 'котён', 'котен', 'котэ', 'котейк', 'кис', 'кис-кис',
            'соба', 'пёс', 'пес', 'щен', 'собак', 'псин', 'хвост', 'лап',
            'животн', 'питом', 'звер', 'зверюшк', 'зверёк', 'питомец',
            'пристр', 'потерял', 'нашел', 'найдён', 'найден', 'пропал', 'пропада',
            'приют', 'передерж', 'ветеринар', 'корм', 'стерилиз', 'кастрац'
        ]
        
        self.posts_cache = []
        self.last_update = None
        self.last_attempt = None
        self.failure_count = 0
        
        # Инициализация CloudScraper
        try:
            self.scraper = cloudscraper.create_scraper(
                browser={
                    'browser': 'chrome',
                    'platform': 'windows',
                    'mobile': False
                }
            )
        except:
            self.scraper = requests.Session()
            logger.warning("⚠️ CloudScraper недоступен, используем обычный requests")
        
        # User-Agents для ротации
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
        ]
    
    def extract_media(self, div) -> Optional[Dict]:
        """Улучшенное извлечение медиа (фото, видео, документы)"""
        try:
            # 1. Пробуем получить фото через тег img
            img = div.select_one('.tgme_widget_message_photo img[src]')
            if img and img['src'].startswith('http'):
                return {'type': 'photo', 'url': img['src']}
            
            # 2. Пробуем получить фото через background-image
            photo_wrap = div.select_one('.tgme_widget_message_photo_wrap[style*="background-image"]')
            if photo_wrap:
                style = photo_wrap.get('style', '')
                match = re.search(r"url\('([^']+)'\)", style)
                if match and match.group(1).startswith('http'):
                    return {'type': 'photo', 'url': match.group(1)}
            
            # 3. Пробуем получить видео
            video = div.select_one('video.tgme_widget_message_video[src]')
            if video and video['src'].startswith('http'):
                return {'type': 'video', 'url': video['src']}
            
            # 4. Пробуем получить документы (гифки и др.)
            doc = div.select_one('a.tgme_widget_message_document[href]')
            if doc and doc['href'].startswith('http'):
                return {'type': 'document', 'url': doc['href']}
            
            # 5. Альтернативный метод для фото (может работать для некоторых каналов)
            photo_div = div.select_one('.tgme_widget_message_photo')
            if photo_div:
                img = photo_div.select_one('img[src]')
                if img and img['src'].startswith('http'):
                    return {'type': 'photo', 'url': img['src']}
                
                # Пробуем извлечь из data-src
                img = photo_div.select_one('img[data-src]')
                if img and img['data-src'].startswith('http'):
                    return {'type': 'photo', 'url': img['data-src']}
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка при извлечении медиа: {str(e)}")
            return None
    
    def parse_message_div(self, div, channel: Dict) -> Optional[Dict]:
        """Парсинг отдельного сообщения с улучшенной обработкой медиа"""
        try:
            # ID поста
            post_id = div.get('data-post', '') or f"msg_{hash(str(div)[:100]) % 10000}"
            if '/' in str(post_id):
                post_id = str(post_id).split('/')[-1]
            
            # Текст сообщения
            text_elem = div.select_one('.tgme_widget_message_text')
            if not text_elem:
                return None
                
            text = '\n'.join([p.get_text(strip=True) for p in text_elem.find_all(['p', 'br']) if p.get_text(strip=True)])
            if not text:
                text = text_elem.get_text(separator='\n', strip=True)
            
            text = self.clean_text(text)
            if len(text) < 10:
                return None
            
            # Дата и время
            date_elem = div.select_one('.tgme_widget_message_date time')
            date_str = "Недавно"
            timestamp = 0
            
            if date_elem:
                datetime_attr = date_elem.get('datetime')
                if datetime_attr:
                    try:
                        dt = datetime.fromisoformat(datetime_attr.replace('Z', '+00:00'))
                        date_str = dt.strftime('%d.%m.%Y %H:%M')
                        timestamp = dt.timestamp()
                    except:
                        date_str = date_elem.get_text(strip=True)
            
            # Медиа (улучшенное извлечение)
            media = self.extract_media(div)
            
            return {
                'id': post_id,
                'text': text,
                'date': date_str,
                'timestamp': timestamp,
                'url': f"{channel['url']}/{post_id}",
                'channel_name': channel['name'],
                'channel_url': channel['url'],
                'media': media,
                'has_media': bool(media),
                'source': 'parsed'
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга сообщения в {channel['name']}: {str(e)}")
            return None

    # ... (остальные методы класса остаются без изменений)

class AnimalNewsBot:
    """Бот для новостей о животных с улучшенной отправкой медиа"""
    
    def send_animal_post(self, chat_id: int, post: Dict):
        """Улучшенная отправка поста с медиа"""
        try:
            # Формируем текст с информацией о канале
            post_text = (
                f"🐾 <b>{post['channel_name']}</b>\n\n"
                f"{post['text']}\n\n"
                f"📅 {post['date']}\n"
                f"🔗 <a href='{post['url']}'>Открыть в канале</a>"
            )
            
            # Обрезаем если слишком длинный
            if len(post_text) > 4000:
                lines = post_text.split('\n')
                truncated = []
                length = 0
                for line in lines:
                    if length + len(line) < 3800:
                        truncated.append(line)
                        length += len(line) + 1
                    else:
                        break
                post_text = '\n'.join(truncated) + "...\n\n🔗 Читать далее в канале"
            
            # Отправляем медиа если есть
            if post.get('has_media'):
                media = post['media']
                try:
                    if media['type'] == 'photo':
                        # Проверяем URL фото
                        if not media['url'].startswith('http'):
                            raise ValueError("Неверный URL фото")
                            
                        # Пробуем скачать фото для проверки
                        test_response = requests.head(media['url'], timeout=5)
                        if test_response.status_code != 200:
                            raise ValueError("Фото недоступно")
                            
                        self.bot.send_photo(
                            chat_id,
                            media['url'],
                            caption=post_text,
                            parse_mode="HTML",
                            reply_markup=self.get_post_markup(post['url'])
                        )
                        return
                    
                    elif media['type'] == 'video':
                        # Проверяем URL видео
                        if not media['url'].startswith('http'):
                            raise ValueError("Неверный URL видео")
                            
                        self.bot.send_video(
                            chat_id,
                            media['url'],
                            caption=post_text,
                            parse_mode="HTML",
                            reply_markup=self.get_post_markup(post['url'])
                        )
                        return
                    
                    elif media['type'] == 'document':
                        # Для документов просто отправляем ссылку
                        post_text += f"\n\n📎 Вложение: {media['url']}"
                        
                except Exception as media_error:
                    logger.error(f"⚠️ Ошибка отправки медиа: {media_error}. Пробуем отправить как текст.")
                    # Продолжаем с текстовым вариантом
            
            # Текстовая отправка (если нет медиа или не удалось отправить)
            self.bot.send_message(
                chat_id,
                post_text,
                parse_mode="HTML",
                disable_web_page_preview=False,
                reply_markup=self.get_post_markup(post['url'])
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки поста: {str(e)}")
            self.bot.send_message(
                chat_id,
                f"⚠️ Не удалось отправить пост. Вы можете посмотреть его прямо в канале:\n{post['url']}"
            )

    # ... (остальные методы класса остаются без изменений)

if __name__ == "__main__":
    print("""
🔧 Для работы бота необходимо установить зависимости:
pip install telebot flask requests beautifulsoup4 cloudscraper lxml

🔄 Запуск бота...
""")
    
    try:
        bot = AnimalNewsBot()
        bot.run()
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"💥 Ошибка запуска: {str(e)}")
        print("\n❌ Возможные причины:")
        print("1. Не установлен TOKEN в переменных окружения")
        print("2. Проблемы с сетью или доступом к Telegram API")
        print("\n🔄 Попробуйте перезапустить...")
        time.sleep(5)
