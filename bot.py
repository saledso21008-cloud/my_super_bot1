# -*- coding: utf-8 -*-
import sqlite3
import pandas as pd
import os
import asyncio
from datetime import datetime
import pytz
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

TOKEN = "8215589738:AAFYtsklp7838K1HHLQNMln9r6Aj_YGMhlc"
ADMIN_ID = 5186730282
MOSCOW_TZ = pytz.timezone('Europe/Moscow')
REMINDER_TIMES = ["16:00", "19:00", "21:00"]
LONG_TASK_THRESHOLD = 90

SUBJECTS = ["Русский язык", "Литература", "Иностранный язык", "Алгебра", "Геометрия", "Вероятность и статистика", "История", "Обществознание", "География", "Биология", "Физика", "Химия", "Информатика", "ОБЖ", "Технология", "Музыка"]

def init_db():
    conn = sqlite3.connect('homework.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER UNIQUE, username TEXT, full_name TEXT, class TEXT, registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS homework_sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, subject TEXT, date DATE, start_time TEXT, end_time TEXT, duration_seconds INTEGER, duration_minutes INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS active_timers (user_id INTEGER PRIMARY KEY, subject TEXT, start_time TIMESTAMP, last_check_time TIMESTAMP, check_count INTEGER DEFAULT 0)')
    conn.commit()
    return conn, cursor

db_conn, db_cursor = init_db()

def is_admin(user_id):
    return user_id == ADMIN_ID

def save_active_timer(user_id, subject, start_time):
    db_cursor.execute("INSERT OR REPLACE INTO active_timers VALUES (?, ?, ?, ?, ?)", (user_id, subject, start_time, datetime.now(), 0))
    db_conn.commit()

