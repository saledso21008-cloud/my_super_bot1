import json
import os
import telegram
from flask import Flask, request

TOKEN = "8215589738:AAFYtsklp7838K1HHLQNMln9r6Aj_YGMhlc"
ADMIN_ID = 5186730282
bot = telegram.Bot(token=TOKEN)
app = Flask(__name__)

@app.route('/', methods=['POST'])
def webhook():
    try:
        update = telegram.Update.de_json(request.get_json(force=True), bot)
        
        if update.message and update.message.text == '/start':
            bot.send_message(chat_id=update.effective_chat.id, text="Привет! Я бот на Netlify!")
        elif update.message:
            bot.send_message(chat_id=update.effective_chat.id, text=f"Ты написал: {update.message.text}")
        
        return 'ok', 200
    except Exception as e:
        print(e)
        return 'error', 500

@app.route('/', methods=['GET'])
def index():
    return 'Bot is running!', 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
