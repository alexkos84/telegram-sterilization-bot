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

# 🔧 Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class AvitoAnimalsParser:
    """Парсер объявлений о животных с Avito"""
    
    def __init__(self):
        self.base_url = "https://www.avito.ru"
        self.search_urls = {
            'cats': '/rossiya/zhivotnye/koshki?q=отдам+в+добрые+руки',
            'dogs': '/rossiya/zhivotnye/sobaki?q=отдам+в+добрые+руки'
        }
        self.posts_cache = []
        self.last_update = None
        self.failure_count = 0
        
        # Настройка сессии для обхода блокировок
        self.session = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'mobile': False
            }
        )
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        })
    
    def get_group_posts(self, animal_type: str = 'cats', limit: int = 5) -> List[Dict]:
        """Получение объявлений с Avito"""
        try:
            url = f"{self.base_url}{self.search_urls.get(animal_type, self.search_urls['cats'])}"
            logger.info(f"🌐 Парсинг Avito: {url}")
            
            response = self.session.get(url, timeout=15)
            if response.status_code != 200:
                logger.error(f"Ошибка HTTP {response.status_code}")
                return []
            
            soup = BeautifulSoup(response.text, 'html.parser')
            items = soup.find_all('div', {'data-marker': 'item'})
            
            posts = []
            for item in items[:limit]:
                post = self.parse_item(item, animal_type)
                if post:
                    posts.append(post)
            
            self.posts_cache = posts
            self.last_update = datetime.now()
            return posts
            
        except Exception as e:
            logger.error(f"Ошибка парсинга Avito: {str(e)}")
            self.failure_count += 1
            return []
    
    def parse_item(self, item, animal_type: str) -> Optional[Dict]:
        """Парсинг отдельного объявления"""
        try:
            title_elem = item.find('h3', {'itemprop': 'name'})
            title = title_elem.text.strip() if title_elem else "Без названия"
            
            url_elem = item.find('a', {'itemprop': 'url'})
            url = f"{self.base_url}{url_elem['href']}" if url_elem else ""
            
            price_elem = item.find('meta', {'itemprop': 'price'})
            price = price_elem['content'] if price_elem else "Договорная"
            
            desc_elem = item.find('div', {'class': re.compile('description')})
            description = desc_elem.text.strip() if desc_elem else ""
            
            date_elem = item.find('div', {'data-marker': 'item-date'})
            date = date_elem.text.strip() if date_elem else "Сегодня"
            
            img_elem = item.find('img', {'itemprop': 'image'})
            img_url = img_elem['src'] if img_elem else ""
            
            location_elem = item.find('div', {'class': re.compile('geo-root')})
            location = location_elem.text.strip() if location_elem else ""
            
            return {
                'id': hash(url) % 1000000,
                'title': title,
                'description': description,
                'text': f"{title}\n{description}\nЦена: {price}\nМесто: {location}",
                'date': date,
                'url': url,
                'photo_url': img_url,
                'has_photo': bool(img_url),
                'price': price,
                'location': location,
                'type': animal_type,
                'source': 'avito'
            }
            
        except Exception as e:
            logger.error(f"Ошибка парсинга объявления: {str(e)}")
            return None
    
    def get_cached_posts(self, animal_type: str = 'cats') -> List[Dict]:
        """Получение кэшированных объявлений"""
        if not self.posts_cache or (datetime.now() - self.last_update).seconds > 3600:
            return self.get_group_posts(animal_type)
        return [p for p in self.posts_cache if p['type'] == animal_type]

