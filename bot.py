import telebot
import os

TOKEN = os.environ.get('TOKEN')
ADMIN_ID = 5186730282  # сюда свой ID

bot = telebot.TeleBot(TOKEN)

# Проверка на админа
def is_admin(user_id):
    return user_id == ADMIN_ID

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "Привет! Бот работает!")

@bot.message_handler(func=lambda m: m.text == "админ команда" and is_admin(m.from_user.id))
def admin_command(message):
    bot.reply_to(message, "Ты админ!")

@bot.message_handler(func=lambda m: True)
def echo(message):
    bot.reply_to(message, f"Ты написал: {message.text}")

print("Бот запущен!")
bot.infinity_polling()
