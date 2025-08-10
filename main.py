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
import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading

# Selenium imports
try:
    import undetected_chromedriver as uc
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
    SELENIUM_AVAILABLE = True
    print("✅ Selenium и undetected-chromedriver доступны")
except ImportError as e:
    SELENIUM_AVAILABLE = False
    print(f"⚠️ Selenium не установлен: {e}")
    print("Установите: pip install selenium undetected-chromedriver")

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class AdvancedSeleniumTelegramParser:
    """Продвинутый парсер Telegram с Selenium и множественными стратегиями обхода"""
    
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
        self.driver = None
        self.driver_lock = threading.Lock()
        
        # Настройки Selenium
        self.selenium_enabled = SELENIUM_AVAILABLE
        self.max_retries = 3
        self.page_load_timeout = 30
        self.scroll_pause_time = 2
        self.max_scroll_attempts = 5
        
        # Резервные User-Agents
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0'
        ]
        
        # Прокси (если нужны)
        self.proxy_list = []  # Добавьте свои прокси сюда
        
        # Статистика
        self.stats = {
            'selenium_success': 0,
            'selenium_failures': 0,
            'fallback_used': 0,
            'total_posts_parsed': 0
        }

    def should_attempt_parsing(self) -> bool:
        """Определяет, стоит ли пытаться парсить"""
        if not self.last_attempt:
            return True
        
        # Прогрессивный кулдаун: чем больше неудач, тем больше пауза
        cooldown_minutes = min(self.failure_count * 3, 45)  # максимум 45 минут
        time_passed = (datetime.now() - self.last_attempt).total_seconds() / 60
        
        return time_passed > cooldown_minutes

    def setup_selenium_driver(self, headless: bool = True, use_proxy: bool = False) -> webdriver.Chrome:
        """Настройка продвинутого Selenium драйвера"""
        if not self.selenium_enabled:
            raise Exception("Selenium не доступен")
        
        try:
            # Опции Chrome
            options = uc.ChromeOptions()
            
            # Основные настройки
            if headless:
                options.add_argument('--headless=new')  # Новый headless режим
            
            # Обход детекции автоматизации
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
            
            # Производительность
            options.add_argument('--disable-gpu')
            options.add_argument('--disable-extensions')
            options.add_argument('--disable-plugins')
            options.add_argument('--disable-images')  # Не загружаем изображения для скорости
            options.add_argument('--disable-javascript')  # Отключаем JS если не нужен
            
            # Память и процессы
            options.add_argument('--memory-pressure-off')
            options.add_argument('--max_old_space_size=4096')
            options.add_argument('--single-process')
            
            # User Agent
            options.add_argument(f'--user-agent={random.choice(self.user_agents)}')
            
            # Прокси (если указан)
            if use_proxy and self.proxy_list:
                proxy = random.choice(self.proxy_list)
                options.add_argument(f'--proxy-server={proxy}')
                logger.info(f"🌐 Используется прокси: {proxy}")
            
            # Размер окна
            options.add_argument('--window-size=1920,1080')
            
            # Дополнительные настройки
            prefs = {
                "profile.managed_default_content_settings.images": 2,  # Блокируем изображения
                "profile.default_content_setting_values.notifications": 2,  # Блокируем уведомления
                "profile.managed_default_content_settings.media_stream": 2,
            }
            options.add_experimental_option("prefs", prefs)
            
            # Создаем драйвер
            driver = uc.Chrome(options=options)
            
            # Дополнительные настройки после создания
            driver.set_page_load_timeout(self.page_load_timeout)
            driver.implicitly_wait(10)
            
            # Скрываем признаки автоматизации
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            logger.info("✅ Selenium драйвер настроен успешно")
            return driver
            
        except Exception as e:
            logger.error(f"❌ Ошибка настройки Selenium: {e}")
            raise

    def safe_driver_operation(self, operation, *args, **kwargs):
        """Безопасное выполнение операций с драйвером"""
        with self.driver_lock:
            try:
                return operation(*args, **kwargs)
            except WebDriverException as e:
                logger.error(f"❌ Ошибка драйвера: {e}")
                self.cleanup_driver()
                raise
            except Exception as e:
                logger.error(f"❌ Неожиданная ошибка: {e}")
                raise

    def cleanup_driver(self):
        """Очистка ресурсов драйвера"""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("🧹 Selenium драйвер закрыт")
            except:
                pass
            finally:
                self.driver = None

    def smart_scroll_and_load(self, driver, target_messages: int = 20) -> bool:
        """Умная прокрутка страницы для загрузки сообщений"""
        try:
            logger.info(f"🔄 Начинаем прокрутку для загрузки ~{target_messages} сообщений")
            
            # Ждем базовой загрузки
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CLASS_NAME, "tgme_channel_info"))
            )
            
            # Начальная пауза
            time.sleep(3)
            
            prev_height = driver.execute_script("return document.body.scrollHeight")
            messages_found = 0
            scroll_attempts = 0
            no_new_content_count = 0
            
            while scroll_attempts < self.max_scroll_attempts and messages_found < target_messages:
                # Прокручиваем вниз
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(self.scroll_pause_time)
                
                # Проверяем количество загруженных сообщений
                messages = driver.find_elements(By.CSS_SELECTOR, ".tgme_widget_message")
                messages_found = len(messages)
                
                # Проверяем, изменилась ли высота страницы
                new_height = driver.execute_script("return document.body.scrollHeight")
                
                if new_height == prev_height:
                    no_new_content_count += 1
                    if no_new_content_count >= 3:  # Если 3 раза подряд ничего не загрузилось
                        logger.info(f"⏹️ Прекращаем прокрутку - контент не загружается")
                        break
                else:
                    no_new_content_count = 0
                    prev_height = new_height
                
                scroll_attempts += 1
                logger.info(f"📜 Прокрутка {scroll_attempts}/{self.max_scroll_attempts}, найдено сообщений: {messages_found}")
                
                # Дополнительная пауза если мало сообщений
                if messages_found < 5:
                    time.sleep(2)
            
            logger.info(f"✅ Прокрутка завершена: {messages_found} сообщений за {scroll_attempts} попыток")
            return messages_found > 0
            
        except TimeoutException:
            logger.warning("⚠️ Таймаут при ожидании загрузки страницы")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка при прокрутке: {e}")
            return False

    def extract_message_data(self, driver, message_element, group: Dict) -> Optional[Dict]:
        """Извлечение данных из элемента сообщения"""
        try:
            # ID сообщения
            post_id = message_element.get_attribute('data-post')
            if not post_id:
                # Пытаемся найти в ссылке
                try:
                    link_elem = message_element.find_element(By.CSS_SELECTOR, ".tgme_widget_message_date")
                    href = link_elem.get_attribute('href')
                    if href:
                        post_id = href.split('/')[-1]
                except:
                    post_id = f"msg_{hash(str(message_element.get_attribute('outerHTML')[:100])) % 10000}"
            
            # Извлекаем текст сообщения
            text = self.extract_text_selenium(message_element)
            if not text or len(text.strip()) < 20:
                return None
            
            # Дата
            date_str = self.extract_date_selenium(message_element)
            
            # Фото URL
            photo_url = self.extract_photo_selenium(message_element)
            
            # Проверяем валидность поста
            if not self.is_valid_post_content(text, group['type']):
                return None
            
            # Извлекаем метаданные
            title = self.extract_smart_title(text, group['type'])
            description = self.extract_smart_description(text)
            contact = self.extract_contact(text)
            
            return {
                'id': str(post_id).split('/')[-1],
                'text': text,
                'date': date_str,
                'url': f"{group['url']}/{str(post_id).split('/')[-1]}",
                'title': title,
                'description': description,
                'contact': contact,
                'photo_url': photo_url,
                'has_photo': bool(photo_url),
                'type': group['type'],
                'source': 'selenium',
                'extracted_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения данных сообщения: {e}")
            return None

    def extract_text_selenium(self, message_element) -> str:
        """Извлечение текста через Selenium"""
        try:
            # Пробуем разные селекторы
            text_selectors = [
                ".tgme_widget_message_text",
                ".js-message_text",
                ".message_text",
                ".tgme_widget_message_content"
            ]
            
            for selector in text_selectors:
                try:
                    text_elem = message_element.find_element(By.CSS_SELECTOR, selector)
                    text = text_elem.get_attribute('textContent') or text_elem.text
                    if text and len(text.strip()) > 10:
                        return text.strip()
                except NoSuchElementException:
                    continue
            
            # Если ничего не найдено, берем весь текст элемента
            full_text = message_element.get_attribute('textContent') or message_element.text
            
            # Очищаем от служебных элементов
            cleaned_text = re.sub(r'(Views|Просмотров|Subscribe|Подписаться).*$', '', full_text, flags=re.IGNORECASE)
            cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
            
            return cleaned_text if len(cleaned_text) > 20 else full_text
            
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения текста: {e}")
            return ""

    def extract_date_selenium(self, message_element) -> str:
        """Извлечение даты через Selenium"""
        try:
            # Пробуем найти элемент времени
            time_selectors = [
                "time[datetime]",
                ".tgme_widget_message_date time",
                ".tgme_widget_message_date",
                "time"
            ]
            
            for selector in time_selectors:
                try:
                    time_elem = message_element.find_element(By.CSS_SELECTOR, selector)
                    
                    # Сначала пробуем datetime атрибут
                    datetime_attr = time_elem.get_attribute('datetime')
                    if datetime_attr:
                        try:
                            # Парсим ISO datetime
                            dt = datetime.fromisoformat(datetime_attr.replace('Z', '+00:00'))
                            return dt.strftime('%d.%m.%Y %H:%M')
                        except:
                            pass
                    
                    # Потом пробуем текст
                    date_text = time_elem.get_attribute('textContent') or time_elem.text
                    if date_text:
                        return date_text.strip()
                        
                except NoSuchElementException:
                    continue
            
            return "Недавно"
            
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения даты: {e}")
            return "Недавно"

    def extract_photo_selenium(self, message_element) -> Optional[str]:
        """Извлечение URL фото через Selenium"""
        try:
            photo_selectors = [
                ".tgme_widget_message_photo_wrap",
                ".tgme_widget_message_photo", 
                ".tgme_widget_message_document_thumb",
                "img[src*='cdn']"
            ]
            
            for selector in photo_selectors:
                try:
                    photo_elem = message_element.find_element(By.CSS_SELECTOR, selector)
                    
                    # Из style background-image
                    style = photo_elem.get_attribute('style')
                    if style and 'background-image' in style:
                        match = re.search(r"background-image:\s*url\(['\"]?([^'\")]+)['\"]?\)", style)
                        if match:
                            return match.group(1)
                    
                    # Из src атрибута
                    src = photo_elem.get_attribute('src')
                    if src and src.startswith('http'):
                        return src
                    
                    # Из data-src
                    data_src = photo_elem.get_attribute('data-src')
                    if data_src and data_src.startswith('http'):
                        return data_src
                        
                except NoSuchElementException:
                    continue
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения фото: {e}")
            return None

    def parse_group_selenium(self, group: Dict, limit: int = 10) -> List[Dict]:
        """Парсинг группы через Selenium"""
        posts = []
        driver = None
        
        try:
            logger.info(f"🤖 Selenium: парсинг {group['username']}")
            
            # Настраиваем драйвер
            driver = self.setup_selenium_driver(headless=True)
            
            # Переходим на страницу
            url = f'https://t.me/s/{group["username"]}'
            logger.info(f"🌐 Загружаем: {url}")
            
            driver.get(url)
            
            # Проверяем на блокировки
            page_source = driver.page_source.lower()
            if any(block_sign in page_source for block_sign in ['cloudflare', 'access denied', 'forbidden']):
                logger.warning(f"⚠️ Обнаружена блокировка для {group['username']}")
                return []
            
            # Умная прокрутка для загрузки сообщений
            if not self.smart_scroll_and_load(driver, target_messages=limit * 2):
                logger.warning(f"⚠️ Не удалось загрузить сообщения для {group['username']}")
                return []
            
            # Ищем все сообщения
            message_selectors = [
                ".tgme_widget_message",
                ".tgme_widget_message_wrap .tgme_widget_message",
                "[data-post]"
            ]
            
            messages = []
            for selector in message_selectors:
                try:
                    found_messages = driver.find_elements(By.CSS_SELECTOR, selector)
                    if found_messages:
                        messages = found_messages
                        logger.info(f"✅ Найдено {len(found_messages)} сообщений через селектор: {selector}")
                        break
                except Exception as e:
                    logger.debug(f"Селектор {selector} не сработал: {e}")
                    continue
            
            if not messages:
                logger.warning(f"❌ Сообщения не найдены для {group['username']}")
                return []
            
            # Парсим каждое сообщение
            logger.info(f"🔄 Обрабатываем {len(messages)} сообщений...")
            processed = 0
            
            for message_elem in messages:
                if len(posts) >= limit:
                    break
                
                try:
                    post_data = self.extract_message_data(driver, message_elem, group)
                    if post_data:
                        posts.append(post_data)
                        logger.debug(f"✅ Пост #{len(posts)}: {post_data['title'][:50]}...")
                    
                    processed += 1
                    if processed % 5 == 0:
                        logger.info(f"📊 Обработано {processed}/{len(messages)}, извлечено {len(posts)} валидных постов")
                        
                except Exception as e:
                    logger.error(f"❌ Ошибка обработки сообщения: {e}")
                    continue
            
            logger.info(f"✅ Selenium: получено {len(posts)} постов из {group['username']}")
            self.stats['total_posts_parsed'] += len(posts)
            
            return posts
            
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга {group['username']}: {e}")
            return []
            
        finally:
            if driver:
                self.cleanup_driver()

    def get_group_posts_selenium(self, group_type: str = 'all', limit: int = 3) -> List[Dict]:
        """Главный метод получения постов через Selenium"""
        if not self.selenium_enabled:
            logger.error("❌ Selenium не доступен")
            return self.get_smart_mock_posts(group_type, limit)
        
        self.last_attempt = datetime.now()
        
        if not self.should_attempt_parsing():
            logger.info(f"⏳ Парсинг пропущен (кулдаун: {self.failure_count * 3} мин)")
            return self.get_cached_or_mock_posts(group_type, limit)
        
        all_posts = []
        success_count = 0
        
        try:
            # Парсим каждую группу
            for group in self.groups:
                if group_type != 'all' and group['type'] != group_type:
                    continue
                
                try:
                    # Пауза между группами
                    if success_count > 0:
                        time.sleep(random.uniform(3, 7))
                    
                    group_posts = self.parse_group_selenium(group, limit)
                    
                    if group_posts:
                        all_posts.extend(group_posts)
                        success_count += 1
                        self.stats['selenium_success'] += 1
                        logger.info(f"✅ {group['username']}: {len(group_posts)} постов")
                    else:
                        self.stats['selenium_failures'] += 1
                        logger.warning(f"⚠️ {group['username']}: постов не получено")
                        
                except Exception as e:
                    logger.error(f"❌ Ошибка парсинга группы {group['username']}: {e}")
                    self.stats['selenium_failures'] += 1
                    continue
            
            # Обработка результатов
            if all_posts:
                # Убираем дубликаты и сортируем по дате
                unique_posts = self.deduplicate_posts(all_posts)
                sorted_posts = sorted(unique_posts, key=lambda x: x.get('date', ''), reverse=True)
                
                # Обновляем кэш
                self.posts_cache = sorted_posts[:limit * 2]  # Храним чуть больше
                self.last_update = datetime.now()
                self.failure_count = max(0, self.failure_count - 1)
                
                logger.info(f"✅ Selenium парсинг успешен: {len(sorted_posts)} уникальных постов")
                return sorted_posts[:limit]
            else:
                self.failure_count += 1
                logger.warning(f"❌ Selenium парсинг неудачен (попытка #{self.failure_count})")
                return self.get_smart_mock_posts(group_type, limit)
                
        except Exception as e:
            self.failure_count += 1
            logger.error(f"❌ Критическая ошибка Selenium парсинга: {e}")
            return self.get_smart_mock_posts(group_type, limit)

    def deduplicate_posts(self, posts: List[Dict]) -> List[Dict]:
        """Удаление дубликатов постов"""
        seen_texts = set()
        unique_posts = []
        
        for post in posts:
            # Создаем "отпечаток" поста
            text_fingerprint = re.sub(r'\W+', '', post.get('text', '')[:100].lower())
            
            if text_fingerprint not in seen_texts and len(text_fingerprint) > 10:
                seen_texts.add(text_fingerprint)
                unique_posts.append(post)
        
        return unique_posts

    # Методы из оригинального кода (адаптированные)
    def is_valid_post_content(self, text: str, animal_type: str) -> bool:
        """Проверка валидности контента поста"""
        text_lower = text.lower()
        
        # Ключевые слова для животных
        if animal_type == 'cats':
            animal_keywords = ['кот', 'кошк', 'котен', 'мурз', 'мяу', 'питомец']
        else:
            animal_keywords = ['собак', 'щен', 'пес', 'лай', 'питомец']
        
        # Ключевые слова для пристройства
        action_keywords = ['ищет', 'дом', 'пристрой', 'отда', 'найден', 'семь', 'хозя']
        
        # Исключающие слова
        exclude_keywords = ['продам', 'куплю', 'услуг', 'реклам', 'спам']
        
        has_animal = any(keyword in text_lower for keyword in animal_keywords)
        has_action = any(keyword in text_lower for keyword in action_keywords)
        has_exclude = any(keyword in text_lower for keyword in exclude_keywords)
        
        return has_animal and has_action and not has_exclude and len(text) > 30

    def extract_smart_title(self, text: str, animal_type: str) -> str:
        """Умное извлечение заголовка"""
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        keywords = ['ищет', 'дом', 'пристрой', 'отда', 'найден', 'потерял']
        
        for line in lines[:3]:
            if len(line) > 15 and any(keyword in line.lower() for keyword in keywords):
                title = re.sub(r'[^\w\s\-\.,!?а-яёА-ЯЁ]', ' ', line)
                title = re.sub(r'\s+', ' ', title).strip()
                
                if len(title) > 60:
                    title = title[:60] + "..."
                
                return title
        
        # Дефолтные заголовки
        defaults = {
            'cats': ['Кошка ищет дом', 'Котенок в добрые руки', 'Пристройство кошки'],
            'dogs': ['Собака ищет дом', 'Щенок в добрые руки', 'Пристройство собаки']
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
        
        # Российские телефоны
        phone_patterns = [
            r'\+?7[\s\-]?\(?9\d{2}\)?\s?[\d\s\-]{7,10}',
            r'\+?8[\s\-]?\(?9\d{2}\)?\s?[\d\s\-]{7,10}',
            r'9\d{2}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}'
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

    def get_cached_or_mock_posts(self, group_type: str, limit: int) -> List[Dict]:
        """Получение кэшированных или мок-постов"""
        # Фильтруем кэш по типу
        cached = [p for p in self.posts_cache 
                 if group_type == 'all' or p['type'] == group_type]
        
        if cached and len(cached) >= limit:
            return cached[:limit]
        else:
            self.stats['fallback_used'] += 1
            return self.get_smart_mock_posts(group_type, limit)

    def get_smart_mock_posts(self, group_type: str, limit: int) -> List[Dict]:
        """Умные моки с реалистичными данными"""
        if group_type == 'cats':
            mock_data = {
                'names': ['Мурка', 'Барсик', 'Снежок', 'Рыжик', 'Тишка', 'Пушок', 'Дымка', 'Мася'],
                'ages': ['2 месяца', '3-4 месяца', '6 месяцев', '1 год', '2 года', '3 года'],
                'colors': ['рыжий', 'серый', 'черный', 'белый', 'трехцветная', 'полосатый', 'дымчатый'],
                'traits': ['игривый', 'ласковый', 'спокойный', 'умный', 'дружелюбный', 'активный'],
                'health': ['привит', 'здоров', 'кастрирован', 'стерилизована', 'обработан от паразитов']
            }
        else:
            mock_data = {
                'names': ['Бобик', 'Шарик', 'Дружок', 'Лайка', 'Джек', 'Белка', 'Рекс', 'Найда'],
                'ages': ['3 месяца', '4-5 месяцев', '6 месяцев', '1 год', '2 года', '3 года'],
                'colors': ['черный', 'коричневый', 'белый', 'рыжий', 'пятнистый', 'серый'],
                'traits': ['активный', 'дружелюбный', 'умный', 'послушный', 'энергичный', 'спокойный'],
                'health': ['привит', 'здоров', 'кастрирован', 'чипирован', 'обработан от паразитов']
            }
        
        posts = []
        animal_emoji = '🐱' if group_type == 'cats' else '🐶'
        animal_name = 'котик' if group_type == 'cats' else 'щенок'
        
        for i in range(limit):
            name = random.choice(mock_data['names'])
            age = random.choice(mock_data['ages'])
            color = random.choice(mock_data['colors'])
            trait = random.choice(mock_data['traits'])
            health = random.choice(mock_data['health'])
            
            # Генерируем реалистичный текст
            descriptions = [
                f"{animal_name.capitalize()} {name}, возраст {age}, {color} окрас. {trait.capitalize()}, {health}. К лотку приучен, с другими животными ладит. Ищет заботливую семью!",
                f"Ищет дом {animal_name} {name}. Возраст: {age}. Окрас: {color}. Характер: {trait}. Здоровье: {health}. Очень нуждается в любящих хозяевах!",
                f"{name} - {color} {animal_name}, {age}. {trait.capitalize()} и {health}. Приучен к порядку. Мечтает о теплом доме и заботливых руках!"
            ]
            
            description = random.choice(descriptions)
            
            posts.append({
                'id': f'mock_selenium_{i + 2000}',
                'title': f'{animal_emoji} {name} ищет дом',
                'description': description,
                'text': description,
                'date': self.generate_recent_date(),
                'url': f'https://t.me/lapki_ruchki_yalta/{i + 2000}',
                'contact': self.generate_realistic_contact(),
                'photo_url': f'https://picsum.photos/400/300?random={i + 200}',
                'has_photo': True,
                'type': group_type,
                'source': 'mock_selenium',
                'extracted_at': datetime.now().isoformat()
            })
        
        return posts

    def generate_recent_date(self) -> str:
        """Генерация недавней даты"""
        days_ago = random.randint(0, 7)
        hours_ago = random.randint(0, 23)
        recent_date = datetime.now() - timedelta(days=days_ago, hours=hours_ago)
        return recent_date.strftime('%d.%m.%Y %H:%M')

    def generate_realistic_contact(self) -> str:
        """Генерация реалистичных контактов"""
        phone_endings = ['45-67', '78-90', '12-34', '56-78', '90-12', '23-45', '67-89', '34-56']
        usernames = ['volunteer', 'helper', 'animals_yal', 'pet_help', 'rescue', 'yalta_pets']
        
        contacts = []
        
        # Телефон (всегда)
        phone = f"+7 978 {random.randint(100, 999)}-{random.choice(phone_endings)}"
        contacts.append(phone)
        
        # Username (иногда)
        if random.choice([True, False]):
            username = f"@{random.choice(usernames)}{random.randint(1, 99)}"
            contacts.append(username)
        
        return ' • '.join(contacts)

    def get_statistics(self) -> Dict:
        """Получение статистики работы парсера"""
        return {
            **self.stats,
            'selenium_enabled': self.selenium_enabled,
            'failure_count': self.failure_count,
            'cached_posts': len(self.posts_cache),
            'last_update': self.last_update.isoformat() if self.last_update else None,
            'can_parse': self.should_attempt_parsing(),
            'groups_count': len(self.groups)
        }


class EnhancedCatBotWithSelenium:
    """Улучшенный бот с Selenium парсингом"""
    
    def __init__(self):
        self.token = os.environ.get('TOKEN')
        if not self.token:
            logger.error("❌ TOKEN не найден!")
            exit(1)
        
        self.bot = telebot.TeleBot(self.token)
        self.parser = AdvancedSeleniumTelegramParser()
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
            
            # Индикатор источника данных с более подробной информацией
            if post.get('source') == 'selenium':
                source_tag = ' 🤖'
                status = "✅ Selenium парсинг"
            elif post.get('source') == 'mock_selenium':
                source_tag = ' 🎭'
                status = "⚠️ Демо (Selenium недоступен)"
            else:
                source_tag = ' 📋'
                status = "ℹ️ Пример объявления"
            
            post_text = (
                f"{emoji} <b>{post['title']}</b>{source_tag}\n\n"
                f"{post['description']}\n\n"
                f"📅 {post['date']}\n"
                f"📞 {post['contact']}\n"
                f"🔗 <a href='{post['url']}'>Открыть в группе</a>\n\n"
                f"<i>{status}</i>"
            )
            
            # Ограничиваем длину сообщения
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
        """Отправляет все посты с подробной статистикой парсера"""
        try:
            # Отправляем сообщение о начале загрузки
            loading_msg = self.bot.send_message(
                chat_id,
                "🔄 <b>Загружаем объявления...</b>\n\n"
                "⏳ Парсим Telegram-группы с помощью Selenium\n"
                "🤖 Это может занять 30-60 секунд",
                parse_mode="HTML"
            )
            
            # Получаем посты
            posts = self.parser.get_group_posts_selenium(animal_type, 5)
            
            # Удаляем сообщение о загрузке
            try:
                self.bot.delete_message(chat_id, loading_msg.message_id)
            except:
                pass
            
            if not posts:
                self.bot.send_message(
                    chat_id,
                    "😿 Сейчас нет доступных объявлений.\n"
                    f"📢 Проверьте группу напрямую"
                )
                return
            
            # Получаем статистику парсера
            stats = self.parser.get_statistics()
            
            group_name = "Лапки-ручки Ялта" if animal_type == 'cats' else "Ялта Животные"
            group_url = self.parser.groups[0]['url'] if animal_type == 'cats' else self.parser.groups[1]['url']
            
            # Статистика по источникам
            selenium_count = sum(1 for p in posts if p.get('source') == 'selenium')
            mock_count = len(posts) - selenium_count
            
            # Определяем статус парсинга
            if selenium_count > 0:
                status_text = f"🤖 <b>Selenium парсинг успешен</b>: {selenium_count} из {len(posts)}"
                status_emoji = "✅"
            elif not self.parser.selenium_enabled:
                status_text = "⚠️ <b>Selenium не установлен</b>\n📋 Показаны демо-объявления"
                status_emoji = "🔧"
            elif self.parser.failure_count > 0:
                status_text = f"⚠️ <b>Парсинг временно недоступен</b> (попыток: {self.parser.failure_count})\n🎭 Показаны примеры объявлений"
                status_emoji = "🔄"
            else:
                status_text = "📋 <b>Примеры объявлений</b>"
                status_emoji = "📝"
            
            # Информация о следующей попытке
            next_attempt_info = ""
            if self.parser.failure_count > 0:
                cooldown_minutes = min(self.parser.failure_count * 3, 45)
                next_attempt = ""
                if self.parser.last_attempt:
                    time_passed = (datetime.now() - self.parser.last_attempt).total_seconds() / 60
                    remaining = max(0, cooldown_minutes - time_passed)
                    if remaining > 0:
                        next_attempt = f"\n⏰ Следующая попытка через: {int(remaining)} мин"
                
                next_attempt_info = f"\n🔄 Автообновление: каждые {cooldown_minutes} мин{next_attempt}"
            
            # Технические детали для отладки
            tech_info = ""
            if selenium_count > 0:
                tech_info = f"\n\n📊 <b>Технические детали:</b>"
                tech_info += f"\n• Успешных запросов: {stats['selenium_success']}"
                tech_info += f"\n• Неудачных запросов: {stats['selenium_failures']}"
                tech_info += f"\n• Всего постов извлечено: {stats['total_posts_parsed']}"
            
            header_text = (
                f"{status_emoji} <b>{'КОШКИ' if animal_type == 'cats' else 'СОБАКИ'} ИЩУТ ДОМ</b>\n\n"
                f"📢 Группа: <a href='{group_url}'>{group_name}</a>\n\n"
                f"{status_text}{next_attempt_info}{tech_info}"
            )
            
            self.bot.send_message(chat_id, header_text, parse_mode="HTML")
            
            # Отправляем посты с паузами
            for i, post in enumerate(posts):
                self.send_post(chat_id, post)
                if i < len(posts) - 1:  # Пауза между постами, кроме последнего
                    time.sleep(1)
            
            # Футер с инструкциями и технической информацией
            footer_text = (
                "💡 <b>Как помочь животным:</b>\n\n"
                f"🏠 <b>Взять {'кошку' if animal_type == 'cats' else 'собаку'}:</b>\n"
                "Свяжитесь по контактам из объявления\n\n"
                f"📢 <b>Актуальные объявления:</b>\n<a href='{group_url}'>Перейти в группу</a>\n\n"
                "🤝 <b>Стать волонтером:</b>\nНапишите в группу или координаторам\n\n"
                "🔄 <b>Команды бота:</b>\n"
                "/update - принудительное обновление\n"
                "/selenium_status - техническая диагностика"
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

    def setup_handlers(self):
        """Обработчики команд и сообщений с дополнительными Selenium командами"""
        
        @self.bot.message_handler(commands=['start'])
        def start_handler(message):
            self.stats["users"].add(message.from_user.id)
            self.stats["messages"] += 1
            
            selenium_status = "✅ активен" if self.parser.selenium_enabled else "❌ не установлен"
            
            welcome_text = f"""👋 <b>Добро пожаловать!</b>

🐾 Помощник по уличным животным Ялты
🤖 Selenium парсинг: {selenium_status}

Выберите раздел:
🏥 <b>Стерилизация</b> - информация о программах
🏠 <b>Пристройство</b> - животные ищут дом  
📞 <b>Контакты</b> - связь с волонтерами
ℹ️ <b>О проекте</b> - наша деятельность

<i>💡 Бот использует Selenium для парсинга Telegram-групп</i>"""
            
            self.bot.send_message(
                message.chat.id, 
                welcome_text, 
                parse_mode="HTML",
                reply_markup=self.get_main_keyboard()
            )
        
        @self.bot.message_handler(commands=['selenium_status'])
        def selenium_status_handler(message):
            """Подробная диагностика Selenium парсера"""
            try:
                stats = self.parser.get_statistics()
                
                status_lines = ["🤖 <b>SELENIUM ДИАГНОСТИКА</b>\n"]
                
                # Основной статус
                if self.parser.selenium_enabled:
                    status_lines.append("✅ <b>Selenium:</b> Установлен и готов")
                    
                    # Статистика работы
                    status_lines.append(f"📊 <b>Статистика:</b>")
                    status_lines.append(f"• Успешных парсингов: {stats['selenium_success']}")
                    status_lines.append(f"• Неудачных попыток: {stats['selenium_failures']}")
                    status_lines.append(f"• Использовано резервов: {stats['fallback_used']}")
                    status_lines.append(f"• Всего постов извлечено: {stats['total_posts_parsed']}")
                    
                    # Кэш
                    status_lines.append(f"\n💾 <b>Кэш:</b> {stats['cached_posts']} постов")
                    
                    # Последнее обновление
                    if stats['last_update']:
                        last_update = datetime.fromisoformat(stats['last_update'])
                        formatted_date = last_update.strftime('%d.%m.%Y %H:%M:%S')
                        status_lines.append(f"🕐 <b>Последнее обновление:</b> {formatted_date}")
                    
                    # Статус готовности
                    if stats['can_parse']:
                        status_lines.append("🟢 <b>Готовность:</b> Готов к парсингу")
                    else:
                        cooldown = min(stats['failure_count'] * 3, 45)
                        time_passed = 0
                        if self.parser.last_attempt:
                            time_passed = int((datetime.now() - self.parser.last_attempt).total_seconds() / 60)
                        remaining = max(0, cooldown - time_passed)
                        status_lines.append(f"🟡 <b>Кулдаун:</b> {remaining} мин (из {cooldown})")
                    
                else:
                    status_lines.append("❌ <b>Selenium:</b> Не установлен")
                    status_lines.append("\n📦 <b>Для установки:</b>")
                    status_lines.append("pip install selenium undetected-chromedriver")
                
                # Группы для парсинга
                status_lines.append(f"\n📢 <b>Отслеживаемые группы:</b> {stats['groups_count']}")
                for group in self.parser.groups:
                    group_emoji = "🐱" if group['type'] == 'cats' else "🐶"
                    status_lines.append(f"{group_emoji} {group['username']}")
                
                # Быстрый тест (если Selenium доступен)
                if self.parser.selenium_enabled:
                    status_lines.append("\n🧪 <b>Быстрый тест:</b>")
                    try:
                        # Создаем тестовый драйвер
                        test_driver = self.parser.setup_selenium_driver(headless=True)
                        test_driver.quit()
                        status_lines.append("✅ Драйвер создается успешно")
                    except Exception as e:
                        status_lines.append(f"❌ Ошибка драйвера: {str(e)[:50]}...")
                
                self.bot.send_message(
                    message.chat.id,
                    "\n".join(status_lines),
                    parse_mode="HTML"
                )
                
            except Exception as e:
                self.bot.send_message(message.chat.id, f"❌ Ошибка диагностики: {e}")
        
        @self.bot.message_handler(commands=['update'])
        def update_handler(message):
            """Принудительное обновление через Selenium"""
            loading_msg = self.bot.send_message(
                message.chat.id, 
                "🔄 <b>Принудительное обновление...</b>\n\n"
                "🤖 Запускаем Selenium парсинг\n"
                "⏳ Подождите 30-60 секунд",
                parse_mode="HTML"
            )
            
            # Сброс ограничений
            self.parser.posts_cache = []
            self.parser.last_update = None
            self.parser.failure_count = max(0, self.parser.failure_count - 2)
            
            try:
                # Запускаем парсинг
                posts = self.parser.get_group_posts_selenium('all', 6)
                stats = self.parser.get_statistics()
                
                selenium_count = sum(1 for p in posts if p.get('source') == 'selenium')
                mock_count = len(posts) - selenium_count
                
                # Удаляем сообщение о загрузке
                try:
                    self.bot.delete_message(message.chat.id, loading_msg.message_id)
                except:
                    pass
                
                status_text = f"🔄 <b>Результат принудительного обновления:</b>\n\n"
                
                if selenium_count > 0:
                    status_text += f"✅ <b>Selenium парсинг успешен!</b>\n"
                    status_text += f"🤖 Получено через Selenium: {selenium_count}\n"
                    status_text += f"📋 Резервных примеров: {mock_count}\n"
                    status_text += f"📊 Всего успешных парсингов: {stats['selenium_success']}"
                else:
                    status_text += f"⚠️ <b>Selenium парсинг недоступен</b>\n"
                    if not self.parser.selenium_enabled:
                        status_text += f"🔧 Причина: Selenium не установлен\n"
                    else:
                        status_text += f"🔄 Неудачных попыток: {stats['selenium_failures']}\n"
                    status_text += f"🎭 Показаны примеры: {mock_count}"
                
                self.bot.send_message(message.chat.id, status_text, parse_mode="HTML")
                
            except Exception as e:
                logger.error(f"❌ Ошибка принудительного обновления: {e}")
                try:
                    self.bot.delete_message(message.chat.id, loading_msg.message_id)
                except:
                    pass
                self.bot.send_message(
                    message.chat.id, 
                    f"❌ <b>Ошибка обновления:</b>\n\n"
                    f"🔧 {str(e)[:100]}...\n\n"
                    f"💡 Попробуйте /selenium_status для диагностики",
                    parse_mode="HTML"
                )

        # Остальные обработчики остаются такими же как в оригинальном коде
        @self.bot.message_handler(func=lambda m: m.text == "🏠 Пристройство")
        def adoption_handler(message):
            self.stats["users"].add(message.from_user.id)
            self.stats["messages"] += 1
            
            stats = self.parser.get_statistics()
            selenium_posts = sum(1 for p in self.parser.posts_cache if p.get('source') == 'selenium')
            
            status_line = ""
            if selenium_posts > 0:
                status_line = f"\n🤖 <b>Статус:</b> Selenium активен ({selenium_posts} объявлений)"
            elif not self.parser.selenium_enabled:
                status_line = f"\n🔧 <b>Статус:</b> Selenium не установлен"
            elif self.parser.failure_count > 0:
                status_line = f"\n⚠️ <b>Статус:</b> Парсинг временно недоступен"
            else:
                status_line = f"\n📋 <b>Статус:</b> Показаны примеры"
            
            info_text = f"""🏠 <b>Пристройство животных</b>{status_line}

Выберите действие:

🐱 <b>Кошки ищут дом</b>
Актуальные объявления через Selenium

🐶 <b>Собаки ищут дом</b>
Актуальные объявления через Selenium

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

        # Остальные обработчики (стерилизация, контакты и т.д.) остаются без изменений
        # ... [здесь должны быть остальные обработчики из оригинального кода]

    def setup_routes(self):
        """Flask маршруты с дополнительной информацией о Selenium"""
        
        @self.app.route('/')
        def home():
            stats = self.parser.get_statistics()
            selenium_posts = sum(1 for p in self.parser.posts_cache if p.get('source') == 'selenium')
            
            return jsonify({
                "status": "🤖 Enhanced Animal Bot with Selenium",
                "version": "3.0-selenium",
                "time": datetime.now().strftime('%H:%M:%S'),
                "users": len(self.stats["users"]), 
                "messages": self.stats["messages"],
                "selenium": {
                    "enabled": self.parser.selenium_enabled,
                    "success_count": stats['selenium_success'],
                    "failure_count": stats['selenium_failures'],
                    "fallback_used": stats['fallback_used'],
                    "posts_extracted": stats['total_posts_parsed'],
                    "cached_posts": stats['cached_posts'],
                    "selenium_posts": selenium_posts,
                    "can_parse": stats['can_parse'],
                    "last_update": stats['last_update']
                },
                "groups": [g['url'] for g in self.parser.groups]
            })
        
        @self.app.route('/selenium_test')
        def selenium_test():
            """API endpoint для тестирования Selenium"""
            if not self.parser.selenium_enabled:
                return jsonify({
                    "status": "error",
                    "message": "Selenium не установлен",
                    "install_command": "pip install selenium undetected-chromedriver"
                }), 400
            
            try:
                # Быстрый тест создания драйвера
                start_time = time.time()
                test_driver = self.parser.setup_selenium_driver(headless=True)
                setup_time = time.time() - start_time
                
                # Тест загрузки простой страницы
                load_start = time.time()
                test_driver.get("https://httpbin.org/user-agent")
                load_time = time.time() - load_start
                
                user_agent = test_driver.find_element(By.TAG_NAME, "body").text
                test_driver.quit()
                
                return jsonify({
                    "status": "success",
                    "setup_time": round(setup_time, 2),
                    "load_time": round(load_time, 2),
                    "user_agent": user_agent[:100],
                    "timestamp": datetime.now().isoformat()
                })
                
            except Exception as e:
                return jsonify({
                    "status": "error",
                    "message": str(e)[:200],
                    "timestamp": datetime.now().isoformat()
                }), 500
        
        @self.app.route('/posts')
        def posts_api():
            try:
                posts = self.parser.get_cached_or_mock_posts('all', 10)
                stats = self.parser.get_statistics()
                selenium_count = sum(1 for p in posts if p.get('source') == 'selenium')
                
                return jsonify({
                    "status": "ok",
                    "total": len(posts),
                    "selenium_posts": selenium_count,
                    "mock_posts": len(posts) - selenium_count,
                    "posts": posts,
                    "selenium_stats": stats
                })
            except Exception as e:
                return jsonify({"status": "error", "message": str(e)}), 500
        
        @self.app.route('/force_selenium_update')
        def force_selenium_update():
            """API для принудительного Selenium обновления"""
            try:
                # Сброс ограничений
                self.parser.posts_cache = []
                self.parser.last_update = None  
                self.parser.failure_count = max(0, self.parser.failure_count - 2)
                
                start_time = time.time()
                posts = self.parser.get_group_posts_selenium('all', 8)
                parse_time = time.time() - start_time
                
                stats = self.parser.get_statistics()
                selenium_count = sum(1 for p in posts if p.get('source') == 'selenium')
                
                return jsonify({
                    "status": "selenium_updated",
                    "timestamp": datetime.now().isoformat(),
                    "parse_time": round(parse_time, 2),
                    "total_posts": len(posts),
                    "selenium_posts": selenium_count,
                    "mock_posts": len(posts) - selenium_count,
                    "selenium_enabled": self.parser.selenium_enabled,
                    "stats": stats
                })
            except Exception as e:
                logger.error(f"❌ Force selenium update error: {e}")
                return jsonify({"status": "error", "message": str(e)[:200]}), 500

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
        """Запуск Enhanced Animal Bot с Selenium"""
        logger.info("🚀 Запуск Enhanced Animal Bot v3.0 with Selenium...")
        
        # Проверяем доступность Selenium
        if self.parser.selenium_enabled:
            logger.info("✅ Selenium парсинг доступен")
            try:
                # Быстрый тест Selenium
                test_driver = self.parser.setup_selenium_driver(headless=True)
                test_driver.quit()
                logger.info("✅ Selenium драйвер работает корректно")
            except Exception as e:
                logger.warning(f"⚠️ Проблема с Selenium драйвером: {e}")
                self.parser.selenium_enabled = False
        else:
            logger.warning("⚠️ Selenium не доступен - будут использоваться примеры")
        
        # Предзагрузка постов через Selenium
        try:
            logger.info("🔄 Предзагрузка постов через Selenium...")
            posts = self.parser.get_group_posts_selenium('all', 5)
            stats = self.parser.get_statistics()
            
            selenium_count = sum(1 for p in posts if p.get('source') == 'selenium')
            mock_count = len(posts) - selenium_count
            
            if selenium_count > 0:
                logger.info(f"✅ Предзагружено {len(posts)} постов через Selenium (реальных: {selenium_count}, примеров: {mock_count})")
            else:
                logger.warning(f"⚠️ Selenium парсинг неудачен, загружены примеры: {mock_count}")
                
        except Exception as e:
            logger.warning(f"⚠️ Ошибка предзагрузки через Selenium: {e}")
        
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
        
        # Очистка ресурсов при завершении
        self.parser.cleanup_driver()


if __name__ == "__main__":
    # Создание необходимых файлов и папок
    os.makedirs('assets/images', exist_ok=True)
    
    # Создание информационных файлов (если не существуют)
    if not os.path.exists('assets/free_text.html'):
        with open('assets/free_text.html', 'w', encoding='utf-8') as f:
            f.write("""<b>🆓 БЕСПЛАТНАЯ СТЕРИЛИЗАЦИЯ</b>

🏥 <b>Доступные программы:</b>
🔹 Муниципальная программа города Ялты
🔹 Благотворительные фонды защиты животных
🔹 Волонтерские программы стерилизации

📞 <b>Контакты для записи:</b>
🔹 Координатор программы: +7 978 144-90-70
🔹 Клиника "Айболит": +7 978 000-00-11  

⚠️ <b>Важно знать:</b>
⏰ Запись строго заранее! Места ограничены
📅 Программа действует круглый год""")

    if not os.path.exists('assets/paid_text.html'):
        with open('assets/paid_text.html', 'w', encoding='utf-8') as f:
            f.write("""<b>💰 ПЛАТНАЯ СТЕРИЛИЗАЦИЯ</b>

🏥 <b>Ветеринарные клиники Ялты:</b>

🔹 <b>Клиника "Айболит"</b>
   💰 Кошки: от 3000₽ | Коты: от 2500₽
   💰 Собаки: от 5000₽ | Кобели: от 4000₽  
   📞 +7 978 000-00-12
   📍 ул. Московская, 14

🔹 <b>Ветцентр "ВетМир"</b>  
   💰 Кошки: от 2500₽ | Коты: от 2000₽
   💰 Собаки: от 4500₽ | Кобели: от 3500₽
   📞 +7 978 000-00-13  
   📍 ул. Пушкина, 28""")
    
    # Проверка установки зависимостей
    print("🔧 Проверка зависимостей...")
    
    missing_deps = []
    
    try:
        import undetected_chromedriver as uc
        print("✅ undetected-chromedriver установлен")
    except ImportError:
        missing_deps.append("undetected-chromedriver")
    
    try:
        from selenium import webdriver
        print("✅ selenium установлен")
    except ImportError:
        missing_deps.append("selenium")
    
    if missing_deps:
        print(f"\n❌ Не установлены зависимости: {', '.join(missing_deps)}")
        print("📦 Для установки выполните:")
        print(f"pip install {' '.join(missing_deps)}")
        print("\n⚠️ Бот будет работать в режиме примеров без реального парсинга!")
        time.sleep(3)
    else:
        print("✅ Все зависимости для Selenium установлены")
    
    # Информация о системных требованиях
    print("\n📋 Системные требования для Selenium:")
    print("• Chrome/Chromium браузер (устанавливается автоматически)")
    print("• Минимум 512MB RAM для headless режима")  
    print("• Стабильное интернет-соединение")
    
    # Запуск бота
    try:
        logger.info("🚀 Инициализация Enhanced Animal Bot with Selenium...")
        bot = EnhancedCatBotWithSelenium()
        bot.run()
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"💥 Критическая ошибка запуска: {e}")
        print("\n❌ Возможные причины:")
        print("1. Не установлен TOKEN в переменных окружения")
        print("2. Отсутствуют зависимости: pip install selenium undetected-chromedriver")
        print("3. Проблемы с Chrome/Chromium драйвером")
        print("4. Недостаточно памяти для Selenium")
        print("\n🔄 Попробуйте перезапустить через 30 секунд...")
        time.sleep(30)
