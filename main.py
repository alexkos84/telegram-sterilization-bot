import os
import telebot
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv('TOKEN')
if not TOKEN:
    logger.error("❌ Токен не найден!")
    exit(1)

bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start'])
def start_handler(message):
    logger.info(f"Получен /start от {message.from_user.id}")
    bot.send_message(
        message.chat.id,
        "🟢 Бот работает!\n"
        "Попробуйте команды:\n"
        "/cats - кошки\n"
        "/dogs - собаки"
    )

@bot.message_handler(commands=['cats'])
def cats_handler(message):
    bot.send_message(message.chat.id, "🐱 Ищем кошек...")

@bot.message_handler(commands=['dogs'])
def dogs_handler(message):
    bot.send_message(message.chat.id, "🐶 Ищем собак...")

if __name__ == "__main__":
    logger.info("🚀 Запуск тестового бота...")
    bot.polling(none_stop=True)
