import os
import telebot
from telebot import types
from flask import Flask, request
from datetime import datetime
import time

TOKEN = os.environ.get('TOKEN')
if not TOKEN:
    print("❌ Ошибка: Переменная TOKEN не найдена!")
    exit(1)

PORT = int(os.environ.get('PORT', 8080))
WEBHOOK_URL = os.environ.get('RAILWAY_STATIC_URL')  # Автоматически на Railway

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

paid_text = (
    "💰✨ <b>ПЛАТНАЯ СТЕРИЛИЗАЦИЯ</b> ✨💰\n\n"
    "📋 <b>Рекомендуем уточнять цены при записи</b>\n"
    "🕒 <b>Режим работы может различаться</b>\n"
    "💙 <b>Выберите удобную для вас клинику!</b>\n\n"

    "🐾 <b>Евгения Кононенко</b>\n"
    "📍 <a href='https://yandex.ru/maps/?text=Ялта+ул.+Изобильная+20'>ул. Изобильная, 20</a>\n"
    "📞 +79789885105\n"
    "💵 <b>Стерилизация от 2000₽</b>\n\n"

    "🐾 <b>Фауна</b>\n"
    "📍 <a href='https://yandex.ru/maps/?text=Ялта+ул.+Изобильная+20'>ул. Изобильная, 20</a>\n"
    "📞 +79789885105\n"
    "💵 <b>Стерилизация от 2300₽</b>\n\n"

    "🐾 <b>Доктор Лукьянов</b>\n"
    "📍 <a href='https://yandex.ru/maps/?text=Ялта+ул.+Гоголя+16'>ул. Гоголя, 16</a>\n"
    "📞 +79788789309\n"
    "💵 <b>Стерилизация кошки 4500₽</b>\n"
    "💵 <b>Кастрация кота 3500₽</b>\n\n"

    "🐾 <b>ЗдоровейКо</b>\n"
    "📍 <a href='https://yandex.ru/maps/?text=Ялта+ул.+Красноармейская+6'>ул. Красноармейская, 6</a>\n"
    "📞 +79787824682\n"
    "💵 <b>Стерилизация кошки 3500₽</b>\n"
    "💵 <b>Кастрация кота 2500₽</b>\n\n"

    "🐾 <b>Юлия Терещук</b>\n"
    "📍 <a href='https://yandex.ru/maps/?text=Ялта+ул.+Московская+31'>ул. Московская, 31</a>\n"
    "📞 +79782906405\n"
    "💵 <b>Стерилизация от 3000₽</b>\n\n"

    "🐾 <b>Айболит</b>\n"
    "📍 <a href='https://yandex.ru/maps/?text=Ялта+ул.+Васильева+7'>ул. Васильева, 7</a>\n"
    "📞 +79788697009\n"
    "💵 <b>Стерилизация от 1800₽</b>\n\n"

    "🐾 <b>Ялтинский ветеринарный госпиталь</b>\n"
    "📍 <a href='https://yandex.ru/maps/?text=Ялта+ул.+Тимирязева+33'>ул. Тимирязева, 33</a>\n"
    "📞 +79787116762\n"
    "💵 <b>Стерилизация от 2000₽</b>\n\n"

    "🐾 <b>Доверие</b>\n"
    "📍 <a href='https://yandex.ru/maps/?text=Ялта+ул.+Халтурина+52А'>ул. Халтурина, 52А</a>\n"
    "📞 +79782561501\n"
    "💬 <i>Цена уточняется</i>\n\n"

    "🐾 <b>ГБУ ВЛПЦ</b>\n"
    "📍 <a href='https://yandex.ru/maps/?text=Ялта+ул.+Соханя+5'>ул. Соханя, 5</a>\n"
    "📞 +79788603698\n"
    "💬 <i>Цена уточняется</i>\n\n"
)

