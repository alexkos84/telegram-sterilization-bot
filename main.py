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
import signal
import sys

# 🔧 Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Отключаем излишние логи от requests и urllib
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

class BotManager:
    """Менеджер для управления состоянием бота и предотвращения конфликтов"""
    
    def __init__(self, token: str):
        self.token = token
        self.bot = None
        self.webhook_set = False
        self.polling_active = False
        
    def create_bot_instance(self):
        """Создает новый экземпляр бота"""
        if self.bot:
            try:
                self.bot.stop_polling()
                self.bot.remove_webhook()
            except:
                pass
        
        self.bot = telebot.TeleBot(self.token, threaded=True, skip_pending=True)
        return self.bot
    
    def cleanup_bot_state(self):
        """Очищает состояние бота перед новым запуском"""
        try:
            # Создаем временный бот для очистки
            temp_bot = telebot.TeleBot(self.token)
            
            logger.info("🧹 Очистка состояния бота...")
            
            # Удаляем webhook
            result = temp_bot.remove_webhook()
            logger.info(f"📡 Webhook удален: {result}")
            
            # Ждем немного для завершения операций
            time.sleep(3)
            
            # Получаем и пропускаем pending updates
            try:
                updates = temp_bot.get_updates(timeout=1)
                if updates:
                    last_update_id = updates[-1].update_id
                    temp_bot.get_updates(offset=last_update_id + 1, timeout=1)
                    logger.info(f"⏭️ Пропущено {len(updates)} старых обновлений")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось очистить старые обновления: {e}")
            
            del temp_bot
            
        except Exception as e:
            logger.error(f"❌ Ошибка очистки состояния: {e}")
    
    def setup_webhook_safe(self, webhook_url: str) -> bool:
        """Безопасная настройка webhook"""
        try:
            if not self.bot:
                return False
            
            self.cleanup_bot_state()
            
            # Устанавливаем webhook
            full_url = f"https://{webhook_url}/{self.token}"
            result = self.bot.set_webhook(
                url=full_url,
                max_connections=10,
                drop_pending_updates=True  # Важно: удаляем старые обновления
            )
            
            if result:
                self.webhook_set = True
                logger.info(f"✅ Webhook установлен: {full_url}")
                return True
            else:
                logger.error("❌ Не удалось установить webhook")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка настройки webhook: {e}")
            return False
    
    def start_polling_safe(self):
        """Безопасный запуск polling"""
        try:
            if not self.bot:
                return False
            
            self.cleanup_bot_state()
            
            logger.info("📱 Запуск в режиме polling...")
            self.polling_active = True
            
            # Запускаем polling с параметрами для избежания конфликтов
            self.bot.infinity_polling(
                timeout=20,
                long_polling_timeout=20,
                skip_pending=True,  # Пропускаем старые сообщения
                none_stop=True,
                interval=1
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка polling: {e}")
            self.polling_active = False
            raise
    
    def stop_bot(self):
        """Останавливает бота"""
        try:
            if self.bot:
                if self.polling_active:
                    logger.info("⏹️ Остановка polling...")
                    self.bot.stop_polling()
                    self.polling_active = False
                
                if self.webhook_set:
                    logger.info("⏹️ Удаление webhook...")
                    self.bot.remove_webhook()
                    self.webhook_set = False
                
        except Exception as e:
            logger.error(f"❌ Ошибка остановки бота: {e}")

# Ваш существующий MultiChannelParser остается без изменений
class MultiChannelParser:
    """Парсер множественных каналов с животными"""
    
    def __init__(self):
        # 📋 Список каналов для парсинга
        self.channels = [
            {
                'username': 'Котики_Ялта',
                'url': 'https://t.me/cats_yalta',
                'type': 'cats',
                'priority': 1
            },
            {
                'username': 'dogs_yalta_official',
                'url': 'https://t.me/dogs_yalta_official', 
                'type': 'dogs',
                'priority': 1
            },
            {
                'username': 'yalta_animals_help',
                'url': 'https://t.me/yalta_animals_help',
                'type': 'all',
                'priority': 2
            },
            {
                'username': 'crimea_pets_adoption',
                'url': 'https://t.me/crimea_pets_adoption',
                'type': 'all',
                'priority': 2
            }
        ]
        
        self.posts_cache = {'cats': [], 'dogs': [], 'all': []}
        self.last_update = {}
        self.update_lock = Lock()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
    
    # Все остальные методы MultiChannelParser остаются без изменений
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
            for div in message_divs[:10]:
                post_data = self.parse_message_div(div, channel)
                if post_data and self.is_animal_related(post_data.get('text', '')):
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
    
    def get_cached_posts(self, channel_type: str = 'all') -> List[Dict]:
        """Возвращает тестовые посты (для демонстрации)"""
        # Возвращаем mock данные для тестирования
        if channel_type == 'cats':
            return [
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
                }
            ]
        else:  # dogs
            return [
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
    
    # Добавьте остальные методы из предыдущего кода...
    def detect_animal_type(self, text: str) -> str:
        """Определяет тип животного"""
        text_lower = text.lower()
        cat_keywords = ['кот', 'кошк', 'котен', 'котик', 'мурз', 'мяу']
        dog_keywords = ['собак', 'щен', 'пес', 'гав', 'лайк', 'овчарк']
        
        cat_count = sum(1 for word in cat_keywords if word in text_lower)
        dog_count = sum(1 for word in dog_keywords if word in text_lower)
        
        return 'cats' if cat_count > dog_count else 'dogs'
    
    def is_animal_related(self, text: str) -> bool:
        """Проверяет связь с животными"""
        keywords = ['кот', 'кошк', 'котен', 'собак', 'щен', 'пес', 'животн', 'питомец']
        return any(keyword in text.lower() for keyword in keywords)
    
    def parse_message_div(self, div, channel) -> Optional[Dict]:
        """Парсит отдельный пост"""
        try:
            text_div = div.find('div', class_='tgme_widget_message_text')
            text = text_div.get_text(strip=True) if text_div else ""
            
            if not text:
                return None
            
            return {
                'id': f"mock_{int(time.time())}",
                'text': text,
                'date': datetime.now().strftime('%d.%m.%Y %H:%M'),
                'url': f"{channel['url']}/123",
                'title': text[:50] + "..." if len(text) > 50 else text,
                'description': text,
                'contact': "См. в канале",
                'photo_url': None,
                'has_photo': False,
                'type': channel.get('type', 'all'),
                'source_channel': channel['username']
            }
        except:
            return None

# Обновленный главный класс бота
class CatBotWithPhotos:
    """Бот с исправлением конфликтов"""
    
    def __init__(self):
        self.token = os.environ.get('TOKEN')
        if not self.token:
            logger.error("❌ TOKEN не найден!")
            sys.exit(1)
        
        # Используем BotManager для безопасного управления
        self.bot_manager = BotManager(self.token)
        self.bot = self.bot_manager.create_bot_instance()
        
        self.parser = MultiChannelParser()
        self.app = Flask(__name__)
        self.port = int(os.environ.get('PORT', 8080))
        self.webhook_url = os.environ.get('WEBHOOK_URL')
        self.stats = {"users": set(), "messages": 0}
        
        # Настройка обработчика сигналов для graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        self.setup_handlers()
        self.setup_routes()
    
    def signal_handler(self, signum, frame):
        """Обработчик сигналов для корректного завершения"""
        logger.info(f"🛑 Получен сигнал {signum}, завершение работы...")
        self.bot_manager.stop_bot()
        sys.exit(0)
    
    def send_post(self, chat_id: int, post: Dict):
        """Отправляет один пост"""
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
            
            self.bot.send_message(
                chat_id,
                post_text,
                parse_mode="HTML",
                disable_web_page_preview=False
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки поста: {e}")
    
    def send_channel_posts(self, chat_id: int, animal_type: str = 'cats'):
        """Отправляет посты"""
        try:
            posts = self.parser.get_cached_posts(animal_type)
            
            if not posts:
                self.bot.send_message(
                    chat_id,
                    f"😿 Сейчас нет актуальных объявлений типа '{animal_type}'"
                )
                return
            
            header_text = f"{'🐱 КОШКИ' if animal_type == 'cats' else '🐶 СОБАКИ'} ИЩУТ ДОМ\n\nНайдено объявлений: {len(posts)}"
            self.bot.send_message(chat_id, header_text, parse_mode="HTML")
            
            for post in posts:
                self.send_post(chat_id, post)
                time.sleep(0.5)
                
        except Exception as e:
            logger.error(f"❌ Ошибка отправки постов: {e}")
            self.bot.send_message(chat_id, "⚠️ Ошибка загрузки объявлений")
    
    def get_main_keyboard(self):
        """Главная клавиатура"""
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add("🏠 Пристройство", "📞 Контакты")
        return markup
    
    def setup_handlers(self):
        """Обработчики сообщений"""
        
        @self.bot.message_handler(commands=['start'])
        def start_handler(message):
            self.stats["users"].add(message.from_user.id)
            self.stats["messages"] += 1
            
            welcome_text = """👋 <b>Добро пожаловать!</b>

🐾 Помощник по животным Ялты
✅ Исправлена проблема с конфликтами

Выберите раздел:"""
            
            self.bot.send_message(
                message.chat.id, 
                welcome_text, 
                parse_mode="HTML",
                reply_markup=self.get_main_keyboard()
            )
        
        @self.bot.message_handler(commands=['status'])
        def status_handler(message):
            status_text = f"""📊 <b>СТАТУС БОТА</b>

🤖 Состояние: Активен ✅
📡 Webhook: {'Установлен' if self.bot_manager.webhook_set else 'Не установлен'}
📱 Polling: {'Активен' if self.bot_manager.polling_active else 'Неактивен'}
👥 Пользователей: {len(self.stats['users'])}
📨 Сообщений: {self.stats['messages']}
⏰ Время: {datetime.now().strftime('%H:%M:%S')}"""
            
            self.bot.send_message(message.chat.id, status_text, parse_mode="HTML")
        
        @self.bot.message_handler(func=lambda m: m.text == "🏠 Пристройство")
        def adoption_handler(message):
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.add("🐱 Кошки", "🐶 Собаки")
            markup.add("🔙 Назад")
            
            self.bot.send_message(
                message.chat.id,
                "🏠 <b>Выберите тип животного:</b>",
                parse_mode="HTML",
                reply_markup=markup
            )
        
        @self.bot.message_handler(func=lambda m: m.text == "🐱 Кошки")
        def cats_handler(message):
            self.send_channel_posts(message.chat.id, 'cats')
        
        @self.bot.message_handler(func=lambda m: m.text == "🐶 Собаки")
        def dogs_handler(message):
            self.send_channel_posts(message.chat.id, 'dogs')
        
        @self.bot.message_handler(func=lambda m: m.text == "📞 Контакты")
        def contacts_handler(message):
            contacts_text = """📞 <b>КОНТАКТЫ</b>

👥 Координаторы:
🔹 Кошки: +7 978 144-90-70
🔹 Собаки: +7 978 234-56-78

🏥 Клиники:
🔹 "Айболит": +7 978 456-78-90"""
            
            self.bot.send_message(message.chat.id, contacts_text, parse_mode="HTML")
        
        @self.bot.message_handler(func=lambda m: m.text == "🔙 Назад")
        def back_handler(message):
            self.bot.send_message(
                message.chat.id,
                "🏠 Главное меню:",
                reply_markup=self.get_main_keyboard()
            )
        
        @self.bot.message_handler(func=lambda m: True)
        def default_handler(message):
            self.bot.send_message(
                message.chat.id,
                "❓ Используйте кнопки меню\n\n/start - главное меню\n/status - статус бота",
                reply_markup=self.get_main_keyboard()
            )
    
    def setup_routes(self):
        """Flask маршруты"""
        
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
                "status": "🤖 Bot Running (Conflict Fixed)",
                "time": datetime.now().strftime('%H:%M:%S'),
                "webhook_set": self.bot_manager.webhook_set,
                "polling_active": self.bot_manager.polling_active,
                "users": len(self.stats["users"]),
                "messages": self.stats["messages"]
            })
        
        @self.app.route('/health')
        def health():
            return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})
    
    def run(self):
        """Запуск бота с исправлением конфликтов"""
        logger.info("🚀 Запуск Animal Bot (версия с исправлением конфликтов)...")
        
        try:
            # Выбираем режим работы
            if self.webhook_url:
                logger.info("🌐 Попытка запуска с webhook...")
                if self.bot_manager.setup_webhook_safe(self.webhook_url):
                    logger.info(f"🌐 Сервер запущен на порту {self.port}")
                    self.app.run(host='0.0.0.0', port=self.port, debug=False)
                else:
                    logger.warning("⚠️ Webhook не удался, переключение на polling...")
                    self.bot_manager.start_polling_safe()
            else:
                logger.info("📱 Запуск в режиме polling...")
                self.bot_manager.start_polling_safe()
                
        except KeyboardInterrupt:
            logger.info("👋 Бот остановлен пользователем")
        except Exception as e:
            logger.error(f"🚨 Критическая ошибка: {e}")
            raise
        finally:
            self.bot_manager.stop_bot()

if __name__ == "__main__":
    try:
        bot = CatBotWithPhotos()
        bot.run()
    except Exception as e:
        logger.error(f"🚨 Ошибка запуска: {e}")
        sys.exit(1)
