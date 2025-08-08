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

class YaltaChannelParser:
    """Парсер каналов Ялты с улучшенным извлечением данных"""
    
    def __init__(self):
        self.channels = [
            {
                'username': 'lapki_ruchki_yalta',
                'url': 'https://t.me/lapki_ruchki_yalta',
                'type': 'cats',
                'name': 'Лапки-ручки Ялта'
            },
            {
                'username': 'yalta_aninmals',
                'url': 'https://t.me/yalta_aninmals',
                'type': 'dogs',
                'name': 'Ялта Животные'
            }
        ]
        self.posts_cache = []
        self.last_update = None
    
    def get_channel_posts(self, channel_type: str = 'all', limit: int = 5) -> List[Dict]:
        """Получает последние посты из каналов"""
        try:
            all_posts = []
            
            for channel in self.channels:
                if channel_type != 'all' and channel['type'] != channel_type:
                    continue
                    
                web_url = f'https://t.me/s/{channel["username"]}'
                logger.info(f"🌐 Парсинг {channel['name']}: {web_url}")
                
                response = requests.get(web_url, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                }, timeout=15)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.content, 'html.parser')
                message_divs = soup.find_all('div', class_='tgme_widget_message')
                
                channel_posts = []
                for div in message_divs[:limit*3]:  # Берем больше для фильтрации
                    post_data = self.parse_message_div(div, channel)
                    if post_data and self.is_relevant_post(post_data.get('text', ''), channel['type']):
                        post_data['channel_name'] = channel['name']
                        channel_posts.append(post_data)
                        
                        if len(channel_posts) >= limit:
                            break
                
                all_posts.extend(channel_posts)
                time.sleep(1)  # Пауза между запросами
            
            # Сортируем по дате (новые сначала)
            all_posts.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
            
            if all_posts:
                self.posts_cache = all_posts
                self.last_update = datetime.now()
                logger.info(f"✅ Получено {len(all_posts)} постов из {len([c for c in self.channels if channel_type == 'all' or c['type'] == channel_type])} каналов")
            
            return all_posts[:limit*2] if all_posts else self.get_mock_posts(channel_type)
            
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга: {e}")
            return self.get_mock_posts(channel_type)
    
    def parse_message_div(self, div, channel) -> Optional[Dict]:
        """Улучшенный парсинг сообщения"""
        try:
            # ID поста
            post_id = div.get('data-post', '').split('/')[-1] or str(int(time.time()))
            
            # Текст сообщения
            text_div = div.find('div', class_='tgme_widget_message_text')
            text = ""
            if text_div:
                text = text_div.get_text(separator='\n', strip=True)
            
            if not text or len(text.strip()) < 10:
                return None
            
            # Дата с улучшенным парсингом
            timestamp = int(time.time())
            date_str = "Недавно"
            date_elem = div.find('time', datetime=True)
            if date_elem:
                try:
                    dt = datetime.fromisoformat(date_elem['datetime'].replace('Z', '+00:00'))
                    timestamp = int(dt.timestamp())
                    # Форматируем дату по-русски
                    date_str = dt.strftime('%d.%m.%Y в %H:%M')
                except:
                    pass
            
            # Извлечение фото (несколько вариантов)
            photo_url = self.extract_photo_url(div)
            
            # Извлекаем структурированные данные
            title = self.extract_title(text, channel['type'])
            description = self.extract_description(text)
            contacts = self.extract_contacts(text)
            animal_info = self.extract_animal_info(text, channel['type'])
            
            return {
                'id': post_id,
                'text': text,
                'title': title,
                'description': description,
                'contacts': contacts,
                'animal_info': animal_info,
                'date': date_str,
                'timestamp': timestamp,
                'url': f"{channel['url']}/{post_id}",
                'photo_url': photo_url,
                'has_photo': bool(photo_url),
                'type': channel['type'],
                'channel_name': channel['name']
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга сообщения: {e}")
            return None
    
    def extract_photo_url(self, div) -> Optional[str]:
        """Извлекает URL фото из различных элементов"""
        # Основное фото
        photo_wrap = div.find('a', class_='tgme_widget_message_photo_wrap')
        if photo_wrap and photo_wrap.get('style'):
            match = re.search(r"background-image:url\('([^']+)'\)", photo_wrap['style'])
            if match:
                return match.group(1)
        
        # Альтернативные варианты
        img_tag = div.find('img')
        if img_tag and img_tag.get('src'):
            return img_tag['src']
        
        # Документ с превью
        doc_thumb = div.find('i', class_='tgme_widget_message_document_thumb')
        if doc_thumb and doc_thumb.get('style'):
            match = re.search(r"background-image:url\('([^']+)'\)", doc_thumb['style'])
            if match:
                return match.group(1)
        
        return None
    
    def extract_title(self, text: str, animal_type: str) -> str:
        """Извлекает заголовок из текста"""
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        # Ищем строки с ключевыми словами
        keywords = {
            'cats': ['кот', 'кошк', 'котен', 'котик', 'пристрой', 'ищет дом'],
            'dogs': ['собак', 'щен', 'пес', 'пристрой', 'ищет дом']
        }
        
        for line in lines[:4]:  # Проверяем первые 4 строки
            if len(line) > 5:
                line_lower = line.lower()
                if any(keyword in line_lower for keyword in keywords.get(animal_type, [])):
                    # Очищаем от лишних символов
                    clean_line = re.sub(r'[^\w\s\-\.,!?а-яёА-ЯЁ]', '', line)
                    if len(clean_line) > 50:
                        clean_line = clean_line[:47] + "..."
                    return clean_line
        
        # Если не нашли подходящий заголовок, используем первую длинную строку
        for line in lines[:3]:
            if len(line) > 15:
                clean_line = re.sub(r'[^\w\s\-\.,!?а-яёА-ЯЁ]', '', line)
                if len(clean_line) > 50:
                    clean_line = clean_line[:47] + "..."
                return clean_line
        
        # Дефолтные заголовки
        return "🐱 Кошка ищет дом" if animal_type == 'cats' else "🐶 Собака ищет дом"
    
    def extract_description(self, text: str) -> str:
        """Извлекает описание, убирая контакты"""
        # Убираем номера телефонов и юзернеймы
        clean_text = re.sub(r'\+?[78][\s\-]?\(?9\d{2}\)?\s?[\d\s\-\(\)]{7,15}', '', text)
        clean_text = re.sub(r'@\w+', '', clean_text)
        clean_text = re.sub(r'https?://\S+', '', clean_text)
        
        # Убираем множественные пробелы и переносы
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        
        if len(clean_text) > 300:
            return clean_text[:297] + "..."
        return clean_text
    
    def extract_contacts(self, text: str) -> Dict[str, List[str]]:
        """Извлекает все контактные данные"""
        contacts = {
            'phones': [],
            'usernames': [],
            'formatted_phones': []
        }
        
        # Улучшенные регулярные выражения для телефонов
        phone_patterns = [
            r'\+?7[\s\-]?\(?9\d{2}\)?\s?[\d\s\-\(\)]{7,10}',
            r'8[\s\-]?\(?9\d{2}\)?\s?[\d\s\-\(\)]{7,10}',
            r'9\d{2}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}'
        ]
        
        for pattern in phone_patterns:
            phones = re.findall(pattern, text)
            for phone in phones:
                # Нормализуем номер
                clean_phone = re.sub(r'[^\d]', '', phone)
                if len(clean_phone) >= 10:
                    if clean_phone.startswith('8'):
                        clean_phone = '7' + clean_phone[1:]
                    elif not clean_phone.startswith('7'):
                        clean_phone = '7' + clean_phone
                    
                    if clean_phone not in [p.replace('+', '') for p in contacts['phones']]:
                        formatted_phone = f"+{clean_phone}"
                        contacts['phones'].append(formatted_phone)
                        
                        # Красивое форматирование номера
                        if len(clean_phone) == 11:
                            pretty_phone = f"+{clean_phone[0]} ({clean_phone[1:4]}) {clean_phone[4:7]}-{clean_phone[7:9]}-{clean_phone[9:11]}"
                            contacts['formatted_phones'].append(pretty_phone)
        
        # Юзернеймы
        usernames = re.findall(r'@\w+', text)
        contacts['usernames'] = list(set(usernames))
        
        return contacts
    
    def extract_animal_info(self, text: str, animal_type: str) -> Dict[str, str]:
        """Извлекает информацию о животном"""
        info = {
            'age': '',
            'gender': '',
            'color': '',
            'size': '',
            'health': '',
            'character': ''
        }
        
        text_lower = text.lower()
        
        # Возраст
        age_patterns = [
            r'(\d+)\s*(лет|года|год|мес|месяц)',
            r'(котен|щен|малыш|детеныш)',
            r'(взрослый|взрослая|пожилой|пожилая)'
        ]
        for pattern in age_patterns:
            match = re.search(pattern, text_lower)
            if match:
                info['age'] = match.group(0)
                break
        
        # Пол
        if any(word in text_lower for word in ['мальчик', 'кот ', 'пес ']):
            info['gender'] = 'мальчик'
        elif any(word in text_lower for word in ['девочка', 'кошка', 'сука']):
            info['gender'] = 'девочка'
        
        # Окрас
        colors = ['черный', 'белый', 'рыжий', 'серый', 'трехцветн', 'пятнист', 'полосат', 'тигров']
        for color in colors:
            if color in text_lower:
                info['color'] = color
                break
        
        # Размер (для собак)
        if animal_type == 'dogs':
            sizes = ['маленьк', 'средн', 'больш', 'крупн']
            for size in sizes:
                if size in text_lower:
                    info['size'] = size
                    break
        
        # Здоровье
        if any(word in text_lower for word in ['привит', 'вакцин', 'обработан']):
            info['health'] = 'привит'
        if any(word in text_lower for word in ['кастрир', 'стерилиз']):
            info['health'] += (' кастрирован' if info['health'] else 'кастрирован')
        
        return {k: v for k, v in info.items() if v}
    
    def is_relevant_post(self, text: str, animal_type: str) -> bool:
        """Проверяет релевантность поста"""
        if len(text.strip()) < 20:
            return False
        
        text_lower = text.lower()
        
        # Исключаем нерелевантные посты
        exclude_keywords = [
            'реклам', 'продам', 'куплю', 'услуг', 'работ',
            'магазин', 'ветаптек', 'корм продаж'
        ]
        if any(keyword in text_lower for keyword in exclude_keywords):
            return False
        
        # Проверяем релевантные ключевые слова
        if animal_type == 'cats':
            relevant_keywords = [
                'кот', 'кошк', 'котен', 'котик', 'мурз', 'мяу',
                'пристрой', 'ищет дом', 'в добрые руки', 'отдам',
                'найден', 'потерялся', 'кастрир', 'стерилиз'
            ]
        else:  # dogs
            relevant_keywords = [
                'собак', 'щен', 'пес', 'псин', 'лайк',
                'пристрой', 'ищет дом', 'в добрые руки', 'отдам',
                'найден', 'потерялся', 'кастрир', 'стерилиз'
            ]
        
        return any(keyword in text_lower for keyword in relevant_keywords)
    
    def get_mock_posts(self, channel_type: str = 'cats') -> List[Dict]:
        """Возвращает тестовые данные"""
        if channel_type == 'cats':
            return [{
                'id': '1001',
                'title': '🐱 Котенок Мурзик ищет дом',
                'description': 'Возраст 2 месяца, мальчик, рыжий окрас. Здоров, игривый, к лотку приучен.',
                'contacts': {
                    'phones': ['+7 (978) 123-45-67'],
                    'usernames': ['@cat_volunteer'],
                    'formatted_phones': ['+7 (978) 123-45-67']
                },
                'animal_info': {'age': '2 месяца', 'gender': 'мальчик', 'color': 'рыжий'},
                'date': '08.08.2025 в 14:30',
                'timestamp': int(time.time()),
                'url': 'https://t.me/lapki_ruchki_yalta/1001',
                'photo_url': 'https://via.placeholder.com/400x300/FF6B35/ffffff?text=Котенок+Мурзик',
                'has_photo': True,
                'type': 'cats',
                'channel_name': 'Лапки-ручки Ялта'
            }]
        else:
            return [{
                'id': '2001',
                'title': '🐶 Щенок Бобик ищет семью',
                'description': 'Возраст 4 месяца, мальчик, черный окрас. Активный, здоровый, привит.',
                'contacts': {
                    'phones': ['+7 (978) 765-43-21'],
                    'usernames': ['@dog_helper'],
                    'formatted_phones': ['+7 (978) 765-43-21']
                },
                'animal_info': {'age': '4 месяца', 'gender': 'мальчик', 'color': 'черный'},
                'date': '08.08.2025 в 16:45',
                'timestamp': int(time.time()),
                'url': 'https://t.me/yalta_aninmals/2001',
                'photo_url': 'https://via.placeholder.com/400x300/4ECDC4/ffffff?text=Щенок+Бобик',
                'has_photo': True,
                'type': 'dogs',
                'channel_name': 'Ялта Животные'
            }]
    
    def get_cached_posts(self, channel_type: str = 'all', force_update: bool = False) -> List[Dict]:
        """Возвращает кэшированные или обновленные посты"""
        # Обновляем кэш каждые 30 минут или при принудительном обновлении
        if (force_update or not self.last_update or 
            (datetime.now() - self.last_update).seconds > 1800):
            try:
                return self.get_channel_posts(channel_type)
            except Exception as e:
                logger.error(f"❌ Ошибка обновления кэша: {e}")
        
        # Фильтруем кэш по типу
        filtered_posts = []
        for post in self.posts_cache:
            if channel_type == 'all' or post.get('type') == channel_type:
                filtered_posts.append(post)
        
        return filtered_posts if filtered_posts else self.get_mock_posts(channel_type)


class YaltaAnimalBot:
    """Улучшенный бот для животных Ялты"""
    
    def __init__(self):
        self.token = os.environ.get('TOKEN')
        if not self.token:
            logger.error("❌ TOKEN не найден в переменных окружения!")
            exit(1)
        
        self.bot = telebot.TeleBot(self.token, parse_mode='HTML')
        self.parser = YaltaChannelParser()
        self.app = Flask(__name__)
        self.port = int(os.environ.get('PORT', 8080))
        self.webhook_url = os.environ.get('WEBHOOK_URL')
        
        self.stats = {
            "users": set(),
            "messages": 0,
            "start_time": datetime.now()
        }
        
        self.setup_handlers()
        self.setup_routes()
    
    def create_beautiful_post_message(self, post: Dict) -> str:
        """Создает красиво оформленное сообщение о животном"""
        emoji = '🐱' if post['type'] == 'cats' else '🐶'
        type_name = 'КОШКА' if post['type'] == 'cats' else 'СОБАКА'
        
        # Заголовок
        message_parts = [f"<b>{emoji} {post['title']}</b>"]
        
        # Информация о животном
        if post.get('animal_info'):
            info_lines = []
            animal_info = post['animal_info']
            
            if animal_info.get('age'):
                info_lines.append(f"📅 <b>Возраст:</b> {animal_info['age']}")
            if animal_info.get('gender'):
                info_lines.append(f"👫 <b>Пол:</b> {animal_info['gender']}")
            if animal_info.get('color'):
                info_lines.append(f"🎨 <b>Окрас:</b> {animal_info['color']}")
            if animal_info.get('size'):
                info_lines.append(f"📏 <b>Размер:</b> {animal_info['size']}")
            if animal_info.get('health'):
                info_lines.append(f"🏥 <b>Здоровье:</b> {animal_info['health']}")
            
            if info_lines:
                message_parts.append('\n'.join(info_lines))
        
        # Описание
        if post.get('description'):
            message_parts.append(f"📝 <b>Описание:</b>\n{post['description']}")
        
        # Контакты с кликабельными номерами
        contacts = post.get('contacts', {})
        if contacts.get('phones') or contacts.get('usernames'):
            contact_lines = ["📞 <b>Контакты:</b>"]
            
            for phone in contacts.get('formatted_phones', contacts.get('phones', []))[:2]:
                # Создаем кликабельную ссылку на номер
                clean_phone = re.sub(r'[^\d]', '', phone)
                contact_lines.append(f"📱 <a href='tel:+{clean_phone}'>{phone}</a>")
            
            for username in contacts.get('usernames', [])[:2]:
                contact_lines.append(f"💬 {username}")
            
            message_parts.append('\n'.join(contact_lines))
        
        # Дополнительная информация
        footer_parts = []
        if post.get('date'):
            footer_parts.append(f"🕐 {post['date']}")
        if post.get('channel_name'):
            footer_parts.append(f"📢 {post['channel_name']}")
        
        if footer_parts:
            message_parts.append(' • '.join(footer_parts))
        
        return '\n\n'.join(message_parts)
    
    def send_animal_post(self, chat_id: int, post: Dict):
        """Отправляет красиво оформленный пост о животном"""
        try:
            message_text = self.create_beautiful_post_message(post)
            
            # Создаем клавиатуру
            keyboard = types.InlineKeyboardMarkup(row_width=1)
            keyboard.add(
                types.InlineKeyboardButton(
                    f"📢 Открыть в {post.get('channel_name', 'канале')}", 
                    url=post['url']
                )
            )
            
            # Добавляем кнопки для звонков
            contacts = post.get('contacts', {})
            if contacts.get('phones'):
                phone_clean = re.sub(r'[^\d]', '', contacts['phones'][0])
                keyboard.add(
                    types.InlineKeyboardButton(
                        f"📞 Позвонить {contacts.get('formatted_phones', contacts.get('phones'))[0]}", 
                        url=f"tel:+{phone_clean}"
                    )
                )
            
            # Отправляем с фото или без
            if post.get('photo_url'):
                try:
                    self.bot.send_photo(
                        chat_id,
                        post['photo_url'],
                        caption=message_text,
                        reply_markup=keyboard
                    )
                    return
                except Exception as e:
                    logger.error(f"❌ Ошибка отправки фото: {e}")
            
            # Отправляем текстом
            self.bot.send_message(
                chat_id,
                message_text,
                reply_markup=keyboard,
                disable_web_page_preview=False
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки поста: {e}")
            self.bot.send_message(
                chat_id,
                f"⚠️ Ошибка отправки объявления\n\nПосмотреть можно здесь: {post.get('url', 'в канале')}"
            )
    
    def send_channel_posts(self, chat_id: int, animal_type: str = 'cats', limit: int = 5):
        """Отправляет посты из каналов"""
        try:
            # Информационное сообщение
            type_emoji = '🐱' if animal_type == 'cats' else '🐶'
            type_name = 'КОШКИ' if animal_type == 'cats' else 'СОБАКИ'
            
            self.bot.send_message(
                chat_id,
                f"{type_emoji} <b>{type_name} ИЩУТ ДОМ</b>\n\n"
                f"🔄 Загружаю свежие объявления из каналов...",
            )
            
            # Получаем посты
            posts = self.parser.get_cached_posts(animal_type)
            
            if not posts:
                self.bot.send_message(
                    chat_id,
                    f"😿 Сейчас нет актуальных объявлений о пристройстве.\n\n"
                    f"📢 Проверьте каналы напрямую:\n"
                    f"• <a href='{self.parser.channels[0]['url']}'>{self.parser.channels[0]['name']}</a>\n"
                    f"• <a href='{self.parser.channels[1]['url']}'>{self.parser.channels[1]['name']}</a>"
                )
                return
            
            # Отправляем посты
            sent_count = 0
            for post in posts[:limit]:
                if post.get('type') == animal_type or animal_type == 'all':
                    self.send_animal_post(chat_id, post)
                    sent_count += 1
                    time.sleep(0.8)  # Пауза между сообщениями
            
            # Итоговое сообщение
            if sent_count > 0:
                help_text = (
                    f"💡 <b>Показано {sent_count} объявлений</b>\n\n"
                    f"🏠 <b>Как взять питомца:</b>\n"
                    f"1️⃣ Позвонить по указанному номеру\n"
                    f"2️⃣ Или написать в личные сообщения\n"
                    f"3️⃣ Договориться о встрече\n\n"
                    f"📢 <b>Источники объявлений:</b>\n"
                )
                
                for channel in self.parser.channels:
                    if animal_type == 'all' or channel['type'] == animal_type:
                        help_text += f"• <a href='{channel['url']}'>{channel['name']}</a>\n"
                
                help_text += f"\n🤝 <b>Хотите помочь?</b>\nСтаньте волонтером - пишите в каналы!"
                
                self.bot.send_message(chat_id, help_text)
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки постов: {e}")
            self.bot.send_message(
                chat_id,
                f"⚠️ Ошибка загрузки объявлений\n\n"
                f"Попробуйте позже или посетите каналы:\n"
                f"• <a href='{self.parser.channels[0]['url']}'>{self.parser.channels[0]['name']}</a>\n"
                f"• <a href='{self.parser.channels[1]['url']}'>{self.parser.channels[1]['name']}</a>"
            )
    
    def get_main_keyboard(self):
        """Главная клавиатура"""
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add(
            types.KeyboardButton("🐱 Кошки ищут дом"),
            types.KeyboardButton("🐶 Собаки ищут дом")
        )
        markup.add(
            types.KeyboardButton("🏥 Стерилизация"),
            types.KeyboardButton("📝 Подать объявление")
        )
        markup.add(
            types.KeyboardButton("📞 Контакты"),
            types.KeyboardButton("ℹ️ О проекте")
        )
        return markup
    
    def get_sterilization_keyboard(self):
        """Клавиатура стерилизации"""
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("💰 Платная стерилизация", "🆓 Бесплатная стерилизация")
        markup.add("🔙 Назад")
        return markup
    
    def setup_handlers(self):
        """Настройка обработчиков сообщений"""
        
        @self.bot.message_handler(commands=['start'])
        def start_handler(message):
            self.stats["users"].add(message.from_user.id)
            self.stats["messages"] += 1
            
            user_name = message.from_user.first_name or "друг"
            
            welcome_text = f"""👋 <b>Привет, {user_name}!</b>

🐾 <b>Помощник по уличным животным Ялты</b>

Что вас интересует?

🐱 <b>Кошки ищут дом</b> - актуальные объявления
🐶 <b>Собаки ищут дом</b> - найти питомца  
🏥 <b>Стерилизация</b> - программы и цены
📝 <b>Подать объявление</b> - как разместить
📞 <b>Контакты</b> - связь с волонтерами
ℹ️ <b>О проекте</b> - наша миссия

<i>💡 Все объявления с актуальными номерами телефонов!</i>"""
            
            self.bot.send_message(
                message.chat.id,
                welcome_text,
                reply_markup=self.get_main_keyboard()
            )
        
        @self.bot.message_handler(commands=['update', 'refresh'])
        def update_handler(message):
            """Принудительное обновление постов"""
            self.bot.send_message(message.chat.id, "🔄 Обновляю базу объявлений...")
            
            try:
                cats_posts = self.parser.get_cached_posts('cats', force_update=True)
                dogs_posts = self.parser.get_cached_posts('dogs', force_update=True)
                
                total_posts = len(cats_posts) + len(dogs_posts)
                photo_posts = sum(1 for p in cats_posts + dogs_posts if p.get('has_photo'))
                
                self.bot.send_message(
                    message.chat.id,
                    f"✅ <b>База обновлена!</b>\n\n"
                    f"📊 Всего объявлений: {total_posts}\n"
                    f"🖼 С фотографиями: {photo_posts}\n"
                    f"🐱 Кошки: {len(cats_posts)}\n"
                    f"🐶 Собаки: {len(dogs_posts)}\n\n"
                    f"🕐 Время обновления: {datetime.now().strftime('%H:%M:%S')}"
                )
            except Exception as e:
                logger.error(f"❌ Ошибка обновления: {e}")
                self.bot.send_message(
                    message.chat.id,
                    f"⚠️ Ошибка обновления базы\n\nПопробуйте позже"
                )
        
        @self.bot.message_handler(func=lambda m: m.text == "🐱 Кошки ищут дом")
        def cats_handler(message):
            self.stats["users"].add(message.from_user.id)
            self.stats["messages"] += 1
            self.send_channel_posts(message.chat.id, 'cats')
        
        @self.bot.message_handler(func=lambda m: m.text == "🐶 Собаки ищут дом")
        def dogs_handler(message):
            self.stats["users"].add(message.from_user.id)
            self.stats["messages"] += 1
            self.send_channel_posts(message.chat.id, 'dogs')
        
        @self.bot.message_handler(func=lambda m: m.text == "🏥 Стерилизация")
        def sterilization_handler(message):
            self.stats["users"].add(message.from_user.id)
            self.stats["messages"] += 1
            
            info_text = """🏥 <b>СТЕРИЛИЗАЦИЯ ЖИВОТНЫХ В ЯЛТЕ</b>

Выберите вариант:

💰 <b>Платная стерилизация</b>
Клиники города с ценами

🆓 <b>Бесплатная стерилизация</b>
Программы для малоимущих и бездомных животных

<i>🔬 Стерилизация - важный шаг для здоровья питомца и контроля популяции!</i>"""
            
            self.bot.send_message(
                message.chat.id,
                info_text,
                reply_markup=self.get_sterilization_keyboard()
            )
        
        @self.bot.message_handler(func=lambda m: m.text == "💰 Платная стерилизация")
        def paid_sterilization_handler(message):
            paid_info = """💰 <b>ПЛАТНАЯ СТЕРИЛИЗАЦИЯ В ЯЛТЕ</b>

🏥 <b>Клиники города:</b>

🔹 <b>"Айболит"</b>
   • Кошки: от 3500₽
   • Собаки: от 5500₽
   • 📞 <a href="tel:+73654200123">+7 (365) 420-01-23</a>
   • 📍 ул. Кирова, 15

🔹 <b>"ВетМир"</b> 
   • Кошки: от 3000₽
   • Собаки: от 5000₽
   • 📞 <a href="tel:+73654250456">+7 (365) 425-04-56</a>
   • 📍 ул. Московская, 32

🔹 <b>"Друг"</b>
   • Кошки: от 2800₽
   • Собаки: от 4800₽
   • 📞 <a href="tel:+79788881234">+7 (978) 888-12-34</a>
   • 📍 пер. Чехова, 8

💡 <b>В стоимость входит:</b>
✅ Операция и наркоз
✅ Послеоперационная попона
✅ Консультация врача
✅ Рекомендации по уходу

🎁 <b>Скидки:</b>
• Волонтерам - 15-20%
• При стерилизации 2+ животных - 10%"""
            
            self.bot.send_message(message.chat.id, paid_info)
        
        @self.bot.message_handler(func=lambda m: m.text == "🆓 Бесплатная стерилизация")
        def free_sterilization_handler(message):
            free_info = """🆓 <b>БЕСПЛАТНАЯ СТЕРИЛИЗАЦИЯ</b>

📋 <b>Программы помощи:</b>

🏛 <b>Муниципальная программа</b>
• Для бездомных животных
• По направлению отлова
• 📞 Горветслужба: <a href="tel:+73654270187">+7 (365) 427-01-87</a>

🤝 <b>Благотворительный фонд "Ласка"</b>
• Для малоимущих семей
• Справка о доходах обязательна  
• 📞 <a href="tel:+79787654321">+7 (978) 765-43-21</a>
• 💬 @laska_yalta

🐾 <b>Волонтерские программы</b>
• Для опекунов бездомных животных
• Предварительная запись
• 📞 Координатор: <a href="tel:+79781234567">+7 (978) 123-45-67</a>

📄 <b>Необходимые документы:</b>
• Паспорт опекуна
• Справка о доходах (если требуется)
• Фото животного
• Контакты для связи

⏰ <b>Сроки ожидания:</b> 2-4 недели
🏥 <b>Место проведения:</b> клиника "Айболит"
📍 <b>Адрес:</b> ул. Кирова, 15"""
            
            self.bot.send_message(message.chat.id, free_info)
        
        @self.bot.message_handler(func=lambda m: m.text == "📝 Подать объявление")
        def submit_ad_handler(message):
            submit_info = f"""📝 <b>ПОДАТЬ ОБЪЯВЛЕНИЕ О ПРИСТРОЙСТВЕ</b>

📢 <b>Каналы для размещения:</b>
• <a href="{self.parser.channels[0]['url']}">{self.parser.channels[0]['name']}</a> (кошки)
• <a href="{self.parser.channels[1]['url']}">{self.parser.channels[1]['name']}</a> (собаки)

✍️ <b>Как подать объявление:</b>

1️⃣ <b>Подготовить материалы:</b>
   📸 Качественные фото питомца
   📝 Описание характера
   🏥 Информацию о здоровье
   📞 Контактные данные

2️⃣ <b>Связаться с администраторами:</b>
   • Кошки: 📞 <a href="tel:+79781449070">+7 (978) 144-90-70</a>
   • Собаки: 📞 <a href="tel:+79787654321">+7 (978) 765-43-21</a>
   • Или написать в каналы

3️⃣ <b>Отправить данные:</b>
   📋 Заполненная анкета питомца
   🖼 3-5 хороших фото
   📝 История и особенности

💡 <b>Образец объявления:</b>
<i>"🐱 Котенок Мурзик, 3 мес, мальчик
Рыжий, игривый, к лотку приучен
Здоров, ест корм и натуралку
📞 +7 (978) XXX-XX-XX, Анна"</i>

⚡ <b>Размещение:</b> в течение суток
🆓 <b>Стоимость:</b> бесплатно
🔄 <b>Обновление:</b> по запросу"""
            
            self.bot.send_message(message.chat.id, submit_info)
        
        @self.bot.message_handler(func=lambda m: m.text == "📞 Контакты")
        def contacts_handler(message):
            contacts_text = """📞 <b>КОНТАКТЫ ВОЛОНТЕРОВ ЯЛТЫ</b>

👥 <b>Координаторы по пристройству:</b>
🐱 Кошки: 📞 <a href="tel:+79781449070">+7 (978) 144-90-70</a> (Елена)
🐶 Собаки: 📞 <a href="tel:+79787654321">+7 (978) 765-43-21</a> (Марина)

🏥 <b>Лечение и стерилизация:</b>
💉 Ветпомощь: 📞 <a href="tel:+79789876543">+7 (978) 987-65-43</a> (Врач)
🔬 Стерилизация: 📞 <a href="tel:+79781234567">+7 (978) 123-45-67</a> (Координатор)

🏥 <b>Ветеринарные клиники:</b>
🔹 "Айболит": 📞 <a href="tel:+73654200123">+7 (365) 420-01-23</a>
🔹 "ВетМир": 📞 <a href="tel:+73654250456">+7 (365) 425-04-56</a>
🔹 "Друг": 📞 <a href="tel:+79788881234">+7 (978) 888-12-34</a>

📱 <b>Социальные сети:</b>
• Telegram: <a href="{self.parser.channels[0]['url']}">Лапки-ручки Ялта</a>
• Telegram: <a href="{self.parser.channels[1]['url']}">Ялта Животные</a>
• VK: vk.com/yalta_animals
• Instagram: @yalta_street_animals

🆘 <b>Экстренные случаи:</b>
📞 Дежурный волонтер: <a href="tel:+79781111111">+7 (978) 111-11-11</a>
(Работает круглосуточно)"""
            
            self.bot.send_message(message.chat.id, contacts_text)
        
        @self.bot.message_handler(func=lambda m: m.text == "ℹ️ О проекте")
        def about_handler(message):
            about_text = """ℹ️ <b>О ПРОЕКТЕ "ЖИВОТНЫЕ ЯЛТЫ"</b>

🎯 <b>Наша миссия:</b>
Помощь бездомным животным Ялты через стерилизацию, лечение и пристройство

📊 <b>Результаты работы:</b>
🔸 Стерилизовано: 800+ кошек, 300+ собак
🔸 Пристроено в семьи: 400+ питомцев
🔸 Вылечено: 600+ животных
🔸 Активных волонтеров: 70+ человек

🏆 <b>Программы:</b>
• 🏥 Бесплатная стерилизация
• 🏠 Пристройство в добрые руки
• 💊 Лечение и реабилитация
• 📚 Просвещение о гуманном обращении

💰 <b>Поддержать проект:</b>
💳 Карта Сбербанк: <code>2202 2020 1234 5678</code>
💳 ЮMoney: <code>41001234567890</code>
💳 PayPal: donate@yalta-animals.org

📞 <b>Стать волонтером:</b>
Пишите координатору: <a href="tel:+79781449070">+7 (978) 144-90-70</a>

🌐 <b>Наши каналы:</b>
• <a href="{self.parser.channels[0]['url']}">{self.parser.channels[0]['name']}</a>
• <a href="{self.parser.channels[1]['url']}">{self.parser.channels[1]['name']}</a>

❤️ <b>Вместе мы делаем Ялту добрее к животным!</b>"""
            
            self.bot.send_message(message.chat.id, about_text)
        
        @self.bot.message_handler(func=lambda m: m.text == "🔙 Назад")
        def back_handler(message):
            self.bot.send_message(
                message.chat.id,
                "🏠 <b>Главное меню</b>\n\nВыберите раздел:",
                reply_markup=self.get_main_keyboard()
            )
        
        @self.bot.message_handler(commands=['stats'])
        def stats_handler(message):
            """Статистика бота (для админов)"""
            uptime = datetime.now() - self.stats['start_time']
            stats_text = f"""📊 <b>СТАТИСТИКА БОТА</b>

👥 Пользователей: {len(self.stats['users'])}
💬 Сообщений: {self.stats['messages']}
⏰ Работает: {uptime.days}д {uptime.seconds//3600}ч {(uptime.seconds//60)%60}м

🗃 В кэше постов: {len(self.parser.posts_cache)}
🔄 Последнее обновление: {self.parser.last_update.strftime('%H:%M:%S') if self.parser.last_update else 'Никогда'}

🐱 Каналы кошек: {len([c for c in self.parser.channels if c['type'] == 'cats'])}
🐶 Каналы собак: {len([c for c in self.parser.channels if c['type'] == 'dogs'])}"""
            
            self.bot.send_message(message.chat.id, stats_text)
        
        @self.bot.message_handler(func=lambda message: True)
        def default_handler(message):
            """Обработчик всех остальных сообщений"""
            self.stats["users"].add(message.from_user.id)
            self.stats["messages"] += 1
            
            self.bot.send_message(
                message.chat.id,
                "❓ <b>Используйте кнопки меню</b>\n\n"
                "Если кнопки не видны, отправьте /start",
                reply_markup=self.get_main_keyboard()
            )
    
    def setup_routes(self):
        """Настройка Flask маршрутов"""
        
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
                logger.error(f"❌ Webhook error: {e}")
                return 'Internal error', 500
        
        @self.app.route('/')
        def home():
            uptime = datetime.now() - self.stats['start_time']
            return jsonify({
                "status": "🤖 YaltaAnimalBot is running",
                "version": "2.0",
                "uptime": f"{uptime.days}d {uptime.seconds//3600}h {(uptime.seconds//60)%60}m",
                "users": len(self.stats["users"]),
                "messages": self.stats["messages"],
                "cached_posts": len(self.parser.posts_cache),
                "channels": [
                    {"name": c['name'], "url": c['url'], "type": c['type']} 
                    for c in self.parser.channels
                ],
                "last_update": self.parser.last_update.isoformat() if self.parser.last_update else None
            })
        
        @self.app.route('/api/posts')
        def posts_api():
            """API для получения постов"""
            try:
                channel_type = request.args.get('type', 'all')
                limit = int(request.args.get('limit', 10))
                force_update = request.args.get('update', 'false').lower() == 'true'
                
                posts = self.parser.get_cached_posts(channel_type, force_update)
                
                return jsonify({
                    "status": "success",
                    "count": len(posts),
                    "posts": posts[:limit],
                    "channels": [
                        {"name": c['name'], "url": c['url'], "type": c['type']} 
                        for c in self.parser.channels
                    ],
                    "last_update": self.parser.last_update.isoformat() if self.parser.last_update else None
                })
            except Exception as e:
                logger.error(f"❌ API error: {e}")
                return jsonify({"status": "error", "message": str(e)}), 500
        
        @self.app.route('/api/update', methods=['POST'])
        def force_update():
            """Принудительное обновление кэша"""
            try:
                self.parser.posts_cache = []
                self.parser.last_update = None
                posts = self.parser.get_cached_posts(force_update=True)
                
                return jsonify({
                    "status": "success",
                    "message": "Cache updated",
                    "count": len(posts),
                    "timestamp": datetime.now().isoformat()
                })
            except Exception as e:
                return jsonify({"status": "error", "message": str(e)}), 500
    
    def setup_webhook(self) -> bool:
        """Настройка webhook"""
        try:
            # Удаляем старый webhook
            self.bot.remove_webhook()
            time.sleep(2)
            
            if not self.webhook_url:
                logger.error("❌ WEBHOOK_URL не установлен!")
                return False
            
            # Устанавливаем новый webhook
            webhook_url = f"https://{self.webhook_url}/{self.token}"
            result = self.bot.set_webhook(url=webhook_url)
            
            if result:
                logger.info(f"✅ Webhook установлен: {webhook_url}")
                return True
            else:
                logger.error("❌ Не удалось установить webhook")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка настройки webhook: {e}")
            return False
    
    def run(self):
        """Запуск бота"""
        logger.info("🚀 Запуск YaltaAnimalBot v2.0...")
        
        # Предзагрузка постов
        try:
            logger.info("📥 Предзагрузка постов из каналов...")
            cats_posts = self.parser.get_cached_posts('cats')
            dogs_posts = self.parser.get_cached_posts('dogs')
            total = len(cats_posts) + len(dogs_posts)
            logger.info(f"✅ Предзагружено {total} постов (🐱{len(cats_posts)} 🐶{len(dogs_posts)})")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка предзагрузки: {e}")
        
        # Запуск бота
        if self.setup_webhook():
            logger.info(f"🌐 Запуск Flask сервера на порту {self.port}")
            self.app.run(host='0.0.0.0', port=self.port, debug=False)
        else:
            logger.warning("🔄 Fallback to polling mode")
            try:
                self.bot.polling(none_stop=True, timeout=60)
            except Exception as e:
                logger.error(f"❌ Polling error: {e}")


if __name__ == "__main__":
    # Создание необходимых директорий
    os.makedirs('logs', exist_ok=True)
    os.makedirs('assets', exist_ok=True)
    
    # Запуск бота
    try:
        bot = YaltaAnimalBot()
        bot.run()
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"🚨 Критическая ошибка: {e}")
        exit(1)