class CatBotWithPhotos:
    def __init__(self):
        self.token = os.environ.get('TOKEN')
        if not self.token:
            logger.error("❌ TOKEN не найден!")
            exit(1)
        
        self.bot = telebot.TeleBot(self.token)
        self.parser = AvitoAnimalsParser()
        self.app = Flask(__name__)
        self.port = int(os.environ.get('PORT', 8080))
        self.webhook_url = os.environ.get('WEBHOOK_URL')
        self.stats = {"users": set(), "messages": 0}
        
        self.setup_handlers()
        self.setup_routes()
    
    def send_post(self, chat_id: int, post: Dict):
        """Отправляет одно объявление с фото или текстом"""
        try:
            emoji = '🐱' if post['type'] == 'cats' else '🐶'
            price = f"💰 {post['price']}" if post['price'] != "Договорная" else "💰 Цена: договорная"
            
            post_text = (
                f"{emoji} <b>{post['title']}</b>\n\n"
                f"{post['description']}\n\n"
                f"{price}\n"
                f"📍 {post['location']}\n"
                f"📅 {post['date']}\n"
                f"🔗 <a href='{post['url']}'>Открыть на Avito</a>"
            )
            
            if len(post_text) > 1024:
                post_text = post_text[:1000] + "..."
            
            if post.get('photo_url'):
                try:
                    self.bot.send_photo(
                        chat_id,
                        post['photo_url'],
                        caption=post_text,
                        parse_mode="HTML",
                        reply_markup=types.InlineKeyboardMarkup().add(
                            types.InlineKeyboardButton("📢 Открыть на Avito", url=post['url'])
                        )
                    )
                    return
                except Exception as e:
                    logger.error(f"❌ Ошибка отправки фото: {e}")
            
            self.bot.send_message(
                chat_id,
                post_text,
                parse_mode="HTML",
                disable_web_page_preview=False,
                reply_markup=types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton("📢 Открыть на Avito", url=post['url'])
                )
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки поста: {e}")

    def send_group_posts(self, chat_id: int, animal_type: str = 'cats'):
        """Отправляет все объявления"""
        try:
            posts = self.parser.get_cached_posts(animal_type)
            
            if not posts:
                self.bot.send_message(
                    chat_id,
                    "😿 Сейчас нет доступных объявлений.\n"
                    f"Попробуйте позже или проверьте Avito напрямую"
                )
                return
            
            animal_name = "кошек" if animal_type == 'cats' else "собак"
            header_text = (
                f"🐾 <b>Объявления о {animal_name} с Avito</b>\n\n"
                f"Найдено объявлений: {len(posts)}\n"
                f"Последнее обновление: {self.parser.last_update.strftime('%H:%M') if self.parser.last_update else 'никогда'}"
            )
            
            self.bot.send_message(chat_id, header_text, parse_mode="HTML")
            
            for post in posts:
                self.send_post(chat_id, post)
                time.sleep(0.5)
            
            footer_text = (
                "💡 <b>Как помочь животным:</b>\n\n"
                f"🏠 <b>Взять {animal_name[:-1]}у:</b>\n"
                "Свяжитесь с автором объявления\n\n"
                f"📢 <b>Актуальные объявления:</b>\n"
                f"<a href='{self.parser.base_url}{self.parser.search_urls[animal_type]}'>Смотреть на Avito</a>\n\n"
                "🔄 <b>Обновить данные:</b> /update"
            )
            
            self.bot.send_message(chat_id, footer_text, parse_mode="HTML")
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки постов: {e}")
            self.bot.send_message(
                chat_id,
                f"⚠️ Ошибка загрузки объявлений\n\n"
                f"Попробуйте позже или посетите Avito:\n"
                f"{self.parser.base_url}{self.parser.search_urls.get(animal_type, '')}"
            )

    # Остальные методы класса CatBotWithPhotos остаются без изменений
    # (get_main_keyboard, get_adoption_keyboard, get_sterilization_keyboard,
    # load_html_file, setup_handlers, setup_routes, setup_webhook, run)

    def setup_handlers(self):
        """Обработчики команд и сообщений"""
        
        @self.bot.message_handler(commands=['start'])
        def start_handler(message):
            self.stats["users"].add(message.from_user.id)
            self.stats["messages"] += 1
            
            welcome_text = """👋 <b>Добро пожаловать!</b>

🐾 Помощник по животным с Avito

Выберите раздел:
🏥 <b>Стерилизация</b> - информация о программах
🏠 <b>Пристройство</b> - животные ищут дом  
📞 <b>Контакты</b> - связь с волонтерами
ℹ️ <b>О проекте</b> - наша деятельность

<i>💡 Бот показывает объявления с Avito</i>"""
            
            self.bot.send_message(
                message.chat.id, 
                welcome_text, 
                parse_mode="HTML",
                reply_markup=self.get_main_keyboard()
            )
        
        @self.bot.message_handler(commands=['update'])
        def update_handler(message):
            """Принудительное обновление объявлений"""
            self.parser.posts_cache = []
            self.parser.last_update = None
            
            self.bot.send_message(message.chat.id, "🔄 Обновление объявлений с Avito...")
            
            try:
                posts = self.parser.get_group_posts('cats', 5)
                self.bot.send_message(
                    message.chat.id,
                    f"✅ Обновлено {len(posts)} объявлений",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"❌ Ошибка обновления: {e}")
                self.bot.send_message(
                    message.chat.id, 
                    f"❌ Ошибка обновления: {str(e)[:100]}"
                )
        
        # Остальные обработчики остаются без изменений
        # (sterilization_handler, paid_sterilization_handler, free_sterilization_handler,
        # adoption_handler, cats_handler, dogs_handler, post_ad_handler,
        # contacts_handler, about_handler, back_handler, default_handler)

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
                "status": "🤖 Avito Animals Bot",
                "version": "2.0",
                "time": datetime.now().strftime('%H:%M:%S'),
                "users": len(self.stats["users"]), 
                "messages": self.stats["messages"],
                "parser": {
                    "cached_posts": len(self.parser.posts_cache),
                    "last_update": self.parser.last_update.isoformat() if self.parser.last_update else None,
                    "failure_count": self.parser.failure_count
                }
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
        logger.info("🚀 Запуск Avito Animals Bot...")
        
        try:
            posts = self.parser.get_group_posts('cats')
            logger.info(f"✅ Предзагружено {len(posts)} объявлений")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка предзагрузки: {e}")
        
        if self.setup_webhook():
            logger.info("🌐 Запуск в webhook режиме")
            self.app.run(host='0.0.0.0', port=self.port, debug=False)
        else:
            logger.info("🔄 Запуск в polling режиме")
            try:
                self.bot.polling(none_stop=True, interval=0, timeout=20)
            except Exception as e:
                logger.error(f"❌ Ошибка polling: {e}")
                time.sleep(5)
                self.bot.polling()

