# -*- coding: utf-8 -*-
import sqlite3
import asyncio
import logging
import pandas as pd
import os
import math
from datetime import datetime, timedelta
import pytz
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# ====== ЭТО ВСТАВЛЯЕШЬ В САМОЕ НАЧАЛО ======
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
    print("✅ База данных готова")
    return conn, cursor

# ====== СОЗДАЁМ БАЗУ ПРЯМО ЗДЕСЬ ======
db_conn, db_cursor = init_db()

# ====== ТВОЙ ОСТАЛЬНОЙ КОД ======
# Сюда вставляешь всё остальное: токен, функции, хендлеры и т.д.

# ТОКЕН и НАСТРОЙКИ
TOKEN = "8215589738:AAFYtsklp7838K1HHLQNMln9r6Aj_YGMhlc"
ADMIN_ID = 5186730282

MOSCOW_TZ = pytz.timezone('Europe/Moscow')

# Время напоминаний
REMINDER_TIMES = ["16:00", "19:00", "21:00"]

# Время проверки долгих заданий
LONG_TASK_THRESHOLD = 90  # 1.5 часа

# Список предметов
SUBJECTS = [
    "Русский язык", "Литература", "Иностранный язык",
    "Алгебра", "Геометрия", "Вероятность и статистика",
    "История", "Обществознание", "География",
    "Биология", "Физика", "Химия",
    "Информатика", "ОБЖ", "Технология", "Музыка"
]

# База данных
def init_db():
    conn = sqlite3.connect('homework.db', check_same_thread=False)
    cursor = conn.cursor()
    
    # Users
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
    
    # Homework sessions
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
    
    # Active timers
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
    print("✅ База данных готова (таблицы созданы или уже были)")
    return conn, cursor

