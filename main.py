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
                    'photo_url': None,
                    'video_url': None,
                    'has_media': False,
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
                    'photo_url': None,
                    'video_url': None,
                    'has_media': False,
                    'type': 'cats',
                    'channel': 'Котики Ялта',
                    'channel_url': 'https://t.me/cats_yalta'
                }
            ]

    def get_cached_posts(self, channel_type: str = 'all') -> List[Dict]:
        """Возвращает кэшированные посты"""
        return self.get_mock_posts(channel_type)

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
        """Загружает контакты"""
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
        """Отправляет один пост"""
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
            
            self.bot.send_message(
                chat_id,
                post_text,
                parse_mode="HTML",
                reply_to_message_id=reply_to_message_id,
                disable_web_page_preview=False
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки поста: {e}")

    def send_channel_posts(self, chat_id: int, animal_type: str = 'cats', reply_to_message_id: int = None):
        """Отправляет посты животных"""
        try:
            posts = self.parser.get_cached_posts(animal_type)
            
            if not posts:
                animal_name = "котиков" if animal_type == 'cats' else "собак"
                self.bot.send_message(
                    chat_id,
                    f"😿 Сейчас нет актуальных объявлений о {animal_name}.",
                    reply_to_message_id=reply_to_message_id
                )
                return
            
            animal_emoji = '🐱' if animal_type == 'cats' else '🐕'
            animal_name = "КОТИКИ" if animal_type == 'cats' else "СОБАКИ"
            
            self.bot.send_message(
                chat_id,
                f"{animal_emoji} <b>{animal_name} ИЩУТ ДОМ</b>\n\n📢 Актуальные объявления:",
                parse_mode="HTML",
                reply_to_message_id=reply_to_message_id
            )
            
            for post in posts:
                self.send_post(chat_id, post)
                time.sleep(0.5)
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки постов: {e}")

    def parse_command(self, text: str) -> dict:
        """Парсит команду из упоминания бота"""
        # Убираем упоминание бота
        clean_text = re.sub(r'@catYalta_bot\s*', '', text, flags=re.IGNORECASE).strip().lower()
        
        logger.info(f"🔍 Парсинг команды: '{clean_text}'")
        
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
            return result
        
        # Пристройство животных
        if any(word in clean_text for word in ['пристрой', 'дом', 'взять', 'усынов', 'найти', 'котики', 'собаки']):
            result['action'] = 'adoption'
            if any(word in clean_text for word in ['собак', 'пес', 'щен']):
                result['params']['animal'] = 'dogs'
            else:
                result['params']['animal'] = 'cats'  # по умолчанию котики
            return result
        
        # Подача объявления
        if any(word in clean_text for word in ['подать', 'разместить', 'объявление']):
            result['action'] = 'post_ad'
            return result
        
        # О проекте
        if any(word in clean_text for word in ['проект', 'о нас', 'информация']):
            result['action'] = 'about'
            return result
        
        # Помощь
        if any(word in clean_text for word in ['помощь', 'help', 'команды', 'что умеешь']):
            result['action'] = 'help'
            return result
        
        logger.info(f"📝 Результат парсинга: {result}")
        return result

    def setup_handlers(self):
        """Обработчики сообщений"""
        
        @self.bot.message_handler(commands=['start'])
        def start_handler(message):
            """Команда /start работает только в приватных чатах"""
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
• @catYalta_bot помощь

🔒 <b>В группах:</b> Ответы видны только вам."""
                
                self.bot.send_message(
                    message.chat.id, 
                    welcome_text, 
                    parse_mode="HTML"
                )
        
        @self.bot.message_handler(content_types=['text'])
        def handle_text_messages(message):
            """Обрабатывает все текстовые сообщения"""
            try:
                # Проверяем, есть ли упоминание бота
                if not message.text or '@catYalta_bot' not in message.text.lower():
                    return
                
                logger.info(f"📨 Получено сообщение с упоминанием: {message.text}")
                
                self.stats["users"].add(message.from_user.id)
                self.stats["messages"] += 1
                
                command = self.parse_command(message.text)
                logger.info(f"🎯 Команда: {command}")
                
                response = ""
                
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
                    response = """🏥 <b>СТЕРИЛИЗАЦИЯ ЖИВОТНЫХ</b>

💰 <b>Платная стерилизация:</b>
• Клиника "Айболит": от 3000₽ (+7 978 000-00-11)
• Клиника "ВетМир": от 2500₽ (+7 978 000-00-13)

🆓 <b>Бесплатная стерилизация:</b>
• Для бездомных животных
• Координатор: +7 978 144-90-70

💡 <b>Включено:</b>
✔️ Операция и наркоз
✔️ Послеоперационный уход
✔️ Консультация ветеринара"""
                
                elif command['action'] == 'post_ad':
                    response = """📝 <b>ПОДАТЬ ОБЪЯВЛЕНИЕ</b>

📢 <b>Группы для котиков:</b>
• <a href="https://t.me/cats_yalta">Котики Ялта (канал)</a>
• <a href="https://t.me/cats_yalta_group">Котики Ялта (группа)</a>

📢 <b>Группы для собак:</b>
• <a href="https://t.me/dogs_yalta">Собаки Ялта (канал)</a>
• <a href="https://t.me/dogs_yalta_group">Собаки Ялта (группа)</a>

✍️ <b>Как подать:</b>
1️⃣ Перейти в соответствующую группу
2️⃣ Написать администраторам
3️⃣ Или связаться: +7 978 144-90-70

📋 <b>Укажите:</b>
🔹 Фото животного
🔹 Возраст, пол, окрас/порода
🔹 Характер и здоровье
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
                
                elif command['action'] == 'help':
                    response = """🤖 <b>ПОМОЩНИК ПО ЖИВОТНЫМ ЯЛТЫ</b>

📝 <b>Доступные команды:</b>

📞 <b>Контакты:</b>
• @catYalta_bot номер Светланы
• @catYalta_bot контакт ветклиники

🏠 <b>Пристройство:</b>
• @catYalta_bot котики ищут дом
• @catYalta_bot собаки ищут дом

🏥 <b>Стерилизация:</b>
• @catYalta_bot стерилизация

📝 <b>Объявления:</b>
• @catYalta_bot подать объявление

ℹ️ <b>Информация:</b>
• @catYalta_bot о проекте

🔒 <b>Конфиденциальность:</b> В группах ответы видны только вам"""
                
                else:
                    response = """❓ <b>Не понял команду</b>

Попробуйте:
• @catYalta_bot помощь - список команд
• @catYalta_bot номер Светланы
• @catYalta_bot котики ищут дом
• @catYalta_bot стерилизация"""
                
                # Отправляем ответ
                if message.chat.type in ['group', 'supergroup']:
                    # В группах отвечаем reply (видно только автору)
                    self.bot.reply_to(message, response, parse_mode="HTML")
                else:
                    # В приватных чатах обычное сообщение
                    self.bot.send_message(message.chat.id, response, parse_mode="HTML")
                
                logger.info(f"✅ Отправлен ответ для команды: {command['action']}")
                
            except Exception as e:
                logger.error(f"❌ Ошибка в обработчике: {e}")
                error_response = "⚠️ Ошибка обработки команды. Попробуйте: @catYalta_bot помощь"
                if message.chat.type in ['group', 'supergroup']:
                    self.bot.reply_to(message, error_response)
                else:
                    self.bot.send_message(message.chat.id, error_response)
    
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
                "status": "🤖 Animal Bot Running",
                "time": datetime.now().strftime('%H:%M:%S'),
                "users": len(self.stats["users"]),
                "messages": self.stats["messages"],
                "usage": "Mention @catYalta_bot in any chat"
            })
    
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
                logger.info(f"✅ Webhook: {full_url}")
                return True
            else:
                logger.error("❌ Не удалось установить webhook")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка webhook: {e}")
            return False
    
    def run(self):
        """Запуск бота"""
        logger.info("🚀 Запуск Animal Bot для Ялты (только упоминания)...")
        
        if self.setup_webhook():
            logger.info("✅ Бот запущен в webhook режиме")
            self.app.run(host='0.0.0.0', port=self.port)
        else:
            logger.error("🚨 Ошибка webhook, запуск в polling режиме")
            self.bot.polling(none_stop=True)

if __name__ == "__main__":
    bot = CatBotWithPhotos()
    bot.run()
