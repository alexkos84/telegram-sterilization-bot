# В класс CatBotWithPhotos добавляем новые методы:

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

# В setup_handlers обновляем обработчик раздела стерилизации:
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
    except:
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
