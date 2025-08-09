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
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class RobustTelegramParser:
    """Устойчивый парсер Telegram групп с несколькими методами парсинга"""
    
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
        
        # Инициализация CloudScraper
        try:
            self.scraper = cloudscraper.create_scraper(
                browser={
                    'browser': 'chrome',
                    'platform': 'windows',
                    'mobile': False
                }
            )
        except Exception as e:
            logger.warning(f"CloudScraper недоступен, используем requests: {e}")
            self.scraper = requests.Session()
        
        # Настройки Selenium
        self.selenium_options = Options()
        self.selenium_options.add_argument("--headless")
        self.selenium_options.add_argument("--disable-blink-features=AutomationControlled")
        self.selenium_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        
        # Ротация User-Agents
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
        ]
    
    def should_attempt_parsing(self) -> bool:
        """Определяет, стоит ли пытаться парсить (защита от спама)"""
        if not self.last_attempt:
            return True
        
        cooldown_minutes = min(self.failure_count * 5, 60)
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
            'Cache-Control': 'max-age=0'
        }
    
    def get_group_posts(self, group_type: str = 'all', limit: int = 3) -> List[Dict]:
        """Главный метод получения постов с множественными стратегиями"""
        self.last_attempt = datetime.now()
        
        if not self.should_attempt_parsing():
            logger.info(f"Парсинг пропущен (кулдаун: {self.failure_count * 5} мин)")
            return self.get_smart_mock_posts(group_type, limit)
        
        posts = []
        success = False
        
        # Стратегия 1: CloudScraper
        posts = self.try_cloudscraper_method(group_type, limit)
        if posts:
            success = True
        
        # Стратегия 2: Selenium
        if not success:
            posts = self.try_selenium_method(group_type, limit)
            if posts:
                success = True
        
        # Стратегия 3: Множественные попытки requests
        if not success:
            posts = self.try_multiple_attempts(group_type, limit)
            if posts:
                success = True
        
        if success:
            self.posts_cache = posts
            self.last_update = datetime.now()
            self.failure_count = max(0, self.failure_count - 1)
            logger.info(f"Успешно получено {len(posts)} постов")
        else:
            self.failure_count += 1
            logger.warning(f"Парсинг неудачен (попытка #{self.failure_count})")
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
                logger.info(f"Пробуем CloudScraper: {url}")
                
                self.scraper.headers.update(self.get_advanced_headers())
                response = self.scraper.get(url, timeout=20)
                
                if response.status_code == 200:
                    group_posts = self.parse_html_content(response.text, group, limit)
                    if group_posts:
                        posts.extend(group_posts)
                        logger.info(f"CloudScraper: получено {len(group_posts)} постов")
                else:
                    logger.warning(f"HTTP {response.status_code}")
                
                time.sleep(random.uniform(2, 5))
            
            return posts
        except Exception as e:
            logger.error(f"Ошибка CloudScraper: {e}")
            return []
    
    def try_selenium_method(self, group_type: str, limit: int) -> List[Dict]:
        """Попытка парсинга через Selenium"""
        driver = None
        try:
            # Инициализация драйвера
            driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()),
                options=self.selenium_options
            )
            driver.set_page_load_timeout(30)
            
            posts = []
            for group in self.groups:
                if group_type != 'all' and group['type'] != group_type:
                    continue
                
                url = f'https://t.me/s/{group["username"]}'
                logger.info(f"Пробуем Selenium: {url}")
                
                try:
                    driver.get(url)
                    
                    # Ожидаем загрузки сообщений
                    try:
                        WebDriverWait(driver, 15).until(
                            EC.presence_of_element_located((By.CLASS_NAME, "tgme_widget_message"))
                    except TimeoutException:
                        logger.warning("Не дождались загрузки сообщений")
                        continue
                    
                    # Прокрутка для загрузки больше сообщений
                    for _ in range(2):
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(random.uniform(1, 3))
                    
                    # Парсим HTML
                    html = driver.page_source
                    group_posts = self.parse_html_content(html, group, limit)
                    
                    if group_posts:
                        posts.extend(group_posts)
                        logger.info(f"Selenium: получено {len(group_posts)} постов")
                    
                    time.sleep(random.uniform(3, 5))
                
                except Exception as e:
                    logger.error(f"Ошибка при обработке группы {group['username']}: {e}")
                    continue
            
            return posts
        except Exception as e:
            logger.error(f"Общая ошибка Selenium: {e}")
            return []
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass
    
    def try_multiple_attempts(self, group_type: str, limit: int) -> List[Dict]:
        """Множественные попытки с разными настройками"""
        try:
            posts = []
            for group in self.groups:
                if group_type != 'all' and group['type'] != group_type:
                    continue
                
                for attempt in range(3):
                    try:
                        session = requests.Session()
                        session.headers.update(self.get_advanced_headers())
                        
                        urls = [
                            f'https://t.me/s/{group["username"]}',
                            f'https://telegram.me/s/{group["username"]}'
                        ]
                        
                        for url in urls:
                            logger.info(f"Попытка {attempt + 1}: {url}")
                            response = session.get(url, timeout=15, allow_redirects=True)
                            
                            if response.status_code == 200:
                                group_posts = self.parse_html_content(response.text, group, limit)
                                if group_posts:
                                    posts.extend(group_posts)
                                    logger.info(f"Успешно: {len(group_posts)} постов")
                                    break
                            
                            time.sleep(random.uniform(1, 3))
                        
                        if posts:
                            break
                            
                    except requests.RequestException as e:
                        logger.warning(f"Попытка {attempt + 1} неудачна: {e}")
                        time.sleep(random.uniform(2, 4))
                        continue
                
                time.sleep(random.uniform(3, 7))
            
            return posts
        except Exception as e:
            logger.error(f"Ошибка множественных попыток: {e}")
            return []
    
    def parse_html_content(self, html: str, group: Dict, limit: int) -> List[Dict]:
        """Парсинг HTML контента"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            if "Cloudflare" in html or "checking your browser" in html.lower():
                logger.warning("Обнаружена защита Cloudflare")
                return []
            
            if len(html) < 1000:
                logger.warning("Слишком короткий HTML ответ")
                return []
            
            messages = []
            for selector in ['div.tgme_widget_message', 'div[data-post]', '.tgme_widget_message']:
                found = soup.select(selector)
                if found:
                    messages = found
                    break
            
            if not messages:
                logger.warning("Сообщения не найдены в HTML")
                return []
            
            posts = []
            for msg_div in messages[:limit*2]:
                post_data = self.parse_message_div(msg_div, group)
                if post_data and self.is_valid_post(post_data, group['type']):
                    posts.append(post_data)
                    if len(posts) >= limit:
                        break
            
            return posts
        except Exception as e:
            logger.error(f"Ошибка парсинга HTML: {e}")
            return []
    
    def parse_message_div(self, div, group) -> Optional[Dict]:
        """Парсинг отдельного сообщения"""
        try:
            post_id = (div.get('data-post', '') or 
                      div.get('data-message-id', '') or
                      f"msg_{hash(str(div)[:100]) % 10000}")
            
            if '/' in str(post_id):
                post_id = str(post_id).split('/')[-1]
            
            text = self.extract_text(div)
            if not text or len(text) < 20:
                return None
            
            return {
                'id': post_id,
                'text': text,
                'date': self.extract_date(div),
                'url': f"{group['url']}/{post_id}",
                'title': self.extract_smart_title(text, group['type']),
                'description': self.extract_smart_description(text),
                'contact': self.extract_contact(text),
                'photo_url': self.extract_photo(div),
                'has_photo': bool(self.extract_photo(div)),
                'type': group['type'],
                'source': 'parsed'
            }
        except Exception as e:
            logger.error(f"Ошибка парсинга сообщения: {e}")
            return None
    
    def extract_text(self, div) -> str:
        """Извлечение текста из div"""
        for selector in ['.tgme_widget_message_text', 'div.tgme_widget_message_text', '.message_text']:
            text_elem = div.select_one(selector)
            if text_elem:
                text = text_elem.get_text(separator=' ', strip=True)
                if text:
                    return text
        
        full_text = div.get_text(separator=' ', strip=True)
        cleaned = re.sub(r'(Views|Просмотров|Subscribe|Подписаться).*$', '', full_text, flags=re.IGNORECASE)
        return cleaned if len(cleaned) > 20 else full_text
    
    def extract_date(self, div) -> str:
        """Извлечение даты"""
        for selector in ['time[datetime]', '.tgme_widget_message_date time']:
            date_elem = div.select_one(selector)
            if date_elem:
                if date_elem.get('datetime'):
                    try:
                        dt = datetime.fromisoformat(date_elem['datetime'].replace('Z', '+00:00'))
                        return dt.strftime('%d.%m.%Y %H:%M')
                    except:
                        pass
                return date_elem.get_text(strip=True) or "Недавно"
        return "Недавно"
    
    def extract_photo(self, div) -> Optional[str]:
        """Извлечение URL фото"""
        for selector in ['.tgme_widget_message_photo_wrap[style*="background-image"]', 'img[src]']:
            photo_elem = div.select_one(selector)
            if photo_elem:
                if 'background-image' in photo_elem.get('style', ''):
                    match = re.search(r"background-image:url\('([^']+)'\)", photo_elem['style'])
                    if match:
                        return match.group(1)
                return photo_elem.get('src') or photo_elem.get('data-src')
        return None
    
    def extract_smart_title(self, text: str, animal_type: str) -> str:
        """Умное извлечение заголовка"""
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        keywords = ['ищет', 'дом', 'пристрой', 'отда', 'найден']
        
        for line in lines[:5]:
            if len(line) > 15 and any(keyword in line.lower() for keyword in keywords):
                title = re.sub(r'[^\w\s\-\.,!?а-яёА-ЯЁ]', ' ', line)
                title = re.sub(r'\s+', ' ', title).strip()
                return title[:60] + "..." if len(title) > 60 else title
        
        defaults = {
            'cats': ['Кошка ищет дом', 'Котенок в добрые руки'],
            'dogs': ['Собака ищет дом', 'Щенок в добрые руки']
        }
        return random.choice(defaults.get(animal_type, defaults['cats']))
    
    def extract_smart_description(self, text: str) -> str:
        """Умное извлечение описания"""
        clean_text = re.sub(r'(@\w+|https?://\S+|\+?[78][\d\s\-\(\)]{10,})', '', text)
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        
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
        
        # Телефоны
        phone_patterns = [
            r'\+?7[\s\-]?\(?9\d{2}\)?\s?[\d\s\-]{7,10}',
            r'\+?8[\s\-]?\(?9\d{2}\)?\s?[\d\s\-]{7,10}'
        ]
        
        for pattern in phone_patterns:
            phones = re.findall(pattern, text)
            if phones:
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
        
        animal_keywords = ['кот', 'кошк', 'котен'] if animal_type == 'cats' else ['собак', 'щен', 'пес']
        action_keywords = ['ищет', 'дом', 'пристрой', 'отда']
        exclude_keywords = ['продам', 'куплю', 'услуг', 'реклам']
        
        has_animal = any(keyword in text for keyword in animal_keywords)
        has_action = any(keyword in text for keyword in action_keywords)
        has_exclude = any(keyword in text for keyword in exclude_keywords)
        
        return has_animal and has_action and not has_exclude and len(text) > 30
    
    def get_smart_mock_posts(self, group_type: str, limit: int) -> List[Dict]:
        """Генерация реалистичных мок-постов"""
        mock_data = {
            'cats': {
                'names': ['Мурка', 'Барсик', 'Рыжик'],
                'ages': ['2 месяца', '4 месяца', '1 год'],
                'colors': ['рыжий', 'серый', 'белый']
            },
            'dogs': {
                'names': ['Шарик', 'Дружок', 'Лайка'],
                'ages': ['3 месяца', '6 месяцев', '2 года'],
                'colors': ['черный', 'коричневый', 'пятнистый']
            }
        }
        
        data = mock_data[group_type]
        posts = []
        
        for i in range(limit):
            name = random.choice(data['names'])
            age = random.choice(data['ages'])
            color = random.choice(data['colors'])
            
            emoji = '🐱' if group_type == 'cats' else '🐶'
            animal = 'котенок' if group_type == 'cats' else 'щенок'
            
            description = (
                f"{emoji} {animal.capitalize()} {name}, {age}, {color} окрас. "
                f"Ласковый, приучен к лотку, ищет заботливую семью!"
            )
            
            posts.append({
                'id': f'mock_{i + 1000}',
                'title': f'{emoji} {name} ищет дом',
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
        phone = f"+7 978 {random.choice(['123', '456', '789'])}-{random.randint(10, 99)}"
        username = f"@volunteer_{random.randint(1, 100)}"
        return f"{phone} • {username}" if random.choice([True, False]) else phone
    
    def get_cached_posts(self, group_type: str = 'all') -> List[Dict]:
        """Получение кэшированных постов"""
        should_update = (
            not self.last_update or 
            (datetime.now() - self.last_update).seconds > 1800
        )
        
        if should_update and self.should_attempt_parsing():
            try:
                fresh_posts = self.get_group_posts(group_type, 3)
                if fresh_posts:
                    return fresh_posts
            except Exception as e:
                logger.error(f"Ошибка обновления: {e}")
        
        cached = [p for p in self.posts_cache if group_type == 'all' or p['type'] == group_type]
        return cached if cached else self.get_smart_mock_posts(group_type, 3)

class CatBotWithPhotos:
    """Telegram бот для помощи животным"""
    
    def __init__(self):
        self.token = os.environ.get('TOKEN')
        if not self.token:
            logger.error("Токен бота не найден!")
            exit(1)
        
        self.bot = telebot.TeleBot(self.token)
        self.parser = RobustTelegramParser()
        self.app = Flask(__name__)
        self.port = int(os.environ.get('PORT', 8080))
        self.webhook_url = os.environ.get('WEBHOOK_URL')
        self.stats = {"users": set(), "messages": 0}
        
        self.setup_handlers()
        self.setup_routes()
    
    def send_post(self, chat_id: int, post: Dict):
        """Отправка одного поста"""
        try:
            emoji = '🐱' if post['type'] == 'cats' else '🐶'
            source_tag = ' 📡' if post.get('source') == 'parsed' else ' 🎭'
            status = "✅ Актуальное" if post.get('source') == 'parsed' else "⚠️ Пример"
            
            post_text = (
                f"{emoji} <b>{post['title']}</b>{source_tag}\n\n"
                f"{post['description']}\n\n"
                f"📅 {post['date']}\n"
                f"📞 {post['contact']}\n"
                f"🔗 <a href='{post['url']}'>Открыть в группе</a>\n\n"
                f"<i>{status}</i>"
            )
            
            if post.get('photo_url'):
                try:
                    self.bot.send_photo(
                        chat_id,
                        post['photo_url'],
                        caption=post_text[:1024],
                        parse_mode="HTML",
                        reply_markup=types.InlineKeyboardMarkup().add(
                            types.InlineKeyboardButton("📢 Открыть в группе", url=post['url'])
                        )
                    )
                    return
                except Exception as e:
                    logger.error(f"Ошибка отправки фото: {e}")
            
            self.bot.send_message(
                chat_id,
                post_text[:4096],
                parse_mode="HTML",
                disable_web_page_preview=False,
                reply_markup=types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton("📢 Открыть в группе", url=post['url'])
                )
            )
        except Exception as e:
            logger.error(f"Ошибка отправки поста: {e}")
    
    def send_group_posts(self, chat_id: int, animal_type: str = 'cats'):
        """Отправка всех постов группы"""
        try:
            posts = self.parser.get_cached_posts(animal_type)
            
            if not posts:
                self.bot.send_message(chat_id, "😿 Сейчас нет объявлений.\n📢 Проверьте группу напрямую")
                return
            
            group_name = "Лапки-ручки Ялта" if animal_type == 'cats' else "Ялта Животные"
            group_url = self.parser.groups[0]['url'] if animal_type == 'cats' else self.parser.groups[1]['url']
            
            parsed_count = sum(1 for p in posts if p.get('source') == 'parsed')
            if parsed_count > 0:
                status_text = f"✅ <b>Актуальные данные</b>: {parsed_count} из {len(posts)}"
            elif self.parser.failure_count > 0:
                status_text = f"⚠️ <b>Парсинг временно недоступен</b> (попыток: {self.parser.failure_count})"
            else:
                status_text = "📋 <b>Примеры объявлений</b>"
            
            self.bot.send_message(
                chat_id,
                f"📢 <b>{'КОШКИ' if animal_type == 'cats' else 'СОБАКИ'} ИЩУТ ДОМ</b>\n\n"
                f"Группа: <a href='{group_url}'>{group_name}</a>\n\n"
                f"{status_text}",
                parse_mode="HTML"
            )
            
            for post in posts:
                self.send_post(chat_id, post)
                time.sleep(0.5)
            
            self.bot.send_message(
                chat_id,
                "💡 <b>Как помочь животным:</b>\n\n"
                f"🏠 Взять {'кошку' if animal_type == 'cats' else 'собаку'}\n"
                "📢 <a href='{group_url}'>Перейти в группу</a>\n"
                "🔄 /update - обновить данные",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Ошибка отправки постов: {e}")
            self.bot.send_message(
                chat_id,
                f"⚠️ Ошибка загрузки объявлений\n\nПопробуйте позже или посетите группу:\n{group_url}"
            )
    
    def get_main_keyboard(self):
        """Главное меню"""
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add("🏥 Стерилизация", "🏠 Пристройство")
        markup.add("📞 Контакты", "ℹ️ О проекте")
        return markup
    
    def get_adoption_keyboard(self):
        """Меню пристройства"""
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("🐱 Кошки ищут дом", "🐶 Собаки ищут дом")
        markup.add("📝 Подать объявление", "🔙 Назад")
        return markup
    
    def get_sterilization_keyboard(self):
        """Меню стерилизации"""
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("💰 Платная", "🆓 Бесплатная")
        markup.add("🔙 Назад")
        return markup
    
    def load_html_file(self, filename: str) -> str:
        """Загрузка HTML файла"""
        try:
            with open(f'assets/{filename}', 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Ошибка загрузки HTML: {e}")
            return f"⚠️ Информация временно недоступна ({filename})"
    
    def setup_handlers(self):
        """Настройка обработчиков команд"""
        
        @self.bot.message_handler(commands=['start'])
        def start_handler(message):
            self.stats["users"].add(message.from_user.id)
            self.stats["messages"] += 1
            
            self.bot.send_message(
                message.chat.id,
                "👋 <b>Добро пожаловать!</b>\n\n"
                "🐾 Помощник по уличным животным Ялты\n\n"
                "Выберите раздел:",
                parse_mode="HTML",
                reply_markup=self.get_main_keyboard()
            )
        
        @self.bot.message_handler(commands=['update'])
        def update_handler(message):
            self.parser.posts_cache = []
            self.parser.last_update = None
            self.bot.send_message(message.chat.id, "🔄 Обновление данных...")
            posts = self.parser.get_group_posts('all', 5)
            parsed_count = sum(1 for p in posts if p.get('source') == 'parsed')
            self.bot.send_message(
                message.chat.id,
                f"✅ Получено {len(posts)} постов ({parsed_count} актуальных)",
                parse_mode="HTML"
            )
        
        @self.bot.message_handler(commands=['status'])
        def status_handler(message):
            status = [
                "🔧 <b>Статус бота</b>",
                f"👤 Пользователей: {len(self.stats['users'])}",
                f"✉️ Сообщений: {self.stats['messages']}",
                f"🔄 Неудачных попыток парсинга: {self.parser.failure_count}",
                f"💾 Кэшировано постов: {len(self.parser.posts_cache)}"
            ]
            self.bot.send_message(
                message.chat.id,
                "\n".join(status),
                parse_mode="HTML"
            )
        
        @self.bot.message_handler(func=lambda m: m.text == "🏠 Пристройство")
        def adoption_handler(message):
            self.stats["users"].add(message.from_user.id)
            parsed = sum(1 for p in self.parser.posts_cache if p.get('source') == 'parsed')
            status = f"\n📡 Актуальных: {parsed}" if parsed > 0 else "\n⚠️ Используются примеры"
            
            self.bot.send_message(
                message.chat.id,
                f"🏠 <b>Пристройство животных</b>{status}\n\nВыберите:",
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
            self.bot.send_message(
                message.chat.id,
                "📝 <b>Как подать объявление:</b>\n\n"
                "1. Перейдите в группу\n"
                "2. Напишите администраторам\n"
                "3. Укажите:\n"
                "   - Фото животного\n"
                "   - Возраст, пол, окрас\n"
                "   - Контакты для связи",
                parse_mode="HTML"
            )
        
        @self.bot.message_handler(func=lambda m: m.text == "🏥 Стерилизация")
        def sterilization_handler(message):
            self.bot.send_message(
                message.chat.id,
                "🏥 <b>Стерилизация животных</b>\n\nВыберите вариант:",
                parse_mode="HTML",
                reply_markup=self.get_sterilization_keyboard()
            )
        
        @self.bot.message_handler(func=lambda m: m.text == "💰 Платная")
        def paid_sterilization_handler(message):
            self.bot.send_message(
                message.chat.id,
                self.load_html_file('paid_text.html'),
                parse_mode="HTML"
            )
        
        @self.bot.message_handler(func=lambda m: m.text == "🆓 Бесплатная")
        def free_sterilization_handler(message):
            self.bot.send_message(
                message.chat.id,
                self.load_html_file('free_text.html'),
                parse_mode="HTML"
            )
        
        @self.bot.message_handler(func=lambda m: m.text == "📞 Контакты")
        def contacts_handler(message):
            self.bot.send_message(
                message.chat.id,
                "📞 <b>Контакты:</b>\n\n"
                "🐱 Кошки: +7 978 123-45-67\n"
                "🐶 Собаки: +7 978 765-43-21\n"
                "🏥 Клиника: +7 978 000-11-22",
                parse_mode="HTML"
            )
        
        @self.bot.message_handler(func=lambda m: m.text == "ℹ️ О проекте")
        def about_handler(message):
            self.bot.send_message(
                message.chat.id,
                "ℹ️ <b>О проекте:</b>\n\n"
                "Помогаем бездомным животным Ялты с 2020 года\n"
                "Нашли дом для 500+ животных",
                parse_mode="HTML"
            )
        
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
            self.bot.send_message(
                message.chat.id,
                "❓ Используйте кнопки меню или команды:\n"
                "/start - главное меню\n"
                "/update - обновить данные",
                reply_markup=self.get_main_keyboard()
            )
    
    def setup_routes(self):
        """Настройка Flask маршрутов"""
        
        @self.app.route(f'/{self.token}', methods=['POST'])
        def webhook():
            if request.headers.get('content-type') == 'application/json':
                update = telebot.types.Update.de_json(request.get_data().decode('utf-8'))
                self.bot.process_new_updates([update])
                return '', 200
            return 'Bad request', 400
        
        @self.app.route('/')
        def home():
            return jsonify({
                "status": "running",
                "users": len(self.stats["users"]),
                "posts": len(self.parser.posts_cache)
            })
    
    def setup_webhook(self):
        """Настройка webhook"""
        try:
            self.bot.remove_webhook()
            time.sleep(1)
            if self.webhook_url:
                self.bot.set_webhook(url=f"https://{self.webhook_url}/{self.token}")
                return True
            return False
        except Exception as e:
            logger.error(f"Ошибка webhook: {e}")
            return False
    
    def run(self):
        """Запуск бота"""
        logger.info("Запуск бота...")
        
        # Создаем папку assets если нет
        os.makedirs('assets', exist_ok=True)
        
        # Создаем файлы с информацией если их нет
        if not os.path.exists('assets/paid_text.html'):
            with open('assets/paid_text.html', 'w', encoding='utf-8') as f:
                f.write("<b>💰 Платная стерилизация</b>\n\nСтоимость: от 2000₽")
        
        if not os.path.exists('assets/free_text.html'):
            with open('assets/free_text.html', 'w', encoding='utf-8') as f:
                f.write("<b>🆓 Бесплатная стерилизация</b>\n\nДля бездомных животных")
        
        # Запускаем в нужном режиме
        if self.setup_webhook():
            logger.info("Режим: Webhook")
            self.app.run(host='0.0.0.0', port=self.port)
        else:
            logger.info("Режим: Polling")
            self.bot.polling(none_stop=True)

if __name__ == "__main__":
    bot = CatBotWithPhotos()
    bot.run()