def remove_active_timer(user_id):
    db_cursor.execute("DELETE FROM active_timers WHERE user_id = ?", (user_id,))
    db_conn.commit()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if db_cursor.execute("SELECT * FROM users WHERE user_id = ?", (user.id,)).fetchone():
        kb = [["📚 Начать задание"], ["📊 Моя статистика"], ["📢 Отправить напоминание всем"], ["📊 Получить Excel"]] if is_admin(user.id) else [["📚 Начать задание"], ["📊 Моя статистика"], ["🏠 Главное меню"]]
        await update.message.reply_text("Выбери действие:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
    else:
        await update.message.reply_text(
            "📝 Для регистрации напиши фамилию и имя.\n\n"
            "🙏Убедительная просьба пользоваться ботом регулярно🕐, всего 10 дней до конца четверти, тем самым вы поможете с проектом, спасибо за понимание❤❗ Используя бота, вы соглашаетесь на передачу и обработку информации о вашей успеваемости.",
            reply_markup=ReplyKeyboardRemove()
        )
        context.user_data['step'] = 'name'

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text
    step = context.user_data.get('step', '')

    if text == "/users":
        count = db_cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        await update.message.reply_text(f"👥 Всего пользователей в боте: {count}")
        return
    
    if text == "/resetme":
        db_cursor.execute("DELETE FROM users WHERE user_id = ?", (user.id,))
        db_conn.commit()
        await update.message.reply_text("Вы уверены? Нажми /start для новой регистрации.")
        return

    if step == "name":
        context.user_data['name'] = text
        context.user_data['step'] = 'class'
        await update.message.reply_text("Выбери класс:", reply_markup=ReplyKeyboardMarkup([["7A", "7Б", "7В"], ["8A", "8Б", "8В"], ["9A", "9Б", "9В"], ["10А", "11А"]]))
        return

    if step == "class":
        db_cursor.execute(
            "INSERT INTO users VALUES (NULL, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
            (user.id, user.username, context.user_data['name'], text)
        )
        db_conn.commit()
        context.user_data.clear()
        await update.message.reply_text("✅ Регистрация завершена!")
        await show_main_menu(update, user.id)   # 👈 ЭТО ВАЖНО
        return

    if text == "📚 Начать задание":
        # Проверяем, есть ли пользователь в базе
        user_in_db = db_cursor.execute("SELECT * FROM users WHERE user_id = ?", (user.id,)).fetchone()
        if not user_in_db:
            await update.message.reply_text(
                "❌ Ваш аккаунт не найден в боте.\n"
                "Возможно, данные были сброшены.\n\n"
                "📝 Пожалуйста, зарегистрируйтесь заново, написав своё имя и фамилию:"
            )
            context.user_data['step'] = 'name'
            return

        # Если пользователь есть — показываем предметы
        kb = [SUBJECTS[i:i+2] for i in range(0, len(SUBJECTS), 2)] + [["🏠 Главное меню"]]
        await update.message.reply_text("Выбери предмет:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return

    if text == "⏹️ Завершить":
        if 'current_subject' in context.user_data:
            subj = context.user_data['current_subject']
            start = context.user_data['start_datetime']
            end = datetime.now(MOSCOW_TZ)
            sec = int((end - start).total_seconds())
            db_cursor.execute("INSERT INTO homework_sessions VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)", (user.id, subj, start.strftime("%d.%m.%Y"), start.strftime("%H:%M:%S"), end.strftime("%H:%M:%S"), sec, sec//60))
            db_conn.commit()
            remove_active_timer(user.id)
            context.user_data.clear()
            await update.message.reply_text(f"✅ Завершено!\n{subj}\n{sec//60} мин {sec%60} сек")
        else:
            await update.message.reply_text("Нет активного задания")
        await show_main_menu(update, user.id)
        return

    if text == "🏠 Главное меню":
        await show_main_menu(update, user.id)
        return

    if text == "📊 Моя статистика":
        u = db_cursor.execute("SELECT full_name, class FROM users WHERE user_id = ?", (user.id,)).fetchone()
        if not u:
            await update.message.reply_text("Сначала зарегистрируйся")
            return
        s = db_cursor.execute("SELECT COUNT(*), SUM(duration_seconds) FROM homework_sessions WHERE user_id = ?", (user.id,)).fetchone()
        await update.message.reply_text(f"📊 {u[0]} ({u[1]})\n📝 Заданий: {s[0]}\n⏱️ Всего: {s[1]//60} мин")
        return

    if text == "📢 Отправить напоминание всем" and is_admin(user.id):
        for uid, in db_cursor.execute("SELECT user_id FROM users").fetchall():
            try:
                await context.application.bot.send_message(chat_id=uid, text="Напоминание!")
            except:
                pass
        await update.message.reply_text("✅ Отправлено")
        return

    if text == "📊 Получить Excel" and is_admin(user.id):
        data = db_cursor.execute("""
            SELECT 
                u.user_id,
                u.full_name,
                h.subject,
                h.duration_seconds,
                h.start_time,
                h.end_time,
                h.date
            FROM homework_sessions h
            JOIN users u ON h.user_id = u.user_id
            ORDER BY h.created_at DESC
        """).fetchall()

        if not data:
            await update.message.reply_text("❌ Нет данных")
            return

        rows = []
        for row in data:
            user_id, name, subject, sec, start, end, date = row
            minutes = sec // 60
            seconds = sec % 60
            time_str = f"{minutes} мин {seconds} сек" if minutes > 0 else f"{seconds} сек"
            rows.append([user_id, name, subject, time_str, f"{start} — {end}", date])

        df = pd.DataFrame(rows, columns=["ID", "Имя", "Предмет", "Время", "Начало — Конец", "Дата"])
        df.to_excel("data.xlsx", index=False)

        with open("data.xlsx", "rb") as f:
            await update.message.reply_document(f)
        return

async def show_main_menu(update: Update, user_id: int):
    kb = [["📚 Начать задание"], ["📊 Моя статистика"], ["📢 Отправить напоминание всем"], ["📊 Получить Excel"]] if is_admin(user_id) else [["📚 Начать задание"], ["📊 Моя статистика"], ["🏠 Главное меню"]]
    await update.message.reply_text("Меню:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