free_text = (
    "🎉 <b>БЕСПЛАТНАЯ СТЕРИЛИЗАЦИЯ</b> 🎉\n"
    "🐈‍⬛ <b>для бездомных кошек.</b> 🐈‍⬛\n"
    "🏥 <b>В клинике «Айболит»</b>\n"
    "📍 <a href='https://yandex.ru/maps/-/CHXZj0jJ'>г. Ялта, ул. Васильева, 7</a>\n"
    "<b>⚠️ ЗАПИСЬ ОБЯЗАТЕЛЬНА!</b>\n\n"
    "➿➿➿➿➿➿➿➿➿➿➿\n\n"
    "‼️ <b>Звоните за 2–3 дня до отлова:</b>\n"
    "⏰ <b>Время приёма заявок: 8:00 — 9:00</b>\n"
    "<i>(все дни, кроме четверга)</i>\n"
    "📞 +79781449070 <b>(Екатерина)</b>\n\n"
    "➿➿➿➿➿➿➿➿➿➿➿\n\n"
    "⚠️ <b>ВАЖНЫЕ ТРЕБОВАНИЯ:</b>\n\n"
    "‼️ <b>С Вас отловить и привезти кошку в клинику</b>\n"
    "🔸 <b>Перед операцией:</b> <u>НЕ кормите кошку</u>\n"    
    "🔸 <b>Переноска:</b> только пластиковая и прочная\n"
    "   <i>(при сомнениях — перемотайте скотчем!)</i>\n"
    "🔸 <b>Внутри:</b> обязательно положите пелёнку\n"
    "🔸 <b>На переноску:</b> приклейте записку с адресом\n"
    "   и вашим номером телефона\n"
    "🍗 <b>Можете положить мягкий корм в пакетиках</b>\n"
    "🚫 <b><u>Тканевые переноски и сумки ЗАПРЕЩЕНЫ!</u></b>\n\n"
    "➿➿➿➿➿➿➿➿➿➿➿\n\n"
    "🛡️ <b>ПОСЛЕ СТЕРИЛИЗАЦИИ:</b>\n\n"
    "✅ <b>Кошку забирают наши волонтёры</b>\n"
    "✅ <b>Передержка 1–2 дня для восстановления</b>\n"
    "✅ <b>Возврат по указанному Вами адресу</b>\n\n"
    "➿➿➿➿➿➿➿➿➿➿➿\n\n"
    "📢 <b>ДРУЗЬЯ, НЕ УПУСТИТЕ ШАНС!</b>\n\n"
    "🐾 <b>Количество мест ОГРАНИЧЕНО</b>\n"
    "☎️ <b>Звоните и записывайтесь прямо сейчас!</b>\n\n"
    "💙🐱 <b><i>Вместе мы делаем мир добрее!</i></b> 🐱💙"
)

# Webhook обработчик
@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''
    return 'Bad request', 403

@app.route('/')
def home():
    return f"🤖 Bot is running! Time: {datetime.now().strftime('%H:%M:%S')}"

@app.route('/health')
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}

@bot.message_handler(commands=['start'])
def start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("💰 Платная", "🆓 Бесплатная")
    bot.send_message(message.chat.id, "Выберите тип стерилизации:", reply_markup=markup)

@bot.message_handler(commands=['status'])
def status(message):
    current_time = datetime.now().strftime('%d.%m.%Y %H:%M:%S')
    bot.send_message(message.chat.id, f"🤖 Бот работает!\n⏰ Время: {current_time}")

@bot.message_handler(func=lambda message: True)
def handle_buttons(message):
    if message.text == "💰 Платная":
        bot.send_message(message.chat.id, paid_text, parse_mode="HTML", disable_web_page_preview=True)
    elif message.text == "🆓 Бесплатная":
        bot.send_message(message.chat.id, free_text, parse_mode="HTML", disable_web_page_preview=True)
    else:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("💰 Платная", "🆓 Бесплатная")
        bot.send_message(message.chat.id, "Пожалуйста, выберите одну из кнопок ниже:", reply_markup=markup)

def setup_webhook():
    try:
        bot.remove_webhook()
        time.sleep(1)
        bot.set_webhook(url=f"https://{WEBHOOK_URL}/{TOKEN}")
        print(f"✅ Webhook установлен: https://{WEBHOOK_URL}/{TOKEN}")
    except Exception as e:
        print(f"❌ Ошибка webhook: {e}")

if __name__ == "__main__":
    setup_webhook()
    app.run(host='0.0.0.0', port=PORT)