# Функции для таймеров
def save_active_timer(user_id: int, subject: str, start_time: datetime):
    try:
        db_cursor.execute("""
            INSERT OR REPLACE INTO active_timers (user_id, subject, start_time, last_check_time, check_count)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, subject, start_time, datetime.now(), 0))
        db_conn.commit()
    except Exception as e:
        print(f"Ошибка: {e}")

def remove_active_timer(user_id: int):
    try:
        db_cursor.execute("DELETE FROM active_timers WHERE user_id = ?", (user_id,))
        db_conn.commit()
    except Exception as e:
        print(f"Ошибка: {e}")

def get_active_timers():
    try:
        db_cursor.execute("""
            SELECT at.*, u.full_name, u.class
            FROM active_timers at
            JOIN users u ON at.user_id = u.user_id
        """)
        return db_cursor.fetchall()
    except Exception as e:
        print(f"Ошибка: {e}")
        return []

def update_timer_check(user_id: int):
    try:
        db_cursor.execute("""
            UPDATE active_timers
            SET last_check_time = ?, check_count = check_count + 1
            WHERE user_id = ?
        """, (datetime.now(), user_id))
        db_conn.commit()
    except Exception as e:
        print(f"Ошибка: {e}")

# Функция отправки напоминаний
async def send_reminder_to_all(app: Application):
    try:
        db_cursor.execute("SELECT user_id, full_name FROM users")
        users = db_cursor.fetchall()

        if not users:
            return 0, "❌ Нет пользователей в базе"

        message = (
            "📢 ВАЖНОЕ НАПОМИНАНИЕ!\n\n"
            "Пожалуйста, не забывайте пользоваться ботом - это очень важно для учёта времени!\n\n"
            "📚 Сделайте домашнее задание и отметьте его в боте.\n"
            "Нажмите /start чтобы начать.\n\n"
            "Спасибо за использование! 🙏"
        )

        sent_count = 0
        for user_id, full_name in users:
            try:
                await app.bot.send_message(chat_id=user_id, text=message)
                sent_count += 1
                print(f"✅ Отправлено {full_name}")
                await asyncio.sleep(0.3)
            except Exception as e:
                print(f"❌ Ошибка для {user_id}: {e}")

        return sent_count, f"✅ Отправлено: {sent_count} из {len(users)}"

    except Exception as e:
        print(f"❌ Ошибка в рассылке: {e}")
        return 0, f"❌ Ошибка: {e}"

# Функция проверки долгих заданий
async def check_long_tasks(app: Application):
    try:
        active_timers = get_active_timers()

        for timer in active_timers:
            user_id, subject, start_time, last_check, check_count, full_name, user_class = timer

            if isinstance(start_time, str):
                start_time = datetime.fromisoformat(start_time)

            duration_minutes = (datetime.now() - start_time).total_seconds() / 60

            if duration_minutes > LONG_TASK_THRESHOLD and check_count < 3:
                if isinstance(last_check, str):
                    last_check = datetime.fromisoformat(last_check)

                minutes_since_last = (datetime.now() - last_check).total_seconds() / 60

                if minutes_since_last > 30:
                    update_timer_check(user_id)

                    try:
                        keyboard = [
                            ["✅ Да, еще делаю"],
                            ["❌ Нет, уже закончил"]
                        ]
                        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

                        message = (
                            f"⏰ Вы уже {int(duration_minutes)} минут делаете {subject}!\n\n"
                            f"Вы еще делаете это задание?"
                        )

                        await app.bot.send_message(
                            chat_id=user_id,
                            text=message,
                            reply_markup=reply_markup
                        )
                    except Exception as e:
                        print(f"Ошибка: {e}")

    except Exception as e:
        print(f"Ошибка: {e}")

# Функция создания Excel
def create_excel_for_admin():
    try:
        db_cursor.execute("""
            SELECT
                u.class,
                u.full_name,
                h.subject,
                h.duration_seconds,
                h.start_time,
                h.end_time,
                h.date,
                h.created_at
            FROM homework_sessions h
            JOIN users u ON h.user_id = u.user_id
            ORDER BY h.created_at DESC
        """)

        data = db_cursor.fetchall()

        if not data:
            return None, "❌ Нет данных"

        formatted_data = []
        for row in data:
            class_name, full_name, subject, duration_seconds, start_time, end_time, date, created_at = row
            time_range = f"{start_time}-{end_time}"

            if duration_seconds < 60:
                duration_formatted = f"{duration_seconds} сек"
            elif duration_seconds % 60 == 0:
                minutes = duration_seconds // 60
                duration_formatted = f"{minutes} мин"
            else:
                minutes = duration_seconds // 60
                seconds = duration_seconds % 60
                duration_formatted = f"{minutes} мин {seconds} сек"

            formatted_data.append([
                class_name,
                full_name,
                subject,
                duration_formatted,
                time_range,
                date
            ])

        df = pd.DataFrame(formatted_data, columns=[
            'Класс', 'Ученик', 'Предмет', 'Время', 'Начало-Конец', 'Дата'
        ])

        excel_file = 'homework_data.xlsx'
        df.to_excel(excel_file, index=False)

        db_cursor.execute("SELECT COUNT(*) FROM users")
        total_users = db_cursor.fetchone()[0]

        db_cursor.execute("SELECT COUNT(*) FROM homework_sessions")
        total_sessions = db_cursor.fetchone()[0]

        caption = f"📊 Всего записей: {total_sessions}\n👥 Учеников: {total_users}"

        return excel_file, caption

    except Exception as e:
        print(f"Ошибка: {e}")
        return None, str(e)

# Функция проверки админа
def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

# Основные функции бота
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    db_cursor.execute("SELECT * FROM users WHERE user_id = ?", (user.id,))
    existing = db_cursor.fetchone()

    if existing:
        await update.message.reply_text(
            f"👋 С возвращением, {existing[3]}!\n"
            f"Твой класс: {existing[4]}"
        )
        await show_main_menu(update, user.id)
    else:
        await update.message.reply_text(
            f"👋 Привет, {user.full_name}!\n\n"
            "Я бот для учёта времени на домашние задания.\n\n"
            "📝 Для регистрации напиши свою фамилию и имя:\n"
            "(Например: Иванов Иван)",
            reply_markup=ReplyKeyboardRemove()
        )
        context.user_data['step'] = 'name'

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text

    step = context.user_data.get('step', '')

    # Обработка ответов на долгие задания
    if text in ["✅ Да, еще делаю", "❌ Нет, уже закончил"]:
        await handle_long_task_response(update, context, user.id, text)
        return

    if step == 'name':
        if len(text.split()) < 2:
            await update.message.reply_text("Пожалуйста, напиши фамилию и имя через пробел.")
            return

        context.user_data['name'] = text
        context.user_data['step'] = 'class'

        keyboard = [
            ["7А", "7Б", "7В"],
            ["8А", "8Б", "8В"],
            ["9А", "9Б", "9В"],
            ["10(гуманитарный)", "10(информационно-технологический)"],
            ["11А"]
        ]

        await update.message.reply_text(
            f"✅ Принято: {text}\n\n"
            "Теперь выбери свой класс:",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        )

    elif step == 'class':
        valid_classes = [
            "7А", "7Б", "7В", "8А", "8Б", "8В", "9А", "9Б", "9В",
            "10(гуманитарный)", "10(информационно-технологический)", "11А"
        ]

        if text not in valid_classes:
            await update.message.reply_text("Пожалуйста, выбери класс из предложенных вариантов.")
            return

        name = context.user_data['name']

        try:
            db_cursor.execute(
                "INSERT INTO users (user_id, username, full_name, class) VALUES (?, ?, ?, ?)",
                (user.id, user.username, name, text)
            )
            db_conn.commit()

            context.user_data.clear()

            await update.message.reply_text(
                f"🎉 Регистрация завершена!\n\n"
                f"📋 Твои данные:\n"
                f"• ФИО: {name}\n"
                f"• Класс: {text}\n\n"
                f"⏰ Теперь ты будешь получать напоминания:\n"
                f"• в {REMINDER_TIMES[0]}\n"
                f"• в {REMINDER_TIMES[1]}\n"
                f"• в {REMINDER_TIMES[2]}"
            )

            await show_main_menu(update, user.id)

        except Exception as e:
            await update.message.reply_text(f"Ошибка при сохранении: {e}")

    elif text == "📚 Начать задание":
        await select_subject(update, context, user.id)

    elif text in SUBJECTS:
        if 'current_subject' in context.user_data:
            await finish_homework(update, context, user.id, auto_complete=True)
        await start_homework(update, context, text, user.id)

    elif text == "⏹️ Завершить":
        await finish_homework(update, context, user.id)

    elif text == "🏠 Главное меню":
        await show_main_menu(update, user.id)

    elif text == "📊 Моя статистика":
        await show_user_stats(update, user.id)

    elif text == "📢 Отправить напоминание всем" and is_admin(user.id):
        status_msg = await update.message.reply_text("🔄 Отправляю напоминания...")
        sent, result = await send_reminder_to_all(context.application)
        await status_msg.edit_text(f"✅ {result}")

    elif text == "📊 Получить Excel" and is_admin(user.id):
        await send_excel_to_admin(update, user.id)

    elif text == "🔔 Проверить долгие задания" and is_admin(user.id):
        await check_long_tasks(context.application)
        await update.message.reply_text("✅ Проверка выполнена!")

    else:
        db_cursor.execute("SELECT * FROM users WHERE user_id = ?", (user.id,))
        user_data = db_cursor.fetchone()

        if user_data:
            await show_main_menu(update, user.id)
        else:
            await update.message.reply_text(
                "Ты еще не зарегистрирован. Напиши /start чтобы начать."
            )

async def handle_long_task_response(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, response: str):
    try:
        db_cursor.execute("SELECT * FROM active_timers WHERE user_id = ?", (user_id,))
        timer = db_cursor.fetchone()

        if not timer:
            await update.message.reply_text("У тебя нет активных заданий.")
            await show_main_menu(update, user_id)
            return

        subject = timer[1]
        start_time = timer[2]

        if response == "✅ Да, еще делаю":
            update_timer_check(user_id)
            await update.message.reply_text(
                f"✅ Хорошо, продолжаем!",
                reply_markup=ReplyKeyboardMarkup([["⏹️ Завершить"]], resize_keyboard=True)
            )
        else:
            if isinstance(start_time, str):
                start_time = datetime.fromisoformat(start_time)

            context.user_data['current_subject'] = subject
            context.user_data['start_datetime'] = start_time
            await finish_homework(update, context, user_id)

    except Exception as e:
        print(f"Ошибка: {e}")

async def show_main_menu(update: Update, user_id: int):
    if is_admin(user_id):
        keyboard = [
            ["📚 Начать задание"],
            ["📊 Моя статистика"],
            ["📢 Отправить напоминание всем"],
            ["📊 Получить Excel", "🔔 Проверить долгие задания"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            "👑 АДМИН ПАНЕЛЬ\nВыбери действие:",
            reply_markup=reply_markup
        )
    else:
        keyboard = [
            ["📚 Начать задание"],
            ["📊 Моя статистика"],
            ["🏠 Главное меню"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            "Выбери действие:",
            reply_markup=reply_markup
        )

async def select_subject(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    keyboard = []
    for i in range(0, len(SUBJECTS), 2):
        row = SUBJECTS[i:i+2]
        keyboard.append(row)

    keyboard.append(["🏠 Главное меню"])

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

    await update.message.reply_text(
        "📚 Выбери предмет:",
        reply_markup=reply_markup
    )

async def start_homework(update: Update, context: ContextTypes.DEFAULT_TYPE, subject: str, user_id: int):
    now = datetime.now(MOSCOW_TZ)

    context.user_data['current_subject'] = subject
    context.user_data['start_datetime'] = now

    save_active_timer(user_id, subject, now)

    await update.message.reply_text(
        f"✅ Начато: {subject}\n"
        f"🕐 {now.strftime('%H:%M:%S')}\n\n"
        f"Нажми 'Завершить' когда закончишь",
        reply_markup=ReplyKeyboardMarkup([["⏹️ Завершить"]], resize_keyboard=True)
    )

async def finish_homework(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, auto_complete=False):
    if 'current_subject' not in context.user_data:
        if not auto_complete:
            await update.message.reply_text("Нет активного задания")
            await show_main_menu(update, user_id)
        return

    subject = context.user_data['current_subject']
    start = context.user_data['start_datetime']
    end = datetime.now(MOSCOW_TZ)

    seconds = int((end - start).total_seconds())
    minutes = math.ceil(seconds / 60)

    try:
        db_cursor.execute("""
            INSERT INTO homework_sessions
            (user_id, subject, date, start_time, end_time, duration_seconds, duration_minutes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, subject, start.strftime("%d.%m.%Y"),
              start.strftime("%H:%M:%S"), end.strftime("%H:%M:%S"), seconds, minutes))
        db_conn.commit()

        remove_active_timer(user_id)
        context.user_data.clear()

        if not auto_complete:
            if seconds < 60:
                time_text = f"{seconds} сек"
            else:
                m = seconds // 60
                s = seconds % 60
                time_text = f"{m} мин {s} сек" if s > 0 else f"{m} мин"

            await update.message.reply_text(
                f"✅ Завершено!\n"
                f"📚 {subject}\n"
                f"⏱️ {time_text}\n"
                f"🕐 {start.strftime('%H:%M:%S')} - {end.strftime('%H:%M:%S')}"
            )

            await select_subject(update, context, user_id)

    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def show_user_stats(update: Update, user_id: int):
    try:
        db_cursor.execute("SELECT full_name, class FROM users WHERE user_id = ?", (user_id,))
        user = db_cursor.fetchone()

        if not user:
            await update.message.reply_text("Сначала зарегистрируйся")
            return

        db_cursor.execute("""
            SELECT COUNT(*), SUM(duration_seconds), AVG(duration_seconds)
            FROM homework_sessions WHERE user_id = ?
        """, (user_id,))

        stats = db_cursor.fetchone()

        if not stats or stats[0] == 0:
            await update.message.reply_text("Пока нет заданий")
            return

        count, total_sec, avg_sec = stats
        total_hours = total_sec / 3600
        avg_min = avg_sec / 60

        await update.message.reply_text(
            f"📊 Статистика для {user[0]} ({user[1]})\n\n"
            f"📝 Заданий: {count}\n"
            f"⏱️ Всего: {total_hours:.1f} ч\n"
            f"📏 Среднее: {avg_min:.0f} мин"
        )

    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def send_excel_to_admin(update: Update, user_id: int):
    try:
        msg = await update.message.reply_text("🔄 Создаю Excel...")

        file, caption = create_excel_for_admin()

        if file and os.path.exists(file):
            with open(file, 'rb') as f:
                await msg.delete()
                await update.message.reply_document(document=f, caption=caption)
        else:
            await msg.edit_text("❌ Нет данных")

    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