if __name__ == "__main__":
    # Создание необходимых файлов и папок
    os.makedirs('assets', exist_ok=True)
    
    # Создание информационных файлов (остается без изменений)
    if not os.path.exists('assets/free_text.html'):
        with open('assets/free_text.html', 'w', encoding='utf-8') as f:
            f.write("""<b>🆓 БЕСПЛАТНАЯ СТЕРИЛИЗАЦИЯ</b>

🏥 <b>Доступные программы:</b>
🔹 Муниципальная программа города Ялты
🔹 Благотворительные фонды защиты животных
🔹 Волонтерские программы стерилизации
🔹 Акции ветеринарных клиник

📋 <b>Условия участия:</b>
✅ Бездомные и полубездомные животные
✅ Животные из малоимущих семей (справка о доходах)
✅ По направлению волонтерских организаций
✅ Социально незащищенные граждане (пенсионеры, инвалиды)

📞 <b>Контакты для записи:</b>
🔹 Координатор программы: +7 978 144-90-70
🔹 Клиника "Айболит": +7 978 000-00-11  
🔹 Ветцентр "Зооветсервис": +7 978 000-00-15
🔹 Группа волонтеров: @yalta_free_sterilization

📍 <b>Адреса участвующих клиник:</b>
🏥 ул. Кирова, 15 (пн-пт 9:00-18:00)
🏥 ул. Ленина, 32 (пн-сб 8:00-20:00)  
🏥 ул. Чехова, 45 (пн-вс 9:00-19:00)

📋 <b>Необходимые документы:</b>
📄 Справка о доходах (для льготников)
📄 Направление от волонтеров (для бездомных животных)
📄 Паспорт владельца
📄 Справка о регистрации (для местных жителей)

⚠️ <b>Важно знать:</b>
⏰ Запись строго заранее! Места ограничены
📅 Программа действует круглый год
🔄 Повторные операции не входят в программу
💉 Дополнительные процедуры оплачиваются отдельно

🆘 <b>Экстренные случаи:</b>
При травмах и неотложных состояниях - немедленно обращайтесь в ветклиники!""")

    if not os.path.exists('assets/paid_text.html'):
        with open('assets/paid_text.html', 'w', encoding='utf-8') as f:
            f.write("""<b>💰 ПЛАТНАЯ СТЕРИЛИЗАЦИЯ</b>

🏥 <b>Ветеринарные клиники Ялты:</b>

🔹 <b>Клиника "Айболит"</b>
   💰 Кошки: от 3000₽ | Коты: от 2500₽
   💰 Собаки (сучки): от 5000₽ | Собаки (кобели): от 4000₽  
   📞 +7 978 000-00-12
   📍 ул. Московская, 14
   ⏰ пн-вс 8:00-20:00

🔹 <b>Ветцентр "ВетМир"</b>  
   💰 Кошки: от 2500₽ | Коты: от 2000₽
   💰 Собаки (сучки): от 4500₽ | Собаки (кобели): от 3500₽
   📞 +7 978 000-00-13  
   📍 ул. Пушкина, 28
   ⏰ пн-сб 9:00-19:00

🔹 <b>Клиника "Зооветцентр"</b>
   💰 Кошки: от 3500₽ | Коты: от 2800₽  
   💰 Собаки (сучки): от 5500₽ | Собаки (кобели): от 4200₽
   📞 +7 978 000-00-14
   📍 ул. Чехова, 45  
   ⏰ пн-вс 9:00-21:00

🔹 <b>Ветклиника "ПетВет"</b>
   💰 Кошки: от 2800₽ | Коты: от 2200₽
   💰 Собаки (сучки): от 4800₽ | Собаки (кобели): от 3800₽
   📞 +7 978 000-00-16
   📍 ул. Толстого, 12
   ⏰ пн-пт 8:00-18:00, сб 9:00-15:00

🌟 <b>В стоимость операции включено:</b>
✔️ Полноценная хирургическая операция
✔️ Качественный ингаляционный наркоз  
✔️ Послеоперационный стационар (4-6 часов)
✔️ Первичная консультация ветеринара
✔️ Повторный осмотр через 7-10 дней
✔️ Попона/воротник для послеоперационного периода

💊 <b>Дополнительно оплачиваются:</b>
🔸 Предоперационные анализы крови: от 800₽  
🔸 УЗИ органов: от 1200₽
🔸 Чипирование: от 1500₽
🔸 Дополнительные препараты: по назначению

💡 <b>Действующие скидки:</b>
🎯 Постоянным клиникам - 10%
🎯 Волонтерам и опекунам бездомных - 20%  
🎯 При стерилизации 2+ животных - 15%
🎯 Пенсионерам и студентам - 10%
🎯 Сезонные акции (май, октябрь) - до 25%

📅 <b>Запись на операцию:</b>
⏰ Рекомендуется запись за 1-2 недели
📋 При записи уточняйте все детали и стоимость
💉 Животное должно быть здоровым и привитым

⚠️ <b>Подготовка к операции:</b>  
🍽️ Голодная диета 12 часов до операции
💧 Ограничение воды за 4 часа  
🚿 Гигиенические процедуры накануне
📋 Принести все документы о прививках

🆘 <b>Экстренная помощь:</b>
При осложнениях после операции немедленно обращайтесь в клинику!""")

    # Запуск бота
    try:
        logger.info("🚀 Инициализация Avito Animals Bot...")
        bot = CatBotWithPhotos()
        bot.run()
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"💥 Критическая ошибка запуска: {e}")
        print("\n❌ Возможные причины:")
        print("1. Не установлен TOKEN в переменных окружения")
        print("2. Отсутствуют зависимости: pip install -r requirements.txt")
        print("3. Проблемы с сетью или доступом к Avito")
        print("\n🔄 Попробуйте перезапустить через 30 секунд...")
        time.sleep(30)
