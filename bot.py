# -*- coding: utf-8 -*-
import logging
import sqlite3
import pandas as pd
import os
import math
import asyncio
from datetime import datetime, timedelta
import pytz
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

TOKEN = "8215589738:AAFYtsklp7838K1HHLQNMln9r6Aj_YGMhlc"
ADMIN_ID = 5186730282
MOSCOW_TZ = pytz.timezone('Europe/Moscow')
REMINDER_TIMES = ["16:00", "19:00", "21:00"]
LONG_TASK_THRESHOLD = 90

SUBJECTS = [
    "Русский язык", "Литература", "Иностранный язык",
    "Алгебра", "Геометрия", "Вероятность и статистика",
    "История", "Обществознание", "География",
    "Биология", "Физика", "Химия",
    "Информатика", "ОБЖ", "Технология", "Музыка"
]

def init_db():
    conn = sqlite3.connect('homework.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            username TEXT,
            full_name TEXT,
            class TEXT,
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS homework_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            subject TEXT,
            date DATE,
            start_time TEXT,
            end_time TEXT,
            duration_seconds INTEGER,
            duration_minutes INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS active_timers (
            user_id INTEGER PRIMARY KEY,
            subject TEXT,
            start_time TIMESTAMP,
            last_check_time TIMESTAMP,
            check_count INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    return conn, cursor

db_conn, db_cursor = init_db()

def is_admin(user_id):
    return user_id == ADMIN_ID

def save_active_timer(user_id, subject, start_time):
    db_cursor.execute("INSERT OR REPLACE INTO active_timers (user_id, subject, start_time, last_check_time, check_count) VALUES (?, ?, ?, ?, ?)",
                      (user_id, subject, start_time, datetime.now(), 0))
    db_conn.commit()

def remove_active_timer(user_id):
    db_cursor.execute("DELETE FROM active_timers WHERE user_id = ?", (user_id,))
    db_conn.commit()

def get_active_timers():
    db_cursor.execute("SELECT at.*, u.full_name, u.class FROM active_timers at JOIN users u ON at.user_id = u.user_id")
    return db_cursor.fetchall()

def update_timer_check(user_id):
    db_cursor.execute("UPDATE active_timers SET last_check_time = ?, check_count = check_count + 1 WHERE user_id = ?",
                      (datetime.now(), user_id))
    db_conn.commit()

async def send_reminder_to_all(app):
    db_cursor.execute("SELECT user_id, full_name FROM users")
    users = db_cursor.fetchall()
    if not users:
        return 0, "❌ Нет пользователей"
    message = "📢 ВАЖНОЕ НАПОМИНАНИЕ!\n\nПожалуйста, не забывайте пользоваться ботом!\n\n📚 Сделайте домашнее задание и отметьте его в боте.\nСпасибо!"
    sent = 0
    for uid, name in users:
        try:
            await app.bot.send_message(chat_id=uid, text=message)
            sent += 1
            await asyncio.sleep(0.3)
        except:
            pass
    return sent, f"✅ Отправлено {sent} из {len(users)}"

async def check_long_tasks(app):
    active = get_active_timers()
    for timer in active:
        uid, subject, start, last, count, name, cls = timer
        if isinstance(start, str):
            start = datetime.fromisoformat(start)
        dur = (datetime.now() - start).total_seconds() / 60
        if dur > LONG_TASK_THRESHOLD and count < 3:
            if isinstance(last, str):
                last = datetime.fromisoformat(last)
            if (datetime.now() - last).total_seconds() / 60 > 30:
                update_timer_check(uid)
                try:
                    kb = [["✅ Да, еще делаю"], ["❌ Нет, уже закончил"]]
                    markup = ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True)
                    await app.bot.send_message(chat_id=uid, text=f"⏰ Вы уже {int(dur)} минут делаете {subject}!\n\nВы еще делаете это задание?", reply_markup=markup)
                except:
                    pass

def create_excel_for_admin():
    print(f"📊 Запрос Excel, всего строк в БД: {db_cursor.execute('SELECT COUNT(*) FROM homework_sessions').fetchone()[0]}")
    db_cursor.execute("""
        SELECT u.class, u.full_name, h.subject, h.duration_seconds, h.start_time, h.end_time, h.date
        FROM homework_sessions h JOIN users u ON h.user_id = u.user_id
        ORDER BY h.created_at DESC
    """)
    data = db_cursor.fetchall()
    if not data:
        return None, "❌ Нет данных"
    rows = []
    for row in data:
        cls, name, subj, sec, st, et, date = row
        if sec < 60:
            dur = f"{sec} сек"
        elif sec % 60 == 0:
            dur = f"{sec//60} мин"
        else:
            dur = f"{sec//60} мин {sec%60} сек"
        rows.append([cls, name, subj, dur, f"{st}-{et}", date])
    df = pd.DataFrame(rows, columns=['Класс', 'Ученик', 'Предмет', 'Время', 'Начало-Конец', 'Дата'])
    fname = 'homework_data.xlsx'
    df.to_excel(fname, index=False)
    db_cursor.execute("SELECT COUNT(*) FROM users")
    users_cnt = db_cursor.fetchone()[0]
    db_cursor.execute("SELECT COUNT(*) FROM homework_sessions")
    sess_cnt = db_cursor.fetchone()[0]
    return fname, f"📊 Всего записей: {sess_cnt}\n👥 Учеников: {users_cnt}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_cursor.execute("SELECT * FROM users WHERE user_id = ?", (user.id,))
    existing = db_cursor.fetchone()
    if existing:
        if is_admin(user.id):
            kb = [["📚 Начать задание"], ["📊 Моя статистика"], ["📢 Отправить напоминание всем"], ["📊 Получить Excel", "🔔 Проверить долгие задания"]]
        else:
            kb = [["📚 Начать задание"], ["📊 Моя статистика"], ["🏠 Главное меню"]]
        await update.message.reply_text("Выбери действие:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
    else:
        await update.message.reply_text("📝 Для регистрации напиши свою фамилию и имя:", reply_markup=ReplyKeyboardRemove())
        context.user_data['step'] = 'name'

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text
    step = context.user_data.get('step', '')
    if text in ["✅ Да, еще делаю", "❌ Нет, уже закончил"]:
        db_cursor.execute("SELECT * FROM active_timers WHERE user_id = ?", (user.id,))
        timer = db_cursor.fetchone()
        if not timer:
            await update.message.reply_text("Нет активных заданий")
            return
        subj, start = timer[1], timer[2]
        if text == "✅ Да, еще делаю":
            update_timer_check(user.id)
            await update.message.reply_text("✅ Хорошо, продолжаем!", reply_markup=ReplyKeyboardMarkup([["⏹️ Завершить"]], resize_keyboard=True))
        else:
            if isinstance(start, str):
                start = datetime.fromisoformat(start)
            context.user_data['current_subject'] = subj
            context.user_data['start_datetime'] = start
            end = datetime.now(MOSCOW_TZ)
            sec = int((end - start).total_seconds())
            print(f"💾 СОХРАНЯЮ задание для user {user.id}, предмет {subj}, секунд {sec}")
            db_cursor.execute("INSERT INTO homework_sessions (user_id, subject, date, start_time, end_time, duration_seconds, duration_minutes) VALUES (?, ?, ?, ?, ?, ?, ?)",
                              (user.id, subj, start.strftime("%d.%m.%Y"), start.strftime("%H:%M:%S"), end.strftime("%H:%M:%S"), sec, sec//60))
            db_conn.commit()
            remove_active_timer(user.id)
            context.user_data.clear()
            if sec < 60:
                tm = f"{sec} сек"
            else:
                m = sec // 60
                s = sec % 60
                tm = f"{m} мин {s} сек" if s else f"{m} мин"
            await update.message.reply_text(f"✅ Завершено!\n📚 {subj}\n⏱️ {tm}")
            await show_main_menu(update, user.id)
        return
    if step == 'name':
        if len(text.split()) < 2:
            await update.message.reply_text("Напиши фамилию и имя через пробел")
            return
        context.user_data['name'] = text
        context.user_data['step'] = 'class'
        kb = [["7А", "7Б", "7В"], ["8А", "8Б", "8В"], ["9А", "9Б", "9В"],
              ["10(гуманитарный)", "10(информационно-технологический)"], ["11А"]]
        await update.message.reply_text("Выбери класс:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True, one_time_keyboard=True))
        return
    if step == 'class':
        valid = ["7А", "7Б", "7В", "8А", "8Б", "8В", "9А", "9Б", "9В",
                 "10(гуманитарный)", "10(информационно-технологический)", "11А"]
        if text not in valid:
            await update.message.reply_text("Выбери из списка")
            return
        db_cursor.execute("INSERT INTO users (user_id, username, full_name, class) VALUES (?, ?, ?, ?)",
                          (user.id, user.username, context.user_data['name'], text))
        db_conn.commit()
        context.user_data.clear()
        await update.message.reply_text("✅ Регистрация завершена!")
        await show_main_menu(update, user.id)
        return
    if text == "📚 Начать задание":
        kb = []
        for i in range(0, len(SUBJECTS), 2):
            kb.append(SUBJECTS[i:i+2])
        kb.append(["🏠 Главное меню"])
        await update.message.reply_text("Выбери предмет:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return
    if text in SUBJECTS:
        now = datetime.now(MOSCOW_TZ)
        context.user_data['current_subject'] = text
        context.user_data['start_datetime'] = now
        save_active_timer(user.id, text, now)
        await update.message.reply_text(f"✅ Начато: {text}\n🕐 {now.strftime('%H:%M:%S')}",
                                         reply_markup=ReplyKeyboardMarkup([["⏹️ Завершить"]], resize_keyboard=True))
        return
    if text == "⏹️ Завершить":
        if 'current_subject' in context.user_data:
            subj = context.user_data['current_subject']
            start = context.user_data['start_datetime']
            end = datetime.now(MOSCOW_TZ)
            sec = int((end - start).total_seconds())
            print(f"💾 СОХРАНЯЮ задание для user {user.id}, предмет {subj}, секунд {sec}")
            db_cursor.execute("INSERT INTO homework_sessions (user_id, subject, date, start_time, end_time, duration_seconds, duration_minutes) VALUES (?, ?, ?, ?, ?, ?, ?)",
                              (user.id, subj, start.strftime("%d.%m.%Y"), start.strftime("%H:%M:%S"), end.strftime("%H:%M:%S"), sec, sec//60))
            db_conn.commit()
            remove_active_timer(user.id)
            context.user_data.clear()
            if sec < 60:
                tm = f"{sec} сек"
            else:
                m = sec // 60
                s = sec % 60
                tm = f"{m} мин {s} сек" if s else f"{m} мин"
            await update.message.reply_text(f"✅ Завершено!\n📚 {subj}\n⏱️ {tm}")
        else:
            await update.message.reply_text("Нет активного задания")
        await show_main_menu(update, user.id)
        return
    if text == "🏠 Главное меню":
        await show_main_menu(update, user.id)
        return
    if text == "📊 Моя статистика":
        db_cursor.execute("SELECT full_name, class FROM users WHERE user_id = ?", (user.id,))
        u = db_cursor.fetchone()
        if not u:
            await update.message.reply_text("Сначала зарегистрируйся")
            return
        db_cursor.execute("SELECT COUNT(*), SUM(duration_seconds), AVG(duration_seconds) FROM homework_sessions WHERE user_id = ?", (user.id,))
        s = db_cursor.fetchone()
        if not s or s[0] == 0:
            await update.message.reply_text("Пока нет заданий")
            return
        cnt, tot, avg = s
        await update.message.reply_text(f"📊 {u[0]} ({u[1]})\n📝 Заданий: {cnt}\n⏱️ Всего: {tot/3600:.1f} ч\n📏 Среднее: {avg/60:.0f} мин")
        return
    if text == "📢 Отправить напоминание всем" and is_admin(user.id):
        msg = await update.message.reply_text("🔄 Отправка...")
        sent, res = await send_reminder_to_all(context.application)
        await msg.edit_text(res)
        return
    if text == "📊 Получить Excel" and is_admin(user.id):
        msg = await update.message.reply_text("🔄 Создание...")
        f, cap = create_excel_for_admin()
        if f and os.path.exists(f):
            with open(f, 'rb') as fl:
                await msg.delete()
                await update.message.reply_document(document=fl, caption=cap)
        else:
            await msg.edit_text("❌ Нет данных")
        return
    if text == "🔔 Проверить долгие задания" and is_admin(user.id):
        await check_long_tasks(context.application)
        await update.message.reply_text("✅ Проверка выполнена")
        return
    db_cursor.execute("SELECT * FROM users WHERE user_id = ?", (user.id,))
    if db_cursor.fetchone():
        await show_main_menu(update, user.id)
    else:
        await update.message.reply_text("Напиши /start")

async def show_main_menu(update: Update, user_id: int):
    if is_admin(user_id):
        kb = [["📚 Начать задание"], ["📊 Моя статистика"], ["📢 Отправить напоминание всем"], ["📊 Получить Excel", "🔔 Проверить долгие задания"]]
        txt = "👑 АДМИН ПАНЕЛЬ"
    else:
        kb = [["📚 Начать задание"], ["📊 Моя статистика"], ["🏠 Главное меню"]]
        txt = "Выбери действие:"
    await update.message.reply_text(txt, reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

async def auto_reminder_loop(app):
    while True:
        now = datetime.now(MOSCOW_TZ).strftime("%H:%M")
        if now in REMINDER_TIMES:
            print(f"⏰ Напоминание в {now}")
            await send_reminder_to_all(app)
        if datetime.now(MOSCOW_TZ).minute % 15 == 0:
            await check_long_tasks(app)
        await asyncio.sleep(60)

def main():
    print("=" * 50)
    print("🤖 Бот для железной дороги")
    print("=" * 50)
    db_cursor.execute("SELECT COUNT(*) FROM users")
    print(f"👥 Пользователей: {db_cursor.fetchone()[0]}")
    print("=" * 50)
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Запускаем фоновые задачи
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(auto_reminder_loop(app))
    
    print("✅ Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
