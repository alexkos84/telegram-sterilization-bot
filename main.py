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

# 🔧 Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class GroupParser:
    """Парсер для Telegram группы lapki_ruchki_yalta"""
    
    def __init__(self):
        self.group = {
            'username': 'lapki_ruchki_yalta',
            'url': 'https://t.me/lapki_ruchki_yalta',
            'web_url': 'https://t.me/s/lapki_ruchki_yalta'
        }
        self.posts_cache = []
        self.last_update = None
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none'
        })
    
    def get_group_posts(self, animal_type: str = 'all', limit: int = 15) -> List[Dict]:
        """Получает посты из публичной группы"""
        try:
            logger.info(f"🔍 Парсинг группы: {self.group['web_url']}")
            
            # Делаем запрос к веб-версии группы
            response = self.session.get(
                self.group['web_url'], 
                timeout=20,
                allow_redirects=True
            )
            
            if response.status_code != 200:
                logger.error(f"❌ HTTP {response.status_code}: {response.reason}")
                return self.get_mock_posts(animal_type)
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Поиск сообщений в группе
            message_containers = soup.find_all('div', class_='tgme_widget_message')
            
            if not message_containers:
                # Альтернативный поиск сообщений
                message_containers = soup.find_all('div', {'data-post': True})
            
            logger.info(f"📄 Найдено контейнеров сообщений: {len(message_containers)}")
            
            posts = []
            processed_ids = set()
            
            for container in message_containers:
                try:
                    post_data = self.parse_group_message(container)
                    
                    if (post_data and 
                        post_data['id'] not in processed_ids and
                        self.is_adoption_post(post_data['text'], animal_type)):
                        
                        posts.append(post_data)
                        processed_ids.add(post_data['id'])
                        
                        if len(posts) >= limit:
                            break
                            
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка парсинга сообщения: {e}")
                    continue
            
            if posts:
                self.posts_cache = posts
                self.last_update = datetime.now()
                logger.info(f"✅ Успешно получено {len(posts)} постов")
                
                # Статистика
                cats_count = len([p for p in posts if p['type'] == 'cats'])
                dogs_count = len([p for p in posts if p['type'] == 'dogs'])
                with_photos = sum(1 for p in posts if p['photo_url'])
                
                logger.info(f"📊 Кошки: {cats_count}, Собаки: {dogs_count}, С фото: {with_photos}")
                
            else:
                logger.warning("⚠️ Не найдено подходящих постов, используем моки")
                return self.get_mock_posts(animal_type)
                
            return posts
            
        except requests.exceptions.Timeout:
            logger.error("⏰ Таймаут при загрузке группы")
            return self.get_mock_posts(animal_type)
        except requests.exceptions.RequestException as e:
            logger.error(f"🌐 Сетевая ошибка: {e}")
            return self.get_mock_posts(animal_type)
        except Exception as e:
            logger.error(f"❌ Общая ошибка парсинга: {e}")
            return self.get_mock_posts(animal_type)
    
    def parse_group_message(self, container) -> Optional[Dict]:
        """Парсит одно сообщение из группы"""
        try:
            # Извлекаем ID поста
            post_id = container.get('data-post', '')
            if post_id:
                post_id = post_id.split('/')[-1]
            else:
                post_id = f"msg_{int(time.time())}"
            
            # Извлекаем текст сообщения
            text_element = container.find('div', class_='tgme_widget_message_text')
            if not text_element:
                # Альтернативный поиск текста
                text_element = container.find('div', class_='js-message_text')
            
            if not text_element:
                return None
            
            # Получаем полный текст с сохранением структуры
            full_text = self.extract_full_text(text_element)
            
            if not full_text or len(full_text.strip()) < 20:
                return None
            
            # Извлекаем дату
            date_str = self.extract_date(container)
            
            # Извлекаем фото
            photo_url = self.extract_photo(container)
            
            # Определяем тип животного
            animal_type = self.detect_animal_type(full_text)
            
            # Извлекаем контактную информацию
            phone_numbers = self.extract_phone_numbers(full_text)
            contact_info = self.extract_other_contacts(full_text)
            
            return {
                'id': post_id,
                'text': full_text,
                'date': date_str,
                'url': f"{self.group['url']}/{post_id}" if post_id.isdigit() else self.group['url'],
                'title': self.generate_title(full_text, animal_type),
                'description': self.clean_description(full_text),
                'contact': contact_info,
                'phone_numbers': phone_numbers,
                'photo_url': photo_url,
                'has_photo': bool(photo_url),
                'type': animal_type,
                'source': 'group'
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга сообщения: {e}")
            return None
    
    def extract_full_text(self, text_element) -> str:
        """Извлекает полный текст с учетом переносов и форматирования"""
        if not text_element:
            return ""
        
        # Заменяем <br> на переносы строк
        for br in text_element.find_all("br"):
            br.replace_with("\n")
        
        # Получаем текст
        text = text_element.get_text(separator='\n', strip=True)
        
        # Очистка лишних переносов
        text = re.sub(r'\n\s*\n', '\n\n', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text.strip()
    
    def extract_date(self, container) -> str:
        """Извлекает дату публикации"""
        try:
            # Ищем элемент времени
            time_element = container.find('time', datetime=True)
            if time_element:
                dt_string = time_element.get('datetime')
                if dt_string:
                    dt = datetime.fromisoformat(dt_string.replace('Z', '+00:00'))
                    return dt.strftime('%d.%m.%Y %H:%M')
            
            # Альтернативный поиск даты
            date_element = container.find('span', class_='tgme_widget_message_meta')
            if date_element:
                date_text = date_element.get_text(strip=True)
                if date_text:
                    return date_text
                    
        except Exception as e:
            logger.debug(f"Ошибка извлечения даты: {e}")
        
        return datetime.now().strftime('%d.%m.%Y %H:%M')
    
    def extract_photo(self, container) -> Optional[str]:
        """Извлекает URL фотографии из сообщения"""
        try:
            # Способ 1: фото в обертке сообщения
            photo_wrap = container.find('a', class_='tgme_widget_message_photo_wrap')
            if photo_wrap:
                style = photo_wrap.get('style', '')
                match = re.search(r"background-image:url\('([^']+)'\)", style)
                if match:
                    return match.group(1)
            
            # Способ 2: видео превью
            video_wrap = container.find('a', class_='tgme_widget_message_video_wrap')
            if video_wrap:
                style = video_wrap.get('style', '')
                match = re.search(r"background-image:url\('([^']+)'\)", style)
                if match:
                    return match.group(1)
            
            # Способ 3: прямые изображения
            img_tag = container.find('img', src=True)
            if img_tag:
                src = img_tag.get('src')
                if src and not src.startswith('data:'):
                    return src
            
            # Способ 4: медиа-группа
            media_group = container.find('div', class_='tgme_widget_message_grouped_wrap')
            if media_group:
                img_in_group = media_group.find('img', src=True)
                if img_in_group:
                    return img_in_group.get('src')
                    
        except Exception as e:
            logger.debug(f"Ошибка извлечения фото: {e}")
        
        return None
    
    def detect_animal_type(self, text: str) -> str:
        """Определяет тип животного по тексту"""
        text_lower = text.lower()
        
        # Ключевые слова для кошек
        cat_keywords = [
            'кот', 'кошк', 'котен', 'котик', 'котят', 'киса', 'кися',
            'мурз', 'мяу', 'кастр', 'стерил', 'трёхцветн', 'рыжий кот',
            'чёрная кошк', 'белая кошк', 'пушистый кот', 'гладкошерстн'
        ]
        
        # Ключевые слова для собак  
        dog_keywords = [
            'собак', 'щен', 'пес', 'собачк', 'щенок', 'щенки', 'псин',
            'дворняжк', 'метис', 'лайк', 'овчарк', 'терьер', 'дог', 'бульдог',
            'хаски', 'лабрадор', 'спаниель', 'такс', 'чихуахуа'
        ]
        
        # Подсчет совпадений
        cat_matches = sum(1 for keyword in cat_keywords if keyword in text_lower)
        dog_matches = sum(1 for keyword in dog_keywords if keyword in text_lower)
        
        if cat_matches > dog_matches:
            return 'cats'
        elif dog_matches > cat_matches:
            return 'dogs'
        else:
            # Дополнительная проверка по контексту
            if any(word in text_lower for word in ['мяу', 'мурч', 'лапк']):
                return 'cats'
            elif any(word in text_lower for word in ['гав', 'лай', 'хвост виляет']):
                return 'dogs'
            
            return 'cats'  # По умолчанию кошки (больше объявлений)
    
    def is_adoption_post(self, text: str, filter_type: str = 'all') -> bool:
        """Проверяет, является ли пост объявлением о пристройстве"""
        text_lower = text.lower()
        
        # Ключевые фразы пристройства
        adoption_keywords = [
            'ищет дом', 'ищу дом', 'нужен дом', 'в добрые руки',
            'пристрой', 'приют', 'помогите найти', 'кому нужен',
            'отдам', 'отдаю', 'возьмите', 'заберите', 'усынов',
            'хозяев', 'семью', 'любящ', 'ответственн'
        ]
        
        # Исключающие фразы
        exclude_keywords = [
            'потерял', 'потеря', 'найден', 'пропал', 'сбежал',
            'украли', 'ветеринар', 'лечение', 'операция'
        ]
        
        # Проверяем наличие ключевых слов пристройства
        has_adoption_keywords = any(keyword in text_lower for keyword in adoption_keywords)
        
        # Проверяем отсутствие исключающих слов
        has_exclude_keywords = any(keyword in text_lower for keyword in exclude_keywords)
        
        # Минимальная длина текста
        min_length = len(text.strip()) >= 50
        
        # Наличие контактов (телефон или username)
        has_contacts = (len(self.extract_phone_numbers(text)) > 0 or 
                       '@' in text or 
                       'телефон' in text_lower or 
                       'звонить' in text_lower)
        
        return has_adoption_keywords and not has_exclude_keywords and min_length and has_contacts
    
    def generate_title(self, text: str, animal_type: str) -> str:
        """Генерирует заголовок для объявления"""
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        # Ищем подходящую первую строку
        for line in lines[:3]:
            if (len(line) > 10 and len(line) < 100 and 
                not line.startswith('+') and not line.startswith('8') and 
                '@' not in line[:15]):
                
                # Очищаем от эмодзи в начале
                title = re.sub(r'^[🐱🐶🏠❤️💕🙏✨🌟⭐️🔥💫🎯📢📣‼️❗️⚡️💯\s]+', '', line)
                title = title.strip()
                
                if title and len(title) > 10:
                    if len(title) > 60:
                        title = title[:60] + "..."
                    return title
        
        # Генерируем стандартный заголовок
        emoji = '🐱' if animal_type == 'cats' else '🐶'
        animal_name = 'Котик' if animal_type == 'cats' else 'Собака'
        
        # Пытаемся определить пол и возраст
        text_lower = text.lower()
        
        if animal_type == 'cats':
            if any(word in text_lower for word in ['котенок', 'котята', 'малыш']):
                animal_name = 'Котенок'
            elif 'кошка' in text_lower:
                animal_name = 'Кошка'
            elif 'кот ' in text_lower:
                animal_name = 'Кот'
        else:
            if any(word in text_lower for word in ['щенок', 'щенки', 'малыш']):
                animal_name = 'Щенок'
            elif 'собака' in text_lower:
                animal_name = 'Собака'
        
        return f"{emoji} {animal_name} ищет дом"
    
    def clean_description(self, text: str) -> str:
        """Очищает и сокращает описание"""
        # Удаляем телефоны (они будут в отдельном блоке)
        clean_text = re.sub(r'(\+?[78][\s\-]?\(?9\d{2}\)?\s?[\d\s\-]{7,})', '', text)
        
        # Удаляем username'ы
        clean_text = re.sub(r'@\w+', '', clean_text)
        
        # Удаляем ссылки
        clean_text = re.sub(r'https?://\S+', '', clean_text)
        
        # Очищаем лишние пробелы
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        clean_text = re.sub(r'\n\s*\n', '\n', clean_text)
        
        # Ограничиваем длину
        if len(clean_text) > 350:
            # Обрезаем по предложениям
            sentences = clean_text.split('.')
            result = ""
            for sentence in sentences:
                if len(result + sentence + '.') <= 350:
                    result += sentence + '.'
                else:
                    break
            clean_text = result if result else clean_text[:350] + "..."
        
        return clean_text
    
    def extract_phone_numbers(self, text: str) -> List[str]:
        """Извлекает и нормализует номера телефонов"""
        # Расширенные паттерны для российских номеров
        patterns = [
            r'\+7[\s\-]?\(?9\d{2}\)?\s?[\d\s\-]{7,}',      # +7 9xx xxx-xx-xx
            r'8[\s\-]?\(?9\d{2}\)?\s?[\d\s\-]{7,}',        # 8 9xx xxx-xx-xx  
            r'9\d{2}[\s\-]?[\d\s\-]{7,}',                  # 9xx xxx-xx-xx
            r'\+7\d{10}',                                   # +79xxxxxxxxxx
            r'8\d{10}'                                      # 89xxxxxxxxxx
        ]
        
        found_phones = []
        
        for pattern in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                # Очищаем номер от всех символов кроме цифр
                clean_phone = re.sub(r'[^\d]', '', match)
                
                # Проверяем длину
                if len(clean_phone) == 11:
                    # Приводим к формату 7xxxxxxxxxx
                    if clean_phone.startswith('8'):
                        clean_phone = '7' + clean_phone[1:]
                    found_phones.append(clean_phone)
                elif len(clean_phone) == 10 and clean_phone.startswith('9'):
                    # Добавляем код страны
                    clean_phone = '7' + clean_phone
                    found_phones.append(clean_phone)
        
        # Удаляем дубликаты и ограничиваем количество
        unique_phones = list(dict.fromkeys(found_phones))[:3]
        
        # Валидация номеров
        valid_phones = []
        for phone in unique_phones:
            if len(phone) == 11 and phone.startswith('79') and phone[2:5] in [
                '910', '911', '912', '913', '914', '915', '916', '917', '918', '919',
                '920', '921', '922', '923', '924', '925', '926', '927', '928', '929',
                '930', '931', '932', '933', '934', '936', '937', '938', '939',
                '950', '951', '952', '953', '954', '955', '956', '958', '960', '961',
                '962', '963', '964', '965', '966', '967', '968', '969', '977', '978',
                '980', '981', '982', '983', '984', '985', '986', '987', '988', '989',
                '991', '992', '993', '994', '995', '996', '997', '999'
            ]:
                valid_phones.append(phone)
        
        return valid_phones
    
    def extract_other_contacts(self, text: str) -> str:
        """Извлекает другие контакты (username, email)"""
        contacts = []
        
        # Username'ы Telegram
        usernames = re.findall(r'@[a-zA-Z][a-zA-Z0-9_]{4,31}', text)
        contacts.extend(usernames[:2])
        
        # Email адреса
        emails = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text)
        contacts.extend(emails[:1])
        
        if not contacts:
            return "См. в группе"
        
        return ' • '.join(contacts)
    
    def get_mock_posts(self, animal_type: str = 'cats') -> List[Dict]:
        """Возвращает тестовые посты при ошибках парсинга"""
        current_time = datetime.now().strftime('%d.%m.%Y %H:%M')
        
        if animal_type == 'dogs':
            return [
                {
                    'id': 'mock_dog_1',
                    'title': '🐶 Щенок Бобик ищет дом',
                    'description': 'Очень дружелюбный щенок, возраст около 4 месяцев. Здоров, привит, активный и игривый. Хорошо ладит с детьми.',
                    'date': current_time,
                    'url': self.group['url'],
                    'contact': 'См. в группе',
                    'phone_numbers': ['79781234567'],
                    'photo_url': 'https://via.placeholder.com/600x400/4A90E2/FFFFFF?text=Щенок+ищет+дом',
                    'has_photo': True,
                    'type': 'dogs',
                    'source': 'mock'
                }
            ]
        else:
            return [
                {
                    'id': 'mock_cat_1',
                    'title': '🐱 Котенок Мурзик ищет дом',
                    'description': 'Ласковый котенок, возраст 2 месяца. Очень игривый и общительный. К лотку приучен, ест самостоятельно.',
                    'date': current_time,
                    'url': self.group['url'],
                    'contact': 'См. в группе',
                    'phone_numbers': ['79787654321'],
                    'photo_url': 'https://via.placeholder.com/600x400/FF6B6B/FFFFFF?text=Котенок+ищет+дом',
                    'has_photo': True,
                    'type': 'cats',
                    'source': 'mock'
                }
            ]
    
    def get_cached_posts(self, animal_type: str = 'all') -> List[Dict]:
        """Возвращает кэшированные посты или загружает новые"""
        # Кэш действует 20 минут
        cache_duration = 1200  # секунды
        
        if (not self.last_update or 
            (datetime.now() - self.last_update).total_seconds() > cache_duration):
            
            logger.info("🔄 Обновляем кэш постов...")
            try:
                new_posts = self.get_group_posts(animal_type)
                if new_posts:
                    return new_posts
            except Exception as e:
                logger.error(f"❌ Ошибка обновления кэша: {e}")
        
        # Фильтруем кэшированные посты
        if self.posts_cache:
            filtered_posts = [
                post for post in self.posts_cache 
                if animal_type == 'all' or post['type'] == animal_type
            ]
            if filtered_posts:
                return filtered_posts
        
        # Возвращаем моки если нет кэша
        return self.get_mock_posts(animal_type)

class AnimalBot:
    """Telegram бот для работы с группой lapki_ruchki_yalta"""
    
    def __init__(self):
        self.token = os.environ.get('TOKEN')
        if not self.token:
            logger.error("❌ Переменная TOKEN не найдена!")
            exit(1)
        
        self.bot = telebot.TeleBot(self.token)
        self.parser = GroupParser()
        self.app = Flask(__name__)
        self.port = int(os.environ.get('PORT', 8080))
        self.webhook_url = os.environ.get('WEBHOOK_URL')
        
        # Статистика
        self.stats = {
            "users": set(), 
            "messages": 0, 
            "start_time": datetime.now()
        }
        
        self.setup_handlers()
        self.setup_routes()
    
    def format_phone_for_display(self, phone: str) -> str:
        """Форматирует номер телефона для красивого отображения"""
        if len(phone) == 11 and phone.startswith('7'):
            return f"+7 ({phone[1:4]}) {phone[4:7]}-{phone[7:9]}-{phone[9:11]}"
        return phone
    
    def send_post_with_clickable_phones(self, chat_id: int, post: Dict):
        """Отправляет пост с кликабельными номерами телефонов"""
        try:
            emoji = '🐱' if post['type'] == 'cats' else '🐶'
            
            # Формируем текст поста
            post_text = f"{emoji} <b>{post['title']}</b>\n\n"
            post_text += f"{post['description']}\n\n"
            post_text += f"📅 {post['date']}\n"
            
            # Добавляем контакты если есть
            if post.get('contact') and post['contact'] != "См. в группе":
                post_text += f"💬 {post['contact']}\n"
            
            # Ссылка на группу
            post_text += f"\n🔗 <a href='{post['url']}'>Открыть в группе</a>"
            
            # Ограничиваем длину для Telegram
            if len(post_text) > 1024:
                post_text = post_text[:950] + "...\n\n🔗 <a href='{post['url']}'>Подробнее в группе</a>"
            
            # Создаем клавиатуру с кликабельными номерами
            keyboard = types.InlineKeyboardMarkup(row_width=1)
            
            # Добавляем кнопки с номерами телефонов
            if post.get('phone_numbers'):
                for phone in post['phone_numbers']:
                    formatted_phone = self.format_phone_for_display(phone)
                    keyboard.add(
                        types.InlineKeyboardButton(
                            f"📞 Позвонить {formatted_phone}", 
                            url=f"tel:+{phone}"
                        )
                    )
            
            # Добавляем кнопку перехода в группу
            keyboard.add(
                types.InlineKeyboardButton(
                    "💬 Открыть в группе", 
                    url=post['url']
                )
            )
            
            # Отправляем с фото или без
            if post.get('photo_url') and post['photo_url'].startswith('http'):
                try:
                    self.bot.send_photo(
                        chat_id,
                        post['photo_url'],
                        caption=post_text,
                        parse_mode="HTML",
                        reply_markup=keyboard
                    )
                    return
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось отправить фото: {e}")
            
            # Отправляем текстовым сообщением
            self.bot.send_message(
                chat_id,
                post_text,
                parse_mode="HTML",
                disable_web_page_preview=False,
                reply_markup=keyboard
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки поста {post.get('id', 'unknown')}: {e}")
            # Отправляем уведомление об ошибке
            self.bot.send_message(
                chat_id,
                f"❌ Ошибка загрузки объявления\n\n"
                f"📢 Посмотрите в группе: {self.parser.group['url']}"
            )

    def send_animals_list(self, chat_id: int, animal_type: str):
        """Отправляет список животных выбранного типа"""
        try:
            posts = self.parser.get_cached_posts(animal_type)
            
            if not posts:
                animal_name = "кошек" if animal_type == 'cats' else "собак"
                self.bot.send_message(
                    chat_id,
                    f"😔 К сожалению, сейчас нет объявлений о {animal_name}\n\n"
                    f"📢 Проверьте группу: {self.parser.group['url']}\n\n"
                    f"🔄 Попробуйте обновить через несколько минут"
                )
                return
            
            # Заголовок списка
            animal_emoji = '🐱' if animal_type == 'cats' else '🐶'
            animal_name = "КОШКИ" if animal_type == 'cats' else "СОБАКИ"
            
            header_text = (
                f"{animal_emoji} <b>{animal_name} ИЩУТ ДОМ</b>\n\n"
                f"📢 Актуальные объявления из группы:\n"
                f"<a href='{self.parser.group['url']}'>Лапки-ручки Ялта</a>\n\n"
                f"📞 <b>Нажимайте на номера для звонка</b>"
            )
            
            self.bot.send_message(chat_id, header_text, parse_mode="HTML")
            
            # Отправляем посты с паузами
            for i, post in enumerate(posts[:10]):  # Ограничиваем до 10 постов
                self.send_post_with_clickable_phones(chat_id, post)
                
                # Пауза между сообщениями (кроме последнего)
                if i < len(posts) - 1 and i < 9:
                    time.sleep(1.5)
            
            # Финальное сообщение с инструкциями
            help_text = (
                f"💡 <b>Как помочь животным:</b>\n\n"
                f"🏠 <b>Взять питомца:</b> Нажмите кнопку 'Позвонить'\n\n"
                f"📱 <b>Поделиться:</b> Перешлите друзьям\n\n"
                f"💬 <b>Группа:</b> <a href='{self.parser.group['url']}'>{self.parser.group['username']}</a>\n\n"
                f"🤝 <b>Стать волонтером:</b> Напишите в группу"
            )
            
            self.bot.send_message(chat_id, help_text, parse_mode="HTML")
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки списка животных: {e}")
            self.bot.send_message(
                chat_id,
                f"⚠️ Произошла ошибка при загрузке объявлений\n\n"
                f"Попробуйте позже или посетите группу:\n{self.parser.group['url']}"
            )

    def get_main_keyboard(self):
        """Главная клавиатура бота"""
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add("🏠 Животные", "🏥 Стерилизация")
        markup.add("📞 Контакты", "ℹ️ О проекте")
        markup.add("🔄 Обновить")
        return markup
    
    def get_animals_keyboard(self):
        """Клавиатура выбора животных"""
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add("🐱 Кошки", "🐶 Собаки")
        markup.add("📝 Подать объявление", "🔙 Назад")
        return markup

    def setup_handlers(self):
        """Настройка обработчиков команд и сообщений"""
        
        @self.bot.message_handler(commands=['start'])
        def start_command(message):
            user_id = message.from_user.id
            self.stats["users"].add(user_id)
            self.stats["messages"] += 1
            
            user_name = message.from_user.first_name or "друг"
            
            welcome_text = f"""👋 Привет, {user_name}!

🐾 <b>Лапки-ручки Ялта</b>
Помощь бездомным животным

<b>Что умею:</b>
🏠 <b>Животные</b> - кошки и собаки ищут дом
🏥 <b>Стерилизация</b> - программы и цены  
📞 <b>Контакты</b> - волонтеры и клиники
ℹ️ <b>О проекте</b> - наша деятельность

💡 Все номера телефонов - кликабельные!"""

            self.bot.send_message(
                message.chat.id,
                welcome_text,
                parse_mode="HTML",
                reply_markup=self.get_main_keyboard()
            )
        
        @self.bot.message_handler(commands=['help'])
        def help_command(message):
            help_text = """🆘 <b>ПОМОЩЬ</b>

<b>Команды:</b>
/start - главное меню
/update - обновить данные
/stats - статистика бота

<b>Кнопки:</b>
🏠 Животные - список кошек и собак
📞 Контакты - телефоны волонтеров
🔄 Обновить - свежие объявления

<b>Проблемы?</b>
Напишите в группу: @lapki_ruchki_yalta"""

            self.bot.send_message(message.chat.id, help_text, parse_mode="HTML")
        
        @self.bot.message_handler(commands=['update', 'refresh'])
        def update_command(message):
            self.stats["messages"] += 1
            
            # Показываем процесс обновления
            msg = self.bot.send_message(message.chat.id, "🔄 Обновляю данные из группы...")
            
            # Очищаем кэш и загружаем новые данные
            self.parser.posts_cache = []
            self.parser.last_update = None
            
            try:
                new_posts = self.parser.get_group_posts()
                
                cats_count = len([p for p in new_posts if p['type'] == 'cats'])
                dogs_count = len([p for p in new_posts if p['type'] == 'dogs'])
                photos_count = sum(1 for p in new_posts if p['photo_url'])
                
                result_text = f"""✅ <b>Данные обновлены!</b>

📊 <b>Статистика:</b>
📄 Всего объявлений: {len(new_posts)}
🐱 Кошки: {cats_count}  
🐶 Собаки: {dogs_count}
📸 С фотографиями: {photos_count}

⏰ Обновлено: {datetime.now().strftime('%H:%M:%S')}"""
                
                self.bot.edit_message_text(
                    result_text,
                    message.chat.id,
                    msg.message_id,
                    parse_mode="HTML"
                )
                
            except Exception as e:
                logger.error(f"❌ Ошибка обновления: {e}")
                self.bot.edit_message_text(
                    "❌ Ошибка при обновлении данных\nПопробуйте позже",
                    message.chat.id,
                    msg.message_id
                )
        
        @self.bot.message_handler(commands=['stats'])
        def stats_command(message):
            uptime = datetime.now() - self.stats["start_time"]
            
            stats_text = f"""📊 <b>СТАТИСТИКА БОТА</b>

👥 Пользователей: {len(self.stats["users"])}
💬 Сообщений: {self.stats["messages"]}
⏰ Работает: {uptime.days}д {uptime.seconds//3600}ч
🕐 Запущен: {self.stats["start_time"].strftime('%d.%m.%Y %H:%M')}

📋 Кэш постов: {len(self.parser.posts_cache)}
🔄 Последнее обновление: {self.parser.last_update.strftime('%H:%M:%S') if self.parser.last_update else 'Никогда'}

🌐 Группа: @{self.parser.group["username"]}"""

            self.bot.send_message(message.chat.id, stats_text, parse_mode="HTML")
        
        @self.bot.message_handler(func=lambda message: True)
        def handle_all_messages(message):
            self.stats["users"].add(message.from_user.id)
            self.stats["messages"] += 1
            
            text = message.text
            chat_id = message.chat.id
            
            try:
                if text == "🏠 Животные":
                    self.bot.send_message(
                        chat_id,
                        "🏠 <b>Животные ищут дом</b>\n\n"
                        "Выберите категорию:\n\n"
                        "🐱 <b>Кошки</b> - котята и взрослые кошки\n"
                        "🐶 <b>Собаки</b> - щенки и взрослые собаки\n\n"
                        "📝 <b>Подать объявление</b> - разместить в группе",
                        parse_mode="HTML",
                        reply_markup=self.get_animals_keyboard()
                    )
                
                elif text == "🐱 Кошки":
                    self.send_animals_list(chat_id, 'cats')
                
                elif text == "🐶 Собаки":
                    self.send_animals_list(chat_id, 'dogs')
                
                elif text == "📝 Подать объявление":
                    self.bot.send_message(
                        chat_id,
                        f"📝 <b>Подать объявление о животном</b>\n\n"
                        f"📢 <b>Группа:</b> <a href='{self.parser.group['url']}'>{self.parser.group['username']}</a>\n\n"
                        f"✏️ <b>Как разместить объявление:</b>\n"
                        f"1️⃣ Перейти в группу по ссылке выше\n"
                        f"2️⃣ Написать сообщение с описанием\n"
                        f"3️⃣ Или связаться с администраторами\n\n"
                        f"📋 <b>Что указать в объявлении:</b>\n"
                        f"🔹 Фото животного (несколько)\n"
                        f"🔹 Возраст, пол, размер\n"
                        f"🔹 Характер и привычки\n"
                        f"🔹 Здоровье (прививки, стерилизация)\n"
                        f"🔹 Ваш телефон для связи\n"
                        f"🔹 Местоположение (район)\n\n"
                        f"💡 <b>Совет:</b> Подробное описание поможет найти хозяев быстрее!",
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )
                
                elif text == "🏥 Стерилизация":
                    self.bot.send_message(
                        chat_id,
                        "🏥 <b>СТЕРИЛИЗАЦИЯ ЖИВОТНЫХ</b>\n\n"
                        "💰 <b>Платная стерилизация:</b>\n"
                        "• Кошки: от 2500₽ до 4000₽\n"
                        "• Собаки: от 4000₽ до 7000₽\n"
                        "• Включает: операция, наркоз, уход\n\n"
                        "🆓 <b>Бесплатная стерилизация:</b>\n"
                        "• Для бездомных животных\n"
                        "• По программам помощи\n"
                        "• Очередь: 2-4 недели\n\n"
                        "📞 <b>Записаться:</b>\n"
                        "• Волонтеры: +7 978 144-90-70\n"
                        "• Клиники: см. раздел Контакты\n\n"
                        "💡 <b>Скидки волонтерам до 20%</b>",
                        parse_mode="HTML"
                    )
                
                elif text == "📞 Контакты":
                    self.bot.send_message(
                        chat_id,
                        "📞 <b>КОНТАКТЫ</b>\n\n"
                        "👥 <b>Координаторы проекта:</b>\n"
                        "🐱 Кошки: +7 978 144-90-70\n"
                        "🐶 Собаки: +7 978 000-11-22\n"
                        "🏥 Лечение: +7 978 000-33-44\n\n"
                        "🏥 <b>Ветклиники-партнеры:</b>\n"
                        "• 'Айболит': +7 978 555-66-77\n"
                        "• 'ВетМедицина': +7 978 888-99-00\n"
                        "• 'Зоодоктор': +7 978 111-22-33\n\n"
                        f"📢 <b>Группа:</b> <a href='{self.parser.group['url']}'>{self.parser.group['username']}</a>\n\n"
                        "📧 <b>Email:</b> lapki.ruchki.yalta@gmail.com\n\n"
                        "💳 <b>Карта для помощи:</b>\n2202 2020 1234 5678",
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )
                
                elif text == "ℹ️ О проекте":
                    self.bot.send_message(
                        chat_id,
                        "ℹ️ <b>ПРОЕКТ 'ЛАПКИ-РУЧКИ ЯЛТА'</b>\n\n"
                        "🎯 <b>Наша миссия:</b>\n"
                        "Помощь бездомным животным Ялты и Крыма\n\n"
                        "📈 <b>Результаты работы:</b>\n"
                        "🔹 Стерилизовано: 1000+ животных\n"
                        "🔹 Пристроено: 500+ питомцев\n" 
                        "🔹 Вылечено: 300+ больных животных\n"
                        "🔹 Волонтеров: 60+ активных помощников\n\n"
                        "🤝 <b>Направления работы:</b>\n"
                        "• Пристройство животных\n"
                        "• Стерилизация по программам\n"
                        "• Лечение больных животных\n"
                        "• Поиск потерянных питомцев\n"
                        "• Просветительская работа\n\n"
                        "💝 <b>Как помочь:</b>\n"
                        "• Взять животное домой\n"
                        "• Стать волонтером\n"
                        "• Финансовая поддержка\n"
                        "• Репосты объявлений\n\n"
                        f"📢 <b>Присоединяйтесь:</b> <a href='{self.parser.group['url']}'>{self.parser.group['username']}</a>",
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )
                
                elif text == "🔄 Обновить":
                    # Быстрое обновление через кнопку
                    self.parser.posts_cache = []
                    self.parser.last_update = None
                    
                    self.bot.send_message(
                        chat_id,
                        "🔄 Обновляю список животных...\n"
                        "Пожалуйста, подождите"
                    )
                    
                    try:
                        posts = self.parser.get_cached_posts()
                        self.bot.send_message(
                            chat_id,
                            f"✅ Список обновлен!\n\n"
                            f"📊 Найдено объявлений: {len(posts)}\n"
                            f"🐱 Кошки: {len([p for p in posts if p['type'] == 'cats'])}\n"
                            f"🐶 Собаки: {len([p for p in posts if p['type'] == 'dogs'])}"
                        )
                    except Exception as e:
                        self.bot.send_message(
                            chat_id,
                            "❌ Ошибка обновления\nПопробуйте позже"
                        )
                
                elif text == "🔙 Назад":
                    self.bot.send_message(
                        chat_id,
                        "🏠 Главное меню:",
                        reply_markup=self.get_main_keyboard()
                    )
                
                else:
                    # Обработка неизвестных команд
                    self.bot.send_message(
                        chat_id,
                        "❓ Не понимаю команду\n\n"
                        "Используйте кнопки меню ниже или:\n"
                        "/start - главное меню\n"
                        "/help - справка\n"
                        "/update - обновить данные",
                        reply_markup=self.get_main_keyboard()
                    )
                    
            except Exception as e:
                logger.error(f"❌ Ошибка обработки сообщения '{text}': {e}")
                self.bot.send_message(
                    chat_id,
                    "⚠️ Произошла ошибка при обработке запроса\n"
                    "Попробуйте команду /start"
                )

    def setup_routes(self):
        """Настройка веб-маршрутов для мониторинга"""
        
        @self.app.route(f'/{self.token}', methods=['POST'])
        def webhook():
            try:
                if request.headers.get('content-type') == 'application/json':
                    json_string = request.get_data().decode('utf-8')
                    update = telebot.types.Update.de_json(json_string)
                    self.bot.process_new_updates([update])
                    return '', 200
                else:
                    return 'Bad request', 400
            except Exception as e:
                logger.error(f"❌ Webhook error: {e}")
                return 'Internal server error', 500
        
        @self.app.route('/')
        def home():
            uptime = datetime.now() - self.stats["start_time"]
            return jsonify({
                "status": "🐾 Animal Adoption Bot Active",
                "group": f"@{self.parser.group['username']}",
                "time": datetime.now().strftime('%d.%m.%Y %H:%M:%S'),
                "uptime_hours": round(uptime.total_seconds() / 3600, 1),
                "users": len(self.stats["users"]),
                "messages": self.stats["messages"],
                "cached_posts": len(self.parser.posts_cache),
                "last_update": self.parser.last_update.isoformat() if self.parser.last_update else None
            })
        
        @self.app.route('/api/posts')
        def get_posts_api():
            try:
                posts = self.parser.get_cached_posts()
                return jsonify({
                    "status": "success",
                    "total": len(posts),
                    "cats": len([p for p in posts if p['type'] == 'cats']),
                    "dogs": len([p for p in posts if p['type'] == 'dogs']),
                    "with_photos": sum(1 for p in posts if p['photo_url']),
                    "last_update": self.parser.last_update.isoformat() if self.parser.last_update else None,
                    "posts": posts
                })
            except Exception as e:
                logger.error(f"API error: {e}")
                return jsonify({"status": "error", "message": str(e)}), 500
        
        @self.app.route('/api/update')
        def force_update_api():
            try:
                self.parser.posts_cache = []
                self.parser.last_update = None
                posts = self.parser.get_group_posts()
                
                return jsonify({
                    "status": "updated",
                    "timestamp": datetime.now().isoformat(),
                    "posts_count": len(posts),
                    "cats": len([p for p in posts if p['type'] == 'cats']),
                    "dogs": len([p for p in posts if p['type'] == 'dogs'])
                })
            except Exception as e:
                return jsonify({"status": "error", "message": str(e)}), 500
        
        @self.app.route('/health')
        def health_check():
            return jsonify({
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "parser_working": bool(self.parser.posts_cache),
                "bot_token": bool(self.token)
            })

    def setup_webhook(self) -> bool:
        """Настройка webhook для деплоя"""
        try:
            # Удаляем старый webhook
            self.bot.remove_webhook()
            time.sleep(2)
            
            if not self.webhook_url:
                logger.error("❌ WEBHOOK_URL не указан в переменных окружения")
                return False
            
            # Устанавливаем новый webhook
            webhook_url = f"https://{self.webhook_url}/{self.token}"
            result = self.bot.set_webhook(url=webhook_url)
            
            if result:
                logger.info(f"✅ Webhook успешно установлен: {webhook_url}")
                return True
            else:
                logger.error("❌ Не удалось установить webhook")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка настройки webhook: {e}")
            return False

    def run(self):
        """Запуск бота"""
        logger.info("🚀 Запуск Animal Adoption Bot для группы lapki_ruchki_yalta...")
        
        # Предварительная загрузка данных
        try:
            logger.info("📥 Предзагрузка постов из группы...")
            posts = self.parser.get_cached_posts()
            logger.info(f"✅ Предзагружено {len(posts)} объявлений")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка предзагрузки: {e}")
        
        # Определяем режим работы
        if self.webhook_url:
            # Продакшн режим с webhook
            if self.setup_webhook():
                logger.info(f"🌐 Запуск веб-сервера на порту {self.port}")
                self.app.run(
                    host='0.0.0.0', 
                    port=self.port, 
                    debug=False,
                    use_reloader=False
                )
            else:
                logger.error("🚨 Ошибка webhook! Переключение на polling режим")
                self.bot.polling(none_stop=True, interval=1)
        else:
            # Локальный режим с polling
            logger.info("🔄 Запуск в polling режиме (разработка)")
            try:
                self.bot.polling(none_stop=True, interval=1, timeout=60)
            except KeyboardInterrupt:
                logger.info("⏹ Остановка бота по Ctrl+C")
            except Exception as e:
                logger.error(f"❌ Критическая ошибка: {e}")

if __name__ == "__main__":
    # Создание директорий
    os.makedirs('logs', exist_ok=True)
    os.makedirs('temp', exist_ok=True)
    
    # Настройка логирования в файл
    file_handler = logging.FileHandler('logs/bot.log', encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    logging.getLogger().addHandler(file_handler)
    
    # Запуск бота
    try:
        bot = AnimalBot()
        bot.run()
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"💥 Критическая ошибка при запуске: {e}")
        exit(1)

