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

class RobustTelegramParser:
    """Устойчивый парсер с несколькими методами обхода блокировок"""
    
    def __init__(self):
        self.groups = [
            {
                'username': 'lapki_ruchki_yalta',
                'url': 'https://t.me/lapki_ruchki_yalta',
                'type': 'cats'
            },
            {
                'username': 'yalta_aninmals',
                'url': 'https://t.me/yalta_aninmals',
                'type': 'dogs'
            }
        ]
        self.posts_cache = []
        self.last_update = None
        self.last_attempt = None
        self.failure_count = 0
        
        # Создаем CloudScraper сессию для обхода Cloudflare
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
        
        # Ротация User-Agents
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
        ]
        
        # Прокси-сервисы (если нужны)
        self.proxy_services = [
            # Можно добавить публичные прокси
        ]
    
    def should_attempt_parsing(self) -> bool:
        """Определяет, стоит ли пытаться парсить (защита от спама)"""
        if not self.last_attempt:
            return True
        
        # Если много неудач, увеличиваем интервал
        cooldown_minutes = min(self.failure_count * 5, 60)  # максимум час
        time_passed = (datetime.now() - self.last_attempt).total_seconds() / 60
        
        return time_passed > cooldown_minutes
    
    def get_advanced_headers(self):
        """Продвинутые заголовки для обхода детекции"""
        return {
            'User-Agent': random.choice(self.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
            'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"'
        }
    
    def get_group_posts(self, group_type: str = 'all', limit: int = 3) -> List[Dict]:
        """Главный метод получения постов с множественными стратегиями"""
        self.last_attempt = datetime.now()
        
        if not self.should_attempt_parsing():
            logger.info(f"⏳ Парсинг пропущен (кулдаун: {self.failure_count * 5} мин)")
            return self.get_smart_mock_posts(group_type, limit)
        
        posts = []
        success = False
        
        # Стратегия 1: CloudScraper с продвинутыми заголовками
        posts = self.try_cloudscraper_method(group_type, limit)
        if posts:
            success = True
        
        # Стратегия 2: Множественные попытки с задержками
        if not success:
            posts = self.try_multiple_attempts(group_type, limit)
            if posts:
                success = True
        
        # Стратегия 3: Альтернативные URL форматы
        if not success:
            posts = self.try_alternative_urls(group_type, limit)
            if posts:
                success = True
        
        if success:
            self.posts_cache = posts
            self.last_update = datetime.now()
            self.failure_count = max(0, self.failure_count - 1)  # Уменьшаем счетчик неудач
            logger.info(f"✅ Успешно получено {len(posts)} постов")
        else:
            self.failure_count += 1
            logger.warning(f"❌ Парсинг неудачен (попытка #{self.failure_count})")
            posts = self.get_smart_mock_posts(group_type, limit)
        
        return posts
    
    def try_cloudscraper_method(self, group_type: str, limit: int) -> List[Dict]:
        """Попытка через CloudScraper"""
        try:
            posts = []
            
            for group in self.groups:
                if group_type != 'all' and group['type'] != group_type:
                    continue
                
                url = f'https://t.me/s/{group["username"]}'
                logger.info(f"🌐 CloudScraper: {url}")
                
                # Настраиваем scraper
                self.scraper.headers.update(self.get_advanced_headers())
                
                # Делаем запрос с таймаутом
                response = self.scraper.get(url, timeout=20)
                
                if response.status_code == 200:
                    group_posts = self.parse_html_content(response.text, group, limit)
                    if group_posts:
                        posts.extend(group_posts)
                        logger.info(f"✅ CloudScraper: получено {len(group_posts)} постов")
                else:
                    logger.warning(f"⚠️ CloudScraper: HTTP {response.status_code}")
                
                # Пауза между группами
                time.sleep(random.uniform(2, 5))
            
            return posts
            
        except Exception as e:
            logger.error(f"❌ CloudScraper ошибка: {e}")
            return []
    
    def try_multiple_attempts(self, group_type: str, limit: int) -> List[Dict]:
        """Множественные попытки с разными настройками"""
        try:
            posts = []
            
            for group in self.groups:
                if group_type != 'all' and group['type'] != group_type:
                    continue
                
                # 3 попытки для каждой группы
                for attempt in range(3):
                    try:
                        session = requests.Session()
                        session.headers.update(self.get_advanced_headers())
                        
                        # Разные URL форматы
                        urls = [
                            f'https://t.me/s/{group["username"]}',
                            f'https://telegram.me/s/{group["username"]}'
                        ]
                        
                        for url in urls:
                            logger.info(f"🔄 Попытка {attempt + 1}: {url}")
                            
                            response = session.get(
                                url, 
                                timeout=15,
                                allow_redirects=True
                            )
                            
                            if response.status_code == 200:
                                group_posts = self.parse_html_content(response.text, group, limit)
                                if group_posts:
                                    posts.extend(group_posts)
                                    logger.info(f"✅ Попытка {attempt + 1}: получено {len(group_posts)} постов")
                                    break
                            
                            # Пауза между попытками
                            time.sleep(random.uniform(1, 3))
                        
                        if posts:
                            break  # Если получили посты, переходим к следующей группе
                            
                    except requests.RequestException as e:
                        logger.warning(f"⚠️ Попытка {attempt + 1} неудачна: {e}")
                        time.sleep(random.uniform(2, 4))
                        continue
                
                # Большая пауза между группами
                time.sleep(random.uniform(3, 7))
            
            return posts
            
        except Exception as e:
            logger.error(f"❌ Множественные попытки: {e}")
            return []
    
    def try_alternative_urls(self, group_type: str, limit: int) -> List[Dict]:
        """Альтернативные методы доступа"""
        # Здесь можно добавить:
        # - RSS фиды (если доступны)
        # - API через прокси
        # - Кэшированные версии
        logger.info("🔄 Пробуем альтернативные методы...")
        return []
    
    def parse_html_content(self, html: str, group: Dict, limit: int) -> List[Dict]:
        """Улучшенный парсинг HTML"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Проверяем, что страница загружена нормально
            if "Cloudflare" in html or "checking your browser" in html.lower():
                logger.warning("⚠️ Cloudflare блокировка обнаружена")
                return []
            
            if len(html) < 1000:
                logger.warning("⚠️ Слишком короткий HTML ответ")
                return []
            
            # Ищем сообщения
            message_selectors = [
                'div.tgme_widget_message',
                'div[data-post]',
                'div.tgme_widget_message_wrap',
                '.tgme_widget_message'
            ]
            
            messages = []
            for selector in message_selectors:
                found = soup.select(selector)
                if found and len(found) > 0:
                    messages = found
                    logger.info(f"✅ Найдено {len(found)} сообщений: {selector}")
                    break
            
            if not messages:
                logger.warning("❌ Сообщения не найдены в HTML")
                # Сохраняем HTML для отладки (первые 500 символов)
                logger.debug(f"HTML preview: {html[:500]}")
                return []
            
            posts = []
            processed = 0
            
            for msg_div in messages:
                if processed >= limit * 2:  # Ограничиваем обработку
                    break
                
                post_data = self.parse_message_div(msg_div, group)
                if post_data:
                    # Дополнительная фильтрация
                    if (self.is_valid_post(post_data, group['type']) and
                        len(post_data.get('text', '')) > 30):
                        posts.append(post_data)
                        if len(posts) >= limit:
                            break
                
                processed += 1
            
            logger.info(f"✅ Обработано {processed} сообщений, получено {len(posts)} постов")
            return posts
            
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга HTML: {e}")
            return []
    
    def parse_message_div(self, div, group) -> Optional[Dict]:
        """Парсинг отдельного сообщения"""
        try:
            # ID поста
            post_id = (div.get('data-post', '') or 
                      div.get('data-message-id', '') or
                      f"msg_{hash(str(div)[:100]) % 10000}")
            
            if '/' in str(post_id):
                post_id = str(post_id).split('/')[-1]
            
            # Текст сообщения
            text = self.extract_text(div)
            if not text or len(text) < 20:
                return None
            
            # Дата
            date_str = self.extract_date(div)
            
            # Фото
            photo_url = self.extract_photo(div)
            
            # Формируем результат
            return {
                'id': post_id,
                'text': text,
                'date': date_str,
                'url': f"{group['url']}/{post_id}",
                'title': self.extract_smart_title(text, group['type']),
                'description': self.extract_smart_description(text),
                'contact': self.extract_contact(text),
                'photo_url': photo_url,
                'has_photo': bool(photo_url),
                'type': group['type'],
                'source': 'parsed'
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга сообщения: {e}")
            return None
    
    def extract_text(self, div) -> str:
        """Извлечение текста из div"""
        # Пробуем разные селекторы для текста
        text_selectors = [
            '.tgme_widget_message_text',
            'div.tgme_widget_message_text',
            '.message_text',
            '.text'
        ]
        
        for selector in text_selectors:
            text_elem = div.select_one(selector)
            if text_elem:
                text = text_elem.get_text(separator=' ', strip=True)
                if text:
                    return text
        
        # Если не нашли, берем весь текст из div
        full_text = div.get_text(separator=' ', strip=True)
        
        # Очищаем от служебных элементов
        cleaned = re.sub(r'(Views|Просмотров|Subscribe|Подписаться).*$', '', full_text, flags=re.IGNORECASE)
        
        return cleaned if len(cleaned) > 20 else full_text
    
    def extract_date(self, div) -> str:
        """Извлечение даты"""
        date_selectors = ['time[datetime]', '.tgme_widget_message_date time', 'time']
        
        for selector in date_selectors:
            date_elem = div.select_one(selector)
            if date_elem:
                datetime_attr = date_elem.get('datetime')
                if datetime_attr:
                    try:
                        # Парсим ISO datetime
                        dt = datetime.fromisoformat(datetime_attr.replace('Z', '+00:00'))
                        return dt.strftime('%d.%m.%Y %H:%M')
                    except:
                        pass
                
                # Пробуем текст элемента
                date_text = date_elem.get_text(strip=True)
                if date_text:
                    return date_text
        
        return "Недавно"
    
    def extract_photo(self, div) -> Optional[str]:
        """Извлечение URL фото"""
        # Селекторы для фото
        photo_selectors = [
            '.tgme_widget_message_photo_wrap[style*="background-image"]',
            'a.tgme_widget_message_photo_wrap[style*="background-image"]',
            'img[src]',
            '[data-src]'
        ]
        
        for selector in photo_selectors:
            photo_elem = div.select_one(selector)
            if photo_elem:
                # Из style background-image
                style = photo_elem.get('style', '')
                if 'background-image' in style:
                    match = re.search(r"background-image:url\('([^']+)'\)", style)
                    if match:
                        return match.group(1)
                
                # Из src или data-src
                for attr in ['src', 'data-src']:
                    url = photo_elem.get(attr)
                    if url and url.startswith('http'):
                        return url
        
        return None
    
    def extract_smart_title(self, text: str, animal_type: str) -> str:
        """Умное извлечение заголовка"""
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        # Ищем строки с ключевыми словами
        keywords = ['ищет', 'дом', 'пристрой', 'отда', 'найден', 'потерял']
        
        for line in lines[:5]:
            if len(line) > 15 and any(keyword in line.lower() for keyword in keywords):
                # Очищаем от лишнего
                title = re.sub(r'[^\w\s\-\.,!?а-яёА-ЯЁ]', ' ', line)
                title = re.sub(r'\s+', ' ', title).strip()
                
                if len(title) > 60:
                    title = title[:60] + "..."
                
                return title
        
        # Дефолтный заголовок
        defaults = {
            'cats': ['Кошка ищет дом', 'Котенок в добрые руки', 'Пристройство кошки'],
            'dogs': ['Собака ищет дом', 'Щенок в добрые руки', 'Пристройство собаки']
        }
        
        return random.choice(defaults.get(animal_type, defaults['cats']))
    
    def extract_smart_description(self, text: str) -> str:
        """Умное извлечение описания"""
        # Удаляем контакты и ссылки для чистого описания
        clean_text = re.sub(r'(@\w+|https?://\S+|\+?[78][\d\s\-\(\)]{10,})', '', text)
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        
        # Ограничиваем длину, сохраняя целые предложения
        if len(clean_text) > 150:
            sentences = clean_text.split('.')
            result = ""
            for sentence in sentences:
                if len(result + sentence + '.') <= 150:
                    result += sentence.strip() + '. '
                else:
                    break
            return result.strip() or clean_text[:150] + "..."
        
        return clean_text
    
    def extract_contact(self, text: str) -> str:
        """Извлечение контактов"""
        contacts = []
        
        # Российские телефоны
        phone_patterns = [
            r'\+?7[\s\-]?\(?9\d{2}\)?\s?[\d\s\-]{7,10}',
            r'\+?8[\s\-]?\(?9\d{2}\)?\s?[\d\s\-]{7,10}',
            r'9\d{2}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}'
        ]
        
        for pattern in phone_patterns:
            phones = re.findall(pattern, text)
            if phones:
                # Очищаем номер от лишних символов
                clean_phone = re.sub(r'[\s\-\(\)]', '', phones[0])
                contacts.append(f"+7{clean_phone[-10:]}" if not clean_phone.startswith(('+7', '+8')) else clean_phone)
                break
        
        # Username
        usernames = re.findall(r'@\w+', text)
        if usernames:
            contacts.append(usernames[0])
        
        return ' • '.join(contacts[:2]) if contacts else "См. в группе"
    
    def is_valid_post(self, post: Dict, animal_type: str) -> bool:
        """Проверка валидности поста"""
        text = post.get('text', '').lower()
        
        # Ключевые слова для животных
        if animal_type == 'cats':
            animal_keywords = ['кот', 'кошк', 'котен', 'мурз', 'мяу', 'питомец']
        else:
            animal_keywords = ['собак', 'щен', 'пес', 'лай', 'питомец']
        
        # Ключевые слова для пристройства
        action_keywords = ['ищет', 'дом', 'пристрой', 'отда', 'найден', 'семь', 'хозя']
        
        # Исключающие слова
        exclude_keywords = ['продам', 'куплю', 'услуг', 'реклам', 'спам']
        
        has_animal = any(keyword in text for keyword in animal_keywords)
        has_action = any(keyword in text for keyword in action_keywords)
        has_exclude = any(keyword in text for keyword in exclude_keywords)
        
        return has_animal and has_action and not has_exclude and len(text) > 30
    
    def get_smart_mock_posts(self, group_type: str, limit: int) -> List[Dict]:
        """Умные моки с реалистичными данными"""
        if group_type == 'cats':
            mock_data = [
                {
                    'names': ['Мурка', 'Барсик', 'Снежок', 'Рыжик', 'Тишка', 'Пушок'],
                    'ages': ['2 месяца', '3-4 месяца', '6 месяцев', '1 год', '2 года'],
                    'colors': ['рыжий', 'серый', 'черный', 'белый', 'трехцветная', 'полосатый'],
                    'traits': ['игривый', 'ласковый', 'спокойный', 'умный', 'дружелюбный'],
                    'health': ['привит', 'здоров', 'кастрирован', 'стерилизована', 'обработан от паразитов']
                }
            ]
        else:
            mock_data = [
                {
                    'names': ['Бобик', 'Шарик', 'Дружок', 'Лайка', 'Джек', 'Белка'],
                    'ages': ['3 месяца', '4-5 месяцев', '6 месяцев', '1 год', '2 года'],
                    'colors': ['черный', 'коричневый', 'белый', 'рыжий', 'пятнистый'],
                    'traits': ['активный', 'дружелюбный', 'умный', 'послушный', 'энергичный'],
                    'health': ['привит', 'здоров', 'кастрирован', 'чипирован', 'обработан от паразитов']
                }
            ]
        
        posts = []
        data = mock_data[0]
        
        for i in range(limit):
            name = random.choice(data['names'])
            age = random.choice(data['ages'])
            color = random.choice(data['colors'])
            trait = random.choice(data['traits'])
            health = random.choice(data['health'])
            
            animal_emoji = '🐱' if group_type == 'cats' else '🐶'
            animal_name = 'кот' if group_type == 'cats' else 'щенок'
            
            # Генерируем реалистичный текст
            description = f"{animal_name.capitalize()} {name}, возраст {age}, {color} окрас. {trait.capitalize()}, {health}. К лотку приучен, с другими животными ладит. Ищет заботливую семью!"
            
            posts.append({
                'id': f'mock_{i + 1000}',
                'title': f'{animal_emoji} {name} ищет дом',
                'description': description,
                'text': description,
                'date': self.generate_recent_date(),
                'url': f'https://t.me/lapki_ruchki_yalta/{i + 1000}',
                'contact': self.generate_realistic_contact(),
                'photo_url': f'https://picsum.photos/400/300?random={i + 100}',
                'has_photo': True,
                'type': group_type,
                'source': 'mock'
            })
        
        return posts
    
    def generate_recent_date(self) -> str:
        """Генерация недавней даты"""
        days_ago = random.randint(0, 5)
        hours_ago = random.randint(0, 23)
        recent_date = datetime.now() - timedelta(days=days_ago, hours=hours_ago)
        return recent_date.strftime('%d.%m.%Y %H:%M')
    
    def generate_realistic_contact(self) -> str:
        """Генерация реалистичных контактов"""
        phone_endings = ['45-67', '78-90', '12-34', '56-78', '90-12', '23-45']
        usernames = ['volunteer', 'helper', 'animals_yal', 'pet_help', 'rescue']
        
        contacts = []
        
        # Телефон
        phone = f"+7 978 {random.choice(phone_endings)}"
        contacts.append(phone)
        
        # Username (иногда)
        if random.choice([True, False]):
            username = f"@{random.choice(usernames)}{random.randint(1, 99)}"
            contacts.append(username)
        
        return ' • '.join(contacts)
    
    def get_cached_posts(self, group_type: str = 'all') -> List[Dict]:
        """Получение кэшированных постов с умным обновлением"""
        # Обновляем каждые 30 минут, но только если есть шанс на успех
        should_update = (
            not self.last_update or 
            (datetime.now() - self.last_update).seconds > 1800
        )
        
        if should_update and self.should_attempt_parsing():
            logger.info("🔄 Время обновления постов...")
            try:
                fresh_posts = self.get_group_posts(group_type, 3)
                if fresh_posts:
                    return fresh_posts
            except Exception as e:
                logger.error(f"❌ Ошибка обновления: {e}")
        
        # Возвращаем кэш или моки
        cached = [p for p in self.posts_cache 
                 if group_type == 'all' or p['type'] == group_type]
        
        if cached:
            return cached
        else:
            return self.get_smart_mock_posts(group_type, 3)

# Остальная часть кода бота остается без изменений...
# Просто меняем RobustTelegramParser вместо AdvancedGroupParser

class CatBotWithPhotos:
    def __init__(self):
        self.token = os.environ.get('TOKEN')
        if not self.token:
            logger.error("❌ TOKEN не найден!")
            exit(1)
        
        self.bot = telebot.TeleBot(self.token)
        self.parser = RobustTelegramParser()  # Используем устойчивый парсер
        self.app = Flask(__name__)
        self.port = int(os.environ.get('PORT', 8080))
        self.webhook_url = os.environ.get('WEBHOOK_URL')
        self.stats = {"users": set(), "messages": 0}
        
        self.setup_handlers()
        self.setup_routes()
    
    def send_post(self, chat_id: int, post: Dict):
        """Отправляет один пост с фото или текстом"""
        try:
            emoji = '🐱' if post['type'] == 'cats' else '🐶'
            
            # Индикатор источника данных
            if post.get('source') == 'parsed':
                source_tag = ' 📡'  # Реальные данные
                status = "✅ Актуальное"
            else:
                source_tag = ' 🎭'  # Моки
                status = "⚠️ Пример"
            
            post_text = (
                f"{emoji} <b>{post['title']}</b>{source_tag}\n\n"
                f"{post['description']}\n\n"
                f"📅 {post['date']}\n"
                f"📞 {post['contact']}\n"
                f"🔗 <a href='{post['url']}'>Открыть в группе</a>\n\n"
                f"<i>{status}</i>"
            )
            
            if len(post_text) > 1024:
                post_text = post_text[:1000] + "..."
            
            # Пробуем отправить с фото
            if post.get('photo_url'):
                try:
                    self.bot.send_photo(
                        chat_id,
                        post['photo_url'],
                        caption=post_text,
                        parse_mode="HTML",
                        reply_markup=types.InlineKeyboardMarkup().add(
                            types.InlineKeyboardButton("📢 Открыть в группе", url=post['url'])
                        )
                    )
                    return
                except Exception as e:
                    logger.error(f"❌ Ошибка отправки фото: {e}")
            
            # Отправляем как текст
            self.bot.send_message(
                chat_id,
                post_text,
                parse_mode="HTML",
                disable_web_page_preview=False,
                reply_markup=types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton("📢 Открыть в группе", url=post['url'])
                )
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки поста: {e}")

    def send_group_posts(self, chat_id: int, animal_type: str = 'cats'):
        """Отправляет все посты с подробной статистикой"""
        try:
            posts = self.parser.get_cached_posts(animal_type)
            
            if not posts:
                self.bot.send_message(
                    chat_id,
                    "😿 Сейчас нет доступных объявлений.\n"
                    f"📢 Проверьте группу напрямую"
                )
                return
            
            group_name = "Лапки-ручки Ялта" if animal_type == 'cats' else "Ялта Животные"
            group_url = self.parser.groups[0]['url'] if animal_type == 'cats' else self.parser.groups[1]['url']
            
            # Статистика по источникам
            parsed_count = sum(1 for p in posts if p.get('source') == 'parsed')
            mock_count = len(posts) - parsed_count
            
            # Статус парсинга
            if parsed_count > 0:
                status_text = f"✅ <b>Актуальные данные</b>: {parsed_count} из {len(posts)}"
                status_emoji = "📡"
            elif self.parser.failure_count > 0:
                status_text = f"⚠️ <b>Парсинг временно недоступен</b> (попыток: {self.parser.failure_count})\n📋 Показаны примеры объявлений"
                status_emoji = "🎭"
            else:
                status_text = "📋 <b>Примеры объявлений</b>"
                status_emoji = "🎭"
            
            # Информация о кулдауне
            cooldown_info = ""
            if self.parser.failure_count > 0:
                cooldown_minutes = min(self.parser.failure_count * 5, 60)
                next_attempt = ""
                if self.parser.last_attempt:
                    time_passed = (datetime.now() - self.parser.last_attempt).total_seconds() / 60
                    remaining = max(0, cooldown_minutes - time_passed)
                    if remaining > 0:
                        next_attempt = f"\n⏳ Следующая попытка через: {int(remaining)} мин"
                
                cooldown_info = f"\n🔄 Автообновление: каждые {cooldown_minutes} мин{next_attempt}"
            
            header_text = (
                f"{status_emoji} <b>{'КОШКИ' if animal_type == 'cats' else 'СОБАКИ'} ИЩУТ ДОМ</b>\n\n"
                f"📢 Группа: <a href='{group_url}'>{group_name}</a>\n\n"
                f"{status_text}{cooldown_info}"
            )
            
            self.bot.send_message(chat_id, header_text, parse_mode="HTML")
            
            # Отправляем посты
            for i, post in enumerate(posts):
                self.send_post(chat_id, post)
                time.sleep(0.5)  # Пауза между постами
            
            # Футер с инструкциями
            footer_text = (
                "💡 <b>Как помочь животным:</b>\n\n"
                f"🏠 <b>Взять {'кошку' if animal_type == 'cats' else 'собаку'}:</b>\n"
                "Свяжитесь по контактам из объявления\n\n"
                f"📢 <b>Актуальные объявления:</b>\n<a href='{group_url}'>Перейти в группу</a>\n\n"
                "🤝 <b>Стать волонтером:</b>\nНапишите в группу или координаторам\n\n"
                "🔄 <b>Обновить данные:</b> /update"
            )
            
            self.bot.send_message(chat_id, footer_text, parse_mode="HTML")
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки постов: {e}")
            self.bot.send_message(
                chat_id,
                f"⚠️ Ошибка загрузки объявлений\n\n"
                f"Попробуйте позже или посетите группу:\n"
                f"{self.parser.groups[0]['url'] if animal_type == 'cats' else self.parser.groups[1]['url']}"
            )

    def get_main_keyboard(self):
        """Главная клавиатура"""
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add("🏥 Стерилизация", "🏠 Пристройство")
        markup.add("📞 Контакты", "ℹ️ О проекте")
        return markup
    
    def get_adoption_keyboard(self):
        """Клавиатура пристройства"""
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("🐱 Кошки ищут дом", "🐶 Собаки ищут дом")
        markup.add("📝 Подать объявление")
        markup.add("🔙 Назад")
        return markup
    
    def get_sterilization_keyboard(self):
        """Клавиатура стерилизации"""
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("💰 Платная стерилизация", "🆓 Бесплатная стерилизация")
        markup.add("🔙 Назад")
        return markup

    def load_html_file(self, filename: str) -> str:
        """Загружает HTML файл из папки assets"""
        try:
            with open(f'assets/{filename}', 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки HTML: {e}")
            return f"⚠️ Информация временно недоступна ({filename})"

    def setup_handlers(self):
        """Обработчики команд и сообщений"""
        
        @self.bot.message_handler(commands=['start'])
        def start_handler(message):
            self.stats["users"].add(message.from_user.id)
            self.stats["messages"] += 1
            
            welcome_text = """👋 <b>Добро пожаловать!</b>

🐾 Помощник по уличным животным Ялты

Выберите раздел:
🏥 <b>Стерилизация</b> - информация о программах
🏠 <b>Пристройство</b> - животные ищут дом  
📞 <b>Контакты</b> - связь с волонтерами
ℹ️ <b>О проекте</b> - наша деятельность

<i>💡 Бот автоматически обновляет объявления из Telegram-групп</i>"""
            
            self.bot.send_message(
                message.chat.id, 
                welcome_text, 
                parse_mode="HTML",
                reply_markup=self.get_main_keyboard()
            )
        
        @self.bot.message_handler(commands=['update'])
        def update_handler(message):
            """Принудительное обновление постов"""
            self.parser.posts_cache = []
            self.parser.last_update = None
            self.parser.failure_count = max(0, self.parser.failure_count - 1)  # Сброс части неудач
            
            self.bot.send_message(message.chat.id, "🔄 Принудительное обновление постов...")
            
            try:
                posts = self.parser.get_group_posts('all', 5)
                parsed_count = sum(1 for p in posts if p.get('source') == 'parsed')
                mock_count = len(posts) - parsed_count
                
                status_text = f"✅ <b>Результат обновления:</b>\n\n"
                
                if parsed_count > 0:
                    status_text += f"📡 Получено актуальных: {parsed_count}\n"
                    status_text += f"✅ Парсинг работает!"
                else:
                    status_text += f"⚠️ Парсинг недоступен\n"
                    status_text += f"🎭 Показаны примеры: {mock_count}\n"
                    status_text += f"🔄 Попыток неудач: {self.parser.failure_count}"
                
                self.bot.send_message(message.chat.id, status_text, parse_mode="HTML")
                
            except Exception as e:
                logger.error(f"❌ Ошибка обновления: {e}")
                self.bot.send_message(
                    message.chat.id, 
                    f"❌ Ошибка обновления: {str(e)[:100]}"
                )
        
        @self.bot.message_handler(commands=['status'])
        def status_handler(message):
            """Подробная диагностика системы"""
            try:
                status_lines = ["🔧 <b>ДИАГНОСТИКА СИСТЕМЫ</b>\n"]
                
                # Статус парсера
                if self.parser.last_update:
                    last_update = self.parser.last_update.strftime('%d.%m.%Y %H:%M:%S')
                    status_lines.append(f"📊 <b>Последнее обновление:</b> {last_update}")
                else:
                    status_lines.append("📊 <b>Последнее обновление:</b> Никогда")
                
                status_lines.append(f"❌ <b>Неудачных попыток:</b> {self.parser.failure_count}")
                status_lines.append(f"💾 <b>Постов в кэше:</b> {len(self.parser.posts_cache)}")
                
                # Следующая попытка
                if self.parser.should_attempt_parsing():
                    status_lines.append("✅ <b>Статус:</b> Готов к обновлению")
                else:
                    cooldown = min(self.parser.failure_count * 5, 60)
                    time_passed = 0
                    if self.parser.last_attempt:
                        time_passed = int((datetime.now() - self.parser.last_attempt).total_seconds() / 60)
                    remaining = max(0, cooldown - time_passed)
                    status_lines.append(f"⏳ <b>Кулдаун:</b> {remaining} мин (из {cooldown})")
                
                # Статус групп
                status_lines.append("\n📢 <b>ГРУППЫ:</b>")
                for group in self.parser.groups:
                    group_type = "🐱" if group['type'] == 'cats' else "🐶"
                    status_lines.append(f"{group_type} {group['username']}")
                
                # Быстрый тест доступности
                status_lines.append("\n🧪 <b>БЫСТРЫЙ ТЕСТ:</b>")
                try:
                    test_url = f"https://t.me/s/{self.parser.groups[0]['username']}"
                    response = requests.get(test_url, timeout=5, headers=self.parser.get_advanced_headers())
                    
                    if response.status_code == 200:
                        if "cloudflare" in response.text.lower():
                            status_lines.append("⚠️ Cloudflare защита активна")
                        elif len(response.text) > 10000:
                            status_lines.append("✅ Группа доступна для парсинга")
                        else:
                            status_lines.append("⚠️ Получен короткий ответ")
                    else:
                        status_lines.append(f"❌ HTTP {response.status_code}")
                        
                except Exception as e:
                    status_lines.append(f"❌ Ошибка теста: {str(e)[:50]}")
                
                self.bot.send_message(
                    message.chat.id,
                    "\n".join(status_lines),
                    parse_mode="HTML"
                )
                
            except Exception as e:
                self.bot.send_message(message.chat.id, f"❌ Ошибка диагностики: {e}")
        
        @self.bot.message_handler(commands=['reset'])
        def reset_handler(message):
            """Сброс счетчиков неудач"""
            self.parser.failure_count = 0
            self.parser.last_attempt = None
            self.bot.send_message(
                message.chat.id, 
                "🔄 Счетчики сброшены. Парсинг будет повторен при следующем запросе."
            )
        
        # Остальные обработчики остаются такими же...
        @self.bot.message_handler(func=lambda m: m.text == "🏥 Стерилизация")
        def sterilization_handler(message):
            self.stats["users"].add(message.from_user.id)
            self.stats["messages"] += 1
            
            self.bot.send_message(
                message.chat.id,
                "🏥 <b>Стерилизация животных</b>\n\nВыберите вариант:",
                parse_mode="HTML",
                reply_markup=self.get_sterilization_keyboard()
            )
        
        @self.bot.message_handler(func=lambda m: m.text == "💰 Платная стерилизация")
        def paid_sterilization_handler(message):
            self.bot.send_message(
                message.chat.id,
                self.load_html_file('paid_text.html'),
                parse_mode="HTML"
            )
        
        @self.bot.message_handler(func=lambda m: m.text == "🆓 Бесплатная стерилизация")
        def free_sterilization_handler(message):
            self.bot.send_message(
                message.chat.id,
                self.load_html_file('free_text.html'),
                parse_mode="HTML"
            )
        
        @self.bot.message_handler(func=lambda m: m.text == "🏠 Пристройство")
        def adoption_handler(message):
            self.stats["users"].add(message.from_user.id)
            self.stats["messages"] += 1
            
            # Показываем статус парсинга в меню
            parsed_posts = sum(1 for p in self.parser.posts_cache if p.get('source') == 'parsed')
            status_line = ""
            
            if parsed_posts > 0:
                status_line = f"\n📡 <b>Статус:</b> Данные актуальны ({parsed_posts} объявлений)"
            elif self.parser.failure_count > 0:
                status_line = f"\n⚠️ <b>Статус:</b> Парсинг временно недоступен"
            else:
                status_line = f"\n📋 <b>Статус:</b> Показаны примеры"
            
            info_text = f"""🏠 <b>Пристройство животных</b>{status_line}

Выберите действие:

🐱 <b>Кошки ищут дом</b>
Актуальные объявления из группы

🐶 <b>Собаки ищут дом</b>
Актуальные объявления из группы

📝 <b>Подать объявление</b>
Как разместить свое объявление"""
            
            self.bot.send_message(
                message.chat.id, 
                info_text, 
                parse_mode="HTML",
                reply_markup=self.get_adoption_keyboard()
            )
        
        @self.bot.message_handler(func=lambda m: m.text == "🐱 Кошки ищут дом")
        def cats_handler(message):
            self.send_group_posts(message.chat.id, 'cats')
        
        @self.bot.message_handler(func=lambda m: m.text == "🐶 Собаки ищут дом")
        def dogs_handler(message):
            self.send_group_posts(message.chat.id, 'dogs')
        
        @self.bot.message_handler(func=lambda m: m.text == "📝 Подать объявление")
        def post_ad_handler(message):
            info_text = f"""📝 <b>Подать объявление</b>

📢 <b>Группы для объявлений:</b>
<a href="{self.parser.groups[0]['url']}">Лапки-ручки Ялта</a> (кошки)
<a href="{self.parser.groups[1]['url']}">Ялта Животные</a> (собаки)

✍️ <b>Как подать:</b>
1️⃣ Перейти в группу
2️⃣ Написать администраторам  
3️⃣ Или связаться с координаторами

📋 <b>Нужная информация:</b>
🔹 Фото животного
🔹 Возраст, пол, окрас  
🔹 Характер и особенности
🔹 Здоровье (прививки, стерилизация)
🔹 Ваши контакты для связи"""
            
            self.bot.send_message(message.chat.id, info_text, parse_mode="HTML")
        
        @self.bot.message_handler(func=lambda m: m.text == "📞 Контакты")
        def contacts_handler(message):
            contacts_text = """📞 <b>КОНТАКТЫ</b>

👥 <b>Координаторы:</b>
🔹 Кошки: +7 978 144-90-70
🔹 Собаки: +7 978 000-00-02  
🔹 Лечение: +7 978 000-00-03

🏥 <b>Ветклиники:</b>
🔹 "Айболит": +7 978 000-00-04
🔹 "ВетМир": +7 978 000-00-05

📱 <b>Социальные сети:</b>  
🔹 Telegram: @yalta_animals
🔹 Instagram: @yalta_street_animals

⚡ <b>Экстренные случаи:</b>
+7 978 000-00-01 (круглосуточно)"""
            
            self.bot.send_message(message.chat.id, contacts_text, parse_mode="HTML")
        
        @self.bot.message_handler(func=lambda m: m.text == "ℹ️ О проекте")  
        def about_handler(message):
            about_text = """ℹ️ <b>О ПРОЕКТЕ</b>

🎯 <b>Наша миссия:</b>
Помощь бездомным животным Ялты и окрестностей

📊 <b>Наши достижения:</b>
🔹 Стерилизовано: 500+ кошек, 200+ собак
🔹 Пристроено в семьи: 300+ животных  
🔹 Активных волонтеров: 50+ человек
🔹 Партнерских клиник: 5

💰 <b>Поддержать проект:</b>
Сбербанк: 2202 2020 0000 0000
ЮMoney: 410012345678901

🤝 <b>Стать волонтером:</b>
Пишите координаторам или в группы

🔄 <b>Этот бот:</b>
Автоматически собирает объявления из Telegram-групп волонтеров"""
            
            self.bot.send_message(message.chat.id, about_text, parse_mode="HTML")
        
        @self.bot.message_handler(func=lambda m: m.text == "🔙 Назад")
        def back_handler(message):
            self.bot.send_message(
                message.chat.id, 
                "🏠 Главное меню:", 
                reply_markup=self.get_main_keyboard()
            )
        
        @self.bot.message_handler(func=lambda m: True)
        def default_handler(message):
            self.stats["users"].add(message.from_user.id)
            self.stats["messages"] += 1
            
            help_text = """❓ <b>Используйте кнопки меню</b>

🚀 Доступные команды:
/start - главное меню
/update - обновить объявления  
/status - диагностика системы
/reset - сбросить ошибки

💡 Или выберите нужный раздел кнопками ниже"""
            
            self.bot.send_message(
                message.chat.id,
                help_text,
                parse_mode="HTML", 
                reply_markup=self.get_main_keyboard()
            )

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
            parsed_count = sum(1 for p in self.parser.posts_cache if p.get('source') == 'parsed')
            
            return jsonify({
                "status": "🤖 Enhanced Animal Bot",
                "version": "2.0",
                "time": datetime.now().strftime('%H:%M:%S'),
                "users": len(self.stats["users"]), 
                "messages": self.stats["messages"],
                "parser": {
                    "cached_posts": len(self.parser.posts_cache),
                    "parsed_posts": parsed_count,
                    "mock_posts": len(self.parser.posts_cache) - parsed_count,
                    "failure_count": self.parser.failure_count,
                    "last_update": self.parser.last_update.isoformat() if self.parser.last_update else None,
                    "can_parse": self.parser.should_attempt_parsing()
                },
                "groups": [g['url'] for g in self.parser.groups]
            })
        
        @self.app.route('/posts')
        def posts_api():
            try:
                posts = self.parser.get_cached_posts()
                parsed_count = sum(1 for p in posts if p.get('source') == 'parsed')
                
                return jsonify({
                    "status": "ok",
                    "total": len(posts),
                    "parsed": parsed_count,
                    "mocks": len(posts) - parsed_count,
                    "posts": posts,
                    "parser_status": {
                        "failure_count": self.parser.failure_count,
                        "can_attempt": self.parser.should_attempt_parsing(),
                        "last_update": self.parser.last_update.isoformat() if self.parser.last_update else None
                    }
                })
            except Exception as e:
                return jsonify({"status": "error", "message": str(e)}), 500
        
        @self.app.route('/force_update')
        def force_update_api():
            """API для принудительного обновления"""
            try:
                # Сброс ограничений
                self.parser.posts_cache = []
                self.parser.last_update = None  
                self.parser.failure_count = max(0, self.parser.failure_count - 2)
                
                posts = self.parser.get_group_posts('all', 5)
                parsed_count = sum(1 for p in posts if p.get('source') == 'parsed')
                
                return jsonify({
                    "status": "force_updated",
                    "timestamp": datetime.now().isoformat(),
                    "total_posts": len(posts),
                    "parsed_posts": parsed_count,
                    "mock_posts": len(posts) - parsed_count,
                    "failure_count": self.parser.failure_count
                })
            except Exception as e:
                logger.error(f"❌ Force update error: {e}")
                return jsonify({"status": "error", "message": str(e)}), 500

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
        """Запуск улучшенного бота"""
        logger.info("🚀 Запуск Enhanced Animal Bot v2.0...")
        
        # Проверяем наличие cloudscraper
        try:
            import cloudscraper
            logger.info("✅ CloudScraper доступен")
        except ImportError:
            logger.warning("⚠️ CloudScraper не установлен: pip install cloudscraper")
        
        # Предзагрузка постов  
        try:
            posts = self.parser.get_cached_posts()
            parsed_count = sum(1 for p in posts if p.get('source') == 'parsed')
            logger.info(f"✅ Предзагружено {len(posts)} постов (парсинг: {parsed_count}, моки: {len(posts) - parsed_count})")
            
            if parsed_count == 0 and self.parser.failure_count > 0:
                logger.warning(f"⚠️ Парсинг недоступен, неудач: {self.parser.failure_count}")
                
        except Exception as e:
            logger.warning(f"⚠️ Ошибка предзагрузки: {e}")
        
        # Запуск бота
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
    os.makedirs('assets/images', exist_ok=True)
    
    # Создание информационных файлов
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

    # Установка зависимостей (инструкции)
    requirements_info = """
Для улучшенного парсинга установите дополнительные зависимости:

pip install cloudscraper beautifulsoup4 requests lxml

CloudScraper помогает обходить защиту Cloudflare.
"""
    
    print("🔧 " + requirements_info)
    
    # Запуск бота
    try:
        logger.info("🚀 Инициализация Enhanced Animal Bot...")
        bot = CatBotWithPhotos()
        bot.run()
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"💥 Критическая ошибка запуска: {e}")
        print("\n❌ Возможные причины:")
        print("1. Не установлен TOKEN в переменных окружения")
        print("2. Отсутствуют зависимости: pip install -r requirements.txt")
        print("3. Проблемы с сетью или доступом к Telegram API")
        print("\n🔄 Попробуйте перезапустить через 30 секунд...")
        time.sleep(30)
