import os
import telebot
from telebot import types
from datetime import datetime
import time
import logging
import re
import requests
from bs4 import BeautifulSoup

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Инициализация бота
bot = telebot.TeleBot(os.getenv('TELEGRAM_TOKEN'))

# Парсер каналов
class ChannelParser:
    CHANNELS = {
        "cats": {
            "username": "Lapki_ruchki_Yalta_help",
            "url": "https://t.me/Lapki_ruchki_Yalta_help",
            "keywords": ["кот", "кошк", "котен", "котик"]
        },
        "dogs": {
            "username": "yalta_aninmals",
            "url": "https://t.me/yalta_aninmals",
            "keywords": ["собак", "щен", "пес", "гав"]
        }
    }

    def get_posts(self, animal_type: str, limit: int = 3) -> list:
        try:
            channel = self.CHANNELS[animal_type]
            url = f"https://t.me/s/{channel['username']}"
            response = requests.get(url, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            posts = []
            for message in soup.find_all('div', class_='tgme_widget_message')[:limit]:
                text_div = message.find('div', class_='tgme_widget_message_text')
                if text_div:
                    text = text_div.get_text('\n').strip()
                    if any(kw in text.lower() for kw in channel['keywords']):
                        post_id = message.get('data-post', '').split('/')[-1]
                        photo_style = message.find('a', class_='tgme_widget_message_photo_wrap').get('style', '')
                        photo_url = re.search(r"url\('(.*?)'\)", photo_style).group(1) if photo_style else None
                        
                        posts.append({
                            'text': text,
                            'photo_url': photo_url,
                            'url': f"{channel['url']}/{post_id}"
                        })
            
            return posts if posts else self._get_mock_posts(animal_type)
        
        except Exception as e:
            logger.error(f"Ошибка парсинга: {str(e)}")
            return self._get_mock_posts(animal_type)

    def _get_mock_posts(self, animal_type: str) -> list:
        if animal_type == "cats":
            return [{
                'text': "Котенок ищет дом. Мальчик, 2 месяца.",
                'photo_url': None,
                'url': "https://t.me/Lapki_ruchki_Yalta_help/123"
            }]
        else:
            return [{
                'text': "Щенок ищет хозяина. Девочка, 3 месяца.",
                'photo_url': None,
                'url': "https://t.me/yalta_aninmals/456"
            }]

parser = ChannelParser()

# Обработчики команд
@bot.message_handler(commands=['start'])
def send_welcome(message):
    try:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.row("🏥 Стерилизация", "🏠 Пристройство")
        markup.row("📞 Контакты", "ℹ️ О проекте")
        
        bot.send_message(
            message.chat.id,
            "🐾 <b>Помощник для животных Ялты</b>\n\n"
            "Выберите раздел:",
            reply_markup=markup,
            parse_mode="HTML"
        )
        logger.info(f"Пользователь {message.chat.id} запустил бота")
    except Exception as e:
        logger.error(f"Ошибка в /start: {str(e)}")

@bot.message_handler(func=lambda m: m.text == "🏠 Пристройство")
def adoption(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🐱 Кошки", "🐶 Собаки")
    markup.add("🔙 Назад")
    
    bot.send_message(
        message.chat.id,
        "🏠 <b>Пристройство животных</b>\n\nВыберите категорию:",
        reply_markup=markup,
        parse_mode="HTML"
    )

@bot.message_handler(func=lambda m: m.text in ["🐱 Кошки", "🐶 Собаки"])
def show_animals(message):
    animal_type = "cats" if message.text == "🐱 Кошки" else "dogs"
    posts = parser.get_posts(animal_type)
    
    emoji = "🐱" if animal_type == "cats" else "🐶"
    bot.send_message(
        message.chat.id,
        f"{emoji} <b>Последние объявления</b>",
        parse_mode="HTML"
    )
    
    for post in posts:
        try:
            if post['photo_url']:
                bot.send_photo(
                    message.chat.id,
                    post['photo_url'],
                    caption=f"{post['text']}\n\n🔗 <a href='{post['url']}'>Открыть в канале</a>",
                    parse_mode="HTML"
                )
            else:
                bot.send_message(
                    message.chat.id,
                    f"{post['text']}\n\n🔗 <a href='{post['url']}'>Открыть в канале</a>",
                    parse_mode="HTML"
                )
        except Exception as e:
            logger.error(f"Ошибка отправки поста: {str(e)}")

@bot.message_handler(func=lambda m: m.text == "🏥 Стерилизация")
def sterilization(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("💰 Платная", "🆓 Бесплатная")
    markup.add("🔙 Назад")
    
    bot.send_message(
        message.chat.id,
        "🏥 <b>Программы стерилизации</b>\n\nВыберите тип:",
        reply_markup=markup,
        parse_mode="HTML"
    )

@bot.message_handler(func=lambda m: m.text in ["💰 Платная", "🆓 Бесплатная"])
def show_sterilization(message):
    text = (
        "Платная стерилизация:\n\n"
        "Клиника 'Айболит': 1500-2000 руб\n"
        "Тел: +7 978 123-45-67" 
        if message.text == "💰 Платная" else
        "Бесплатная стерилизация:\n\n"
        "Для бездомных животных\n"
        "Запись: +7 978 765-43-21"
    )
    bot.send_message(message.chat.id, text)

@bot.message_handler(func=lambda m: m.text == "🔙 Назад")
def back(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🏥 Стерилизация", "🏠 Пристройство")
    markup.row("📞 Контакты", "ℹ️ О проекте")
    bot.send_message(message.chat.id, "Главное меню:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "📞 Контакты")
def contacts(message):
    bot.send_message(
        message.chat.id,
        "📞 <b>Контакты</b>\n\n"
        "Координатор по кошкам: @cat_helper\n"
        "Координатор по собакам: @dog_helper\n"
        "Телефон: +7 978 111-22-33",
        parse_mode="HTML"
    )

@bot.message_handler(func=lambda m: m.text == "ℹ️ О проекте")
def about(message):
    bot.send_message(
        message.chat.id,
        "ℹ️ <b>О проекте</b>\n\n"
        "Помощь бездомным животным Ялты\n"
        "Работаем с 2020 года",
        parse_mode="HTML"
    )

if __name__ == '__main__':
    logger.info("Запуск бота...")
    while True:
        try:
            bot.polling(none_stop=True)
        except Exception as e:
            logger.error(f"Ошибка: {str(e)}")
            time.sleep(15)
