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
import random
from urllib.parse import quote_plus

# 🔧 Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class AdvancedGroupParser:
    """Улучшенный парсер открытых групп с несколькими стратегиями"""
    
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
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
        ]
    
    def get_headers(self):
        """Получает случайные headers"""
        return {
            'User-Agent': random.choice(self.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0',
        }
    
    def get_group_posts(self, group_type: str = 'all', limit: int = 3) -> List[Dict]:
        """Получает посты с использованием нескольких стратегий"""
        posts = []
        
        for group in self.groups:
            if group_type != 'all' and group['type'] != group_type:
                continue
            
            # Стратегия 1: Парсинг через веб-версию
            group_posts = self.parse_web_version(group, limit)
            if group_posts:
                posts.extend(group_posts)
                continue
            
            # Стратегия 2: Альтернативные методы
            group_posts = self.parse_alternative_methods(group, limit)
            if group_posts:
                posts.extend(group_posts)
                continue
            
            logger.warning(f"⚠️ Не удалось получить посты из {group['username']}")
        
        if posts:
            self.posts_cache = posts
            self.last_update = datetime.now()
            logger.info(f"✅ Получено {len(posts)} постов")
        else:
            logger.warning("⚠️ Не найдено постов, используем моки")
            posts = self.get_enhanced_mock_posts(group_type, limit)
        
        return posts[:limit] if posts else []
    
    def parse_web_version(self, group: Dict, limit: int) -> List[Dict]:
        """Парсинг через веб-версию Telegram"""
        try:
            session = requests.Session()
            session.headers.update(self.get_headers())
            
            # Пробуем разные URL форматы
            urls_to_try = [
                f'https://t.me/s/{group["username"]}',
                f'https://telegram.me/s/{group["username"]}',
            ]
            
            for url in urls_to_try:
                try:
                    logger.info(f"🌐 Попытка загрузки: {url}")
                    
                    response = session.get(url, timeout=15, allow_redirects=True)
                    
                    if response.status_code == 200:
                        return self.parse_html_content(response.text, group, limit)
                    else:
                        logger.warning(f"❌ Статус {response.status_code} для {url}")
                        
                except requests.RequestException as e:
                    logger.error(f"❌ Ошибка запроса к {url}: {e}")
                    time.sleep(2)  # Пауза между попытками
                    continue
            
        except Exception as e:
            logger.error(f"❌ Общая ошибка парсинга веб-версии: {e}")
        
        return []
    
    def parse_html_content(self, html: str, group: Dict, limit: int) -> List[Dict]:
        """Парсинг HTML контента"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Ищем сообщения по разным селекторам
            message_selectors = [
                'div.tgme_widget_message',
                'div[data-post]',
                'div.tgme_widget_message_wrap',
            ]
            
            messages = []
            for selector in message_selectors:
                found = soup.select(selector)
                if found:
                    messages = found
                    logger.info(f"✅ Найдено {len(found)} сообщений с селектором: {selector}")
                    break
            
            if not messages:
                logger.warning("❌ Сообщения не найдены")
                return []
            
            posts = []
            for msg_div in messages[:limit * 2]:  # Берем больше для фильтрации
                post_data = self.parse_message_div(msg_div, group)
                if (post_data and 
                    self.is_animal_related(post_data.get('text', ''), group['type']) and
                    len(post_data.get('text', '')) > 20):  # Минимальная длина текста
                    
                    posts.append(post_data)
                    if len(posts) >= limit:
                        break
            
            return posts
            
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга HTML: {e}")
            return []
    
    def parse_alternative_methods(self, group: Dict, limit: int) -> List[Dict]:
        """Альтернативные методы получения данных"""
        try:
            # Можно добавить другие методы, например:
            # - RSS feeds (если доступны)
            # - API через прокси
            # - Кэширование через внешние сервисы
            
            logger.info(f"🔄 Используем альтернативные методы для {group['username']}")
            
            # Пока возвращаем реалистичные моки
            return self.get_realistic_mock_posts(group, limit)
            
        except Exception as e:
            logger.error(f"❌ Ошибка альтернативных методов: {e}")
            return []
    
    def parse_message_div(self, div, group) -> Optional[Dict]:
        """Улучшенный парсинг сообщения"""
        try:
            # Извлечение ID поста
            post_id = (div.get('data-post', '') or 
                      div.get('data-message-id', '') or 
                      str(hash(str(div)[:100]))[-6:])
            
            if '/' in post_id:
                post_id = post_id.split('/')[-1]
            
            # Текст сообщения
            text_selectors = [
                'div.tgme_widget_message_text',
                'div.message_text',
                'div.text',
                '.tgme_widget_message_text'
            ]
            
            text = ""
            for selector in text_selectors:
                text_elem = div.select_one(selector)
                if text_elem:
                    text = text_elem.get_text(strip=True)
                    break
            
            if not text:
                # Пробуем извлечь любой текст из div
                text = div.get_text(strip=True)
                if len(text) > 500:  # Слишком много текста, берем первую часть
                    text = text[:500] + "..."
            
            # Дата
            date_str = "Недавно"
            date_selectors = ['time[datetime]', 'time', '.tgme_widget_message_date']
            
            for selector in date_selectors:
                date_elem = div.select_one(selector)
                if date_elem:
                    datetime_attr = date_elem.get('datetime')
                    if datetime_attr:
                        try:
                            dt = datetime.fromisoformat(datetime_attr.replace('Z', '+00:00'))
                            date_str = dt.strftime('%d.%m.%Y %H:%M')
                        except:
                            date_str = date_elem.get_text(strip=True) or "Недавно"
                    break
            
            # Фото
            photo_url = self.extract_photo_url(div)
            
            if not text or len(text) < 10:
                return None
            
            return {
                'id': post_id or 'unknown',
                'text': text,
                'date': date_str,
                'url': f"{group['url']}/{post_id}" if post_id else group['url'],
                'title': self.extract_title(text, group['type']),
                'description': self.extract_description(text),
                'contact': self.extract_contact(text),
                'photo_url': photo_url,
                'has_photo': bool(photo_url),
                'type': group['type'],
                'source': 'parsed'
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга div: {e}")
            return None
    
    def extract_photo_url(self, div) -> Optional[str]:
        """Извлечение URL фото из div"""
        try:
            # Различные способы найти фото
            photo_selectors = [
                'a.tgme_widget_message_photo_wrap',
                'div.tgme_widget_message_photo_wrap', 
                '.tgme_widget_message_photo_wrap',
                'img',
                '[style*="background-image"]'
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
                    
                    # Из src атрибута
                    src = photo_elem.get('src')
                    if src and src.startswith('http'):
                        return src
                    
                    # Из data-src
                    data_src = photo_elem.get('data-src')
                    if data_src and data_src.startswith('http'):
                        return data_src
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения фото: {e}")
            return None
    
    def extract_title(self, text: str, animal_type: str) -> str:
        """Извлечение заголовка"""
        try:
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            
            for line in lines[:3]:
                if len(line) > 15 and len(line) < 100:
                    # Очистка от лишних символов
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
            
        except:
            return "Животное ищет дом"
    
    def extract_description(self, text: str) -> str:
        """Извлечение описания"""
        # Удаляем контакты и ссылки
        clean_text = re.sub(r'@\w+|https?://\S+|\+?[78][\d\s\-\(\)]+', '', text)
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        
        if len(clean_text) > 200:
            # Ищем конец предложения
            sentences = clean_text.split('.')
            result = ""
            for sentence in sentences:
                if len(result + sentence) < 200:
                    result += sentence + ". "
                else:
                    break
            clean_text = result.strip() or clean_text[:200] + "..."
        
        return clean_text
    
    def extract_contact(self, text: str) -> str:
        """Извлечение контактов"""
        contacts = []
        
        # Телефоны
        phone_patterns = [
            r'\+?[78][\s\-]?\(?9\d{2}\)?\s?[\d\s\-]{7,10}',
            r'\b9\d{2}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}\b'
        ]
        
        for pattern in phone_patterns:
            phones = re.findall(pattern, text)
            contacts.extend([re.sub(r'[\s\-\(\)]', '', phone) for phone in phones[:1]])
        
        # Username
        usernames = re.findall(r'@\w+', text)
        contacts.extend(usernames[:1])
        
        return ' • '.join(contacts) if contacts else "См. в группе"
    
    def is_animal_related(self, text: str, animal_type: str) -> bool:
        """Проверка на тематику животных"""
        text_lower = text.lower()
        
        if animal_type == 'cats':
            keywords = [
                'кот', 'кошк', 'котен', 'котик', 'мурз', 'мяу',
                'кастр', 'стерил', 'привит', 'пристрой', 'дом',
                'котята', 'мама-кошка', 'беременная', 'питомец',
                'лоток', 'корм', 'ищет', 'семь', 'хозяин'
            ]
        else:
            keywords = [
                'собак', 'щен', 'пес', 'гав', 'лай', 'овчарк',
                'дог', 'терьер', 'пристрой', 'дом', 'щенок',
                'щенки', 'питомец', 'породист', 'метис',
                'выгул', 'ошейник', 'поводок', 'ищет'
            ]
        
        # Проверяем наличие ключевых слов
        matches = sum(1 for keyword in keywords if keyword in text_lower)
        
        # Исключаем неподходящие посты
        excluded = ['продам', 'куплю', 'услуг', 'ремонт', 'работ']
        has_excluded = any(word in text_lower for word in excluded)
        
        return matches >= 2 and not has_excluded and len(text) > 30
    
    def get_realistic_mock_posts(self, group: Dict, limit: int) -> List[Dict]:
        """Реалистичные моки на основе реальных данных"""
        if group['type'] == 'cats':
            templates = [
                {
                    'title': 'Котенок {} ищет дом',
                    'description': 'Возраст: {} месяца, {}, {} окрас. Здоров, привит, {}. К лотку приучен, с другими животными ладит.',
                    'names': ['Мурзик', 'Барсик', 'Снежок', 'Рыжик', 'Пушок', 'Тишка'],
                    'ages': ['1-2', '2-3', '3-4', '4-5'],
                    'genders': ['мальчик', 'девочка'],
                    'colors': ['рыжий', 'серый', 'черный', 'белый', 'трехцветный', 'полосатый'],
                    'traits': ['очень игривый', 'ласковый', 'спокойный', 'активный', 'умный']
                }
            ]
        else:
            templates = [
                {
                    'title': 'Щенок {} ищет дом',
                    'description': 'Возраст: {} месяцев, {}, {} окрас. Здоров, привит, {}. Хорошо ладит с детьми.',
                    'names': ['Бобик', 'Шарик', 'Дружок', 'Лайка', 'Джек', 'Белка'],
                    'ages': ['2-3', '3-4', '4-6', '6-8'],
                    'genders': ['мальчик', 'девочка'],
                    'colors': ['черный', 'коричневый', 'белый', 'рыжий', 'пятнистый'],
                    'traits': ['очень активный', 'дружелюбный', 'умный', 'послушный', 'энергичный']
                }
            ]
        
        posts = []
        template = templates[0]
        
        for i in range(limit):
            name = random.choice(template['names'])
            age = random.choice(template['ages'])
            gender = random.choice(template['genders'])
            color = random.choice(template['colors'])
            trait = random.choice(template['traits'])
            
            # Генерируем реалистичные контакты
            phone_endings = ['45-67', '78-90', '12-34', '56-78', '90-12']
            username_nums = random.randint(1, 99)
            
            posts.append({
                'id': f'mock_{group["type"]}_{1000 + i}',
                'title': template['title'].format(name),
                'description': template['description'].format(age, gender, color, trait),
                'date': self.generate_recent_date(),
                'url': f'{group["url"]}/{1000 + i}',
                'contact': f'@volunteer{username_nums} • +7 978 {random.choice(phone_endings)}',
                'photo_url': f'https://picsum.photos/400/300?random={i}&{group["type"]}',
                'has_photo': True,
                'type': group['type'],
                'source': 'mock'
            })
        
        return posts
    
    def generate_recent_date(self) -> str:
        """Генерирует недавнюю дату"""
        import random
        from datetime import timedelta
        
        days_ago = random.randint(0, 7)
        hours_ago = random.randint(0, 23)
        minutes_ago = random.randint(0, 59)
        
        recent_date = datetime.now() - timedelta(days=days_ago, hours=hours_ago, minutes=minutes_ago)
        return recent_date.strftime('%d.%m.%Y %H:%M')
    
    def get_enhanced_mock_posts(self, group_type: str = 'cats', limit: int = 3) -> List[Dict]:
        """Улучшенные моки для отображения"""
        posts = []
        
        for group in self.groups:
            if group_type != 'all' and group['type'] != group_type:
                continue
            
            group_posts = self.get_realistic_mock_posts(group, limit)
            posts.extend(group_posts)
        
        return posts[:limit]
    
    def get_cached_posts(self, group_type: str = 'all') -> List[Dict]:
        """Кэшированные посты с обновлением"""
        # Обновляем каждые 30 минут
        if (not self.last_update or 
            (datetime.now() - self.last_update).seconds > 1800):
            
            logger.info("🔄 Обновление постов...")
            try:
                fresh_posts = self.get_group_posts(group_type, 3)
                if fresh_posts:
                    return fresh_posts
            except Exception as e:
                logger.error(f"❌ Ошибка обновления: {e}")
        
        # Фильтруем кэш
        cached = [p for p in self.posts_cache 
                 if group_type == 'all' or p['type'] == group_type]
        
        return cached or self.get_enhanced_mock_posts(group_type, 3)

# Остальной код остается тем же, просто меняем класс парсера
class CatBotWithPhotos:
    """Бот с улучшенным парсером"""
    
    def __init__(self):
        self.token = os.environ.get('TOKEN')
        if not self.token:
            logger.error("❌ TOKEN не найден!")
            exit(1)
        
        self.bot = telebot.TeleBot(self.token)
        self.parser = AdvancedGroupParser()  # Используем улучшенный парсер
        self.app = Flask(__name__)
        self.port = int(os.environ.get('PORT', 8080))
        self.webhook_url = os.environ.get('WEBHOOK_URL')
        self.stats = {"users": set(), "messages": 0}
        
        self.setup_handlers()
        self.setup_routes()
    
    # Все остальные методы остаются без изменений...
    def send_post(self, chat_id: int, post: Dict):
        """Отправляет один пост с фото или текстом"""
        try:
            emoji = '🐱' if post['type'] == 'cats' else '🐶'
            source_tag = ' 📡' if post.get('source') == 'parsed' else ' 🎭'
            
            post_text = (
                f"{emoji} <b>{post['title']}</b>{source_tag}\n\n"
                f"{post['description']}\n\n"
                f"📅 {post['date']}\n"
                f"📞 {post['contact']}\n"
                f"🔗 <a href='{post['url']}'>Открыть в группе</a>"
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
                            types.InlineKeyboardButton("📢 Открыть в группе", url=post['url'])
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
                    types.InlineKeyboardButton("📢 Открыть в группе", url=post['url'])
                )
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки поста: {e}")

    def send_group_posts(self, chat_id: int, animal_type: str = 'cats'):
        """Отправляет все посты с фото"""
        try:
            posts = self.parser.get_cached_posts(animal_type)
            
            if not posts:
                self.bot.send_message(
                    chat_id,
                    "😿 Сейчас нет актуальных объявлений.\n"
                    f"📢 Проверьте группу: {self.parser.groups[0]['url'] if animal_type == 'cats' else self.parser.groups[1]['url']}"
                )
                return
            
            group_name = "Лапки-ручки Ялта" if animal_type == 'cats' else "Ялта Животные"
            group_url = self.parser.groups[0]['url'] if animal_type == 'cats' else self.parser.groups[1]['url']
            
            # Статистика по источникам
            parsed_count = sum(1 for p in posts if p.get('source') == 'parsed')
            mock_count = len(posts) - parsed_count
            
            status_text = ""
            if parsed_count > 0:
                status_text = f"\n✅ Актуальные данные: {parsed_count} из {len(posts)}"
            else:
                status_text = f"\n⚠️ Показаны примеры (парсинг временно недоступен)"
            
            self.bot.send_message(
                chat_id,
                f"{'🐱' if animal_type == 'cats' else '🐶'} <b>{'КОШКИ' if animal_type == 'cats' else 'СОБАКИ'} ИЩУТ ДОМ</b>\n\n"
                f"📢 Объявления из группы:\n"
                f"<a href='{group_url}'>{group_name}</a>{status_text}",
                parse_mode="HTML"
            )
            
            for post in posts:
                self.send_post(chat_id, post)
                time.sleep(0.5)
            
            self.bot.send_message(
                chat_id,
                "💡 <b>Как помочь?</b>\n\n"
                f"🏠 <b>Взять {'кошку' if animal_type == 'cats' else 'собаку'}:</b>\nСвяжитесь по контактам из объявления\n\n"
                f"📢 <b>Группа:</b> {group_url}\n\n"
                "🤝 <b>Стать волонтером:</b>\nНапишите в группу",
                parse_mode="HTML"
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки постов: {e}")
            self.bot.send_message(
                chat_id,
                f"⚠️ Ошибка загрузки объявлений\n\n"
                f"Попробуйте позже или посетите группу:\n"
                f"{self.parser.groups[0]['url'] if animal_type == 'cats' else self.parser.groups[1]['url']}"
            )

    # Остальные методы остаются без изменений
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
        """Обработчики сообщений"""
        
        @self.bot.message_handler(commands=['start'])
        def start_handler(message):
            self.stats["users"].add(message.from_user.id)
            self.stats["messages"] += 1
            
            welcome_text = """👋 <b>Добро пожаловать!</b>

🐾 Помощник по уличным животным Ялты

Выберите раздел:
🏥 <b>Стерилизация</b> - информация
🏠 <b>Пристройство</b> - животные ищут дом
📞 <b>Контакты</b> - связь с волонтерами
ℹ️ <b>О проекте</b> - наша деятельность"""
            
            self.bot.send_message(
                message.chat.id, 
                welcome_text, 
                parse_mode="HTML",
                reply_markup=self.get_main_keyboard()
            )
        
        @self.bot.message_handler(commands=['update'])
        def update_handler(message):
            """Обновление постов (для админов)"""
            self.parser.posts_cache = []
            self.parser.last_update = None
            self.bot.send_message(message.chat.id, "🔄 Обновляю посты...")
            posts = self.parser.get_group_posts()
            parsed_count = sum(1 for p in posts if p.get('source') == 'parsed')
            self.bot.send_message(
                message.chat.id, 
                f"✅ Обновлено: {len(posts)} постов\n"
                f"📡 Спарсено: {parsed_count}\n"
                f"🎭 Моков: {len(posts) - parsed_count}"
            )
        
        @self.bot.message_handler(commands=['debug'])
        def debug_handler(message):
            """Отладочная информация"""
            try:
                # Проверяем доступность групп
                debug_info = ["🔧 <b>Отладочная информация:</b>\n"]
                
                for group in self.parser.groups:
                    debug_info.append(f"📋 <b>{group['username']}:</b>")
                    
                    # Проверяем доступность
                    try:
                        import requests
                        response = requests.get(f"https://t.me/s/{group['username']}", 
                                              headers=self.parser.get_headers(), 
                                              timeout=10)
                        status = f"✅ HTTP {response.status_code}" if response.status_code == 200 else f"❌ HTTP {response.status_code}"
                        debug_info.append(f"   Статус: {status}")
                        
                        if response.status_code == 200:
                            from bs4 import BeautifulSoup
                            soup = BeautifulSoup(response.text, 'html.parser')
                            messages = soup.select('div.tgme_widget_message')
                            debug_info.append(f"   Сообщений найдено: {len(messages)}")
                        
                    except Exception as e:
                        debug_info.append(f"   Ошибка: {str(e)[:50]}")
                    
                    debug_info.append("")
                
                # Статистика кэша
                cached_posts = len(self.parser.posts_cache)
                last_update = self.parser.last_update.strftime('%H:%M:%S') if self.parser.last_update else "Никогда"
                
                debug_info.extend([
                    f"📊 <b>Кэш:</b>",
                    f"   Постов в кэше: {cached_posts}",
                    f"   Последнее обновление: {last_update}"
                ])
                
                self.bot.send_message(
                    message.chat.id,
                    "\n".join(debug_info),
                    parse_mode="HTML"
                )
                
            except Exception as e:
                self.bot.send_message(message.chat.id, f"❌ Ошибка отладки: {e}")
        
        @self.bot.message_handler(func=lambda m: m.text == "🏥 Стерилизация")
        def sterilization_handler(message):
            self.stats["users"].add(message.from_user.id)
            self.stats["messages"] += 1
            
            try:
                with open('assets/images/sterilization.jpg', 'rb') as photo:
                    self.bot.send_photo(
                        message.chat.id,
                        photo,
                        caption="🏥 <b>Стерилизация животных</b>\n\nВыберите вариант:",
                        parse_mode="HTML",
                        reply_markup=self.get_sterilization_keyboard()
                    )
            except Exception as e:
                logger.error(f"❌ Ошибка загрузки фото: {e}")
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
            
            info_text = """🏠 <b>Пристройство животных</b>

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
3️⃣ Или связаться с координаторами:
   • Кошки: +7 978 000-00-01
   • Собаки: +7 978 000-00-02

📋 <b>Нужная информация:</b>
🔹 Фото животного
🔹 Возраст, пол, окрас
🔹 Характер
🔹 Здоровье (прививки, стерилизация)
🔹 Ваши контакты"""
            
            self.bot.send_message(message.chat.id, info_text, parse_mode="HTML")
        
        @self.bot.message_handler(func=lambda m: m.text == "📞 Контакты")
        def contacts_handler(message):
            contacts_text = """📞 <b>КОНТАКТЫ</b>

👥 <b>Координаторы:</b>
🔹 Кошки: +7 978 144-90-70
🔹 Собаки: +7 978 000-00-02
🔹 Лечение: +7 978 000-00-03

🏥 <b>Клиники:</b>
🔹 "Айболит": +7 978 000-00-04
🔹 "ВетМир": +7 978 000-00-05

📱 <b>Социальные сети:</b>
🔹 Telegram: @yalta_animals
🔹 Instagram: @yalta_street_animals"""
            
            self.bot.send_message(message.chat.id, contacts_text, parse_mode="HTML")
        
        @self.bot.message_handler(func=lambda m: m.text == "ℹ️ О проекте")
        def about_handler(message):
            about_text = """ℹ️ <b>О ПРОЕКТЕ</b>

🎯 <b>Миссия:</b>
Помощь бездомным животным Ялты

📊 <b>Достижения:</b>
🔹 Стерилизовано: 500+ кошек, 200+ собак
🔹 Пристроено: 200+ котят, 100+ щенков
🔹 Волонтеров: 50+ активных

💰 <b>Поддержать:</b>
Карта: 2202 2020 0000 0000

🤝 <b>Стать волонтером:</b>
Пишите @animal_coordinator"""
            
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
            
            self.bot.send_message(
                message.chat.id,
                "❓ Используйте кнопки меню\n\n/start - главное меню",
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
                "status": "🤖 Animal Bot Running (Enhanced)",
                "time": datetime.now().strftime('%H:%M:%S'),
                "users": len(self.stats["users"]),
                "messages": self.stats["messages"],
                "groups": [g['url'] for g in self.parser.groups],
                "cache_posts": len(self.parser.posts_cache),
                "last_update": self.parser.last_update.isoformat() if self.parser.last_update else None
            })
        
        @self.app.route('/posts')
        def posts_api():
            try:
                posts = self.parser.get_cached_posts()
                parsed_count = sum(1 for p in posts if p.get('source') == 'parsed')
                
                return jsonify({
                    "status": "ok",
                    "count": len(posts),
                    "parsed": parsed_count,
                    "mocks": len(posts) - parsed_count,
                    "posts": posts,
                    "groups": [g['url'] for g in self.parser.groups],
                    "last_update": self.parser.last_update.isoformat() if self.parser.last_update else None
                })
            except Exception as e:
                return jsonify({"status": "error", "message": str(e)}), 500
        
        @self.app.route('/force_update')
        def force_update():
            """Принудительное обновление постов"""
            try:
                self.parser.posts_cache = []
                self.parser.last_update = None
                posts = self.parser.get_group_posts('all', 5)
                parsed_count = sum(1 for p in posts if p.get('source') == 'parsed')
                
                return jsonify({
                    "status": "updated",
                    "count": len(posts),
                    "parsed": parsed_count,
                    "mocks": len(posts) - parsed_count,
                    "time": datetime.now().isoformat()
                })
            except Exception as e:
                logger.error(f"❌ Ошибка принудительного обновления: {e}")
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
                logger.info(f"✅ Webhook: {full_url}")
                return True
            else:
                logger.error("❌ Не удалось установить webhook")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка webhook: {e}")
            return False
    
    def run(self):
        """Запуск улучшенного бота"""
        logger.info("🚀 Запуск Enhanced AnimalBot...")
        
        # Предзагрузка постов
        try:
            posts = self.parser.get_cached_posts()
            parsed_count = sum(1 for p in posts if p.get('source') == 'parsed')
            logger.info(f"✅ Предзагружено {len(posts)} постов (парсинг: {parsed_count}, моки: {len(posts) - parsed_count})")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка предзагрузки: {e}")
        
        if self.setup_webhook():
            self.app.run(host='0.0.0.0', port=self.port)
        else:
            logger.error("🚨 Ошибка webhook, запуск в polling режиме")
            try:
                self.bot.polling(none_stop=True, interval=0, timeout=20)
            except Exception as e:
                logger.error(f"❌ Ошибка polling: {e}")
                time.sleep(5)
                self.bot.polling()

if __name__ == "__main__":
    # Создаем необходимые папки и файлы
    os.makedirs('assets/images', exist_ok=True)
    
    # Создаем файлы с информацией о стерилизации
    if not os.path.exists('assets/free_text.html'):
        with open('assets/free_text.html', 'w', encoding='utf-8') as f:
            f.write("""<b>🆓 БЕСПЛАТНАЯ СТЕРИЛИЗАЦИЯ</b>

🏥 <b>Программы:</b>
🔹 Муниципальная программа Ялты
🔹 Благотворительные фонды
🔹 Волонтерские организации

📋 <b>Условия:</b>
✅ Бездомные животные
✅ Животные из малоимущих семей
✅ По направлению волонтеров
✅ Социально незащищенные граждане

📞 <b>Контакты для записи:</b>
🔹 Координатор программы: +7 978 144-90-70
🔹 Клиника "Айболит": +7 978 000-00-11
🔹 Группа волонтеров: @yalta_free_sterilization

📍 <b>Адреса клиник:</b>
🏥 ул. Кирова, 15 (пн-пт 9:00-18:00)
🏥 ул. Ленина, 32 (пн-сб 8:00-20:00)

📋 <b>Необходимые документы:</b>
📄 Справка о доходах (для льготников)
📄 Направление от волонтеров (для бездомных)

⏰ <b>Запись заранее!</b> Места ограничены.""")

    if not os.path.exists('assets/paid_text.html'):
        with open('assets/paid_text.html', 'w', encoding='utf-8') as f:
            f.write("""<b>💰 ПЛАТНАЯ СТЕРИЛИЗАЦИЯ</b>

🏥 <b>Ветеринарные клиники:</b>

🔹 <b>"Айболит"</b>
   💰 Кошки: от 3000₽ | Собаки: от 5000₽
   📞 +7 978 000-00-12
   📍 ул. Московская, 14

🔹 <b>"ВетМир"</b>
   💰 Кошки: от 2500₽ | Собаки: от 4500₽
   📞 +7 978 000-00-13
   📍 ул. Пушкина, 28

🔹 <b>"Зооветцентр"</b>
   💰 Кошки: от 3500₽ | Собаки: от 5500₽
   📞 +7 978 000-00-14
   📍 ул. Чехова, 45

🌟 <b>В стоимость включено:</b>
✔️ Полноценная операция
✔️ Качественный наркоз
✔️ Послеоперационный уход
✔️ Консультация врача
✔️ Повторный осмотр

💡 <b>Скидки и акции:</b>
🎯 Волонтерам и опекунам - 20%
🎯 При стерилизации нескольких животных - 15%
🎯 Пенсионерам - 10%
🎯 Акция "Стерилизуй в мае" - 25%

📅 <b>Запись на операцию:</b>
Звоните заранее! Рекомендуется запись за 1-2 недели.

🔬 <b>Дополнительно:</b>
Анализы крови, УЗИ, чипирование - по желанию""")

    # Запуск бота
    try:
        bot = CatBotWithPhotos()
        bot.run()
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"💥 Критическая ошибка: {e}")
        time.sleep(5)  # Пауза перед перезапуском