# Автоматическая проверка времени
async def auto_reminder_loop(app: Application):
    while True:
        try:
            current_time = datetime.now(MOSCOW_TZ)
            current_hour = current_time.strftime("%H:%M")

            if current_hour in REMINDER_TIMES:
                print(f"⏰ Автоматическое напоминание в {current_hour}")
                await send_reminder_to_all(app)

            if current_time.minute % 15 == 0:
                await check_long_tasks(app)

            await asyncio.sleep(60)

        except Exception as e:
            print(f"Ошибка: {e}")
            await asyncio.sleep(60)

# Команда помощи
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if is_admin(user.id):
        await update.message.reply_text(
            "👑 АДМИН КОМАНДЫ:\n\n"
            "📢 Отправить напоминание всем - ручная рассылка\n"
            "📊 Получить Excel - скачать все данные\n"
            "🔔 Проверить долгие задания - ручная проверка\n\n"
            f"⏰ Автонапоминания: {', '.join(REMINDER_TIMES)}"
        )
    else:
        await update.message.reply_text(
            "📚 Домашний Таймер\n\n"
            "📚 Начать задание - запустить таймер\n"
            "📊 Моя статистика - результаты\n\n"
            f"⏰ Напоминания: {', '.join(REMINDER_TIMES)}"
        )

# Запуск бота
def main():
    print("=" * 60)
    print("🤖 БОТ ДЛЯ ХОСТИНГА")
    print("=" * 60)
    print(f"⏰ Автонапоминания: {REMINDER_TIMES}")
    print(f"👑 Админ ID: {ADMIN_ID}")
    print("=" * 60)

    db_cursor.execute("SELECT COUNT(*) FROM users")
    users_count = db_cursor.fetchone()[0]
    print(f"👥 Пользователей в базе: {users_count}")
    print("=" * 60)

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Запускаем автонапоминания
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(auto_reminder_loop(app))

    print("\n✅ БОТ ЗАПУЩЕН!")
    print("📱 Открой Telegram и напиши /start")
    print("=" * 60)

    app.run_polling()

if __name__ == "__main__":
    main()
