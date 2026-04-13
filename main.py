import asyncio
import logging
import random
import json
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, filters
import requests

# ---------- НАСТРОЙКИ ----------
TOKEN = "8693807260:AAGDZ3121GHyRtnrwJALSHnBrotBrQQTAFc"
SUPABASE_URL = "https://uqenkackpzlslyjrmwkw.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVxZW5rYWNrcHpsc2x5anJtd2t3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzUzMTMzMTAsImV4cCI6MjA5MDg4OTMxMH0.yji4nZOzVvlc64zaogcMrpdsWwqWpkhHlKb29fx6rWs"
ADMIN_CHAT_ID = "689626594"  # ваш Telegram ID
ADMIN_PASSWORD = "admin123"   # пароль для входа в админ-режим

headers = {
    "apikey": SUPABASE_ANON_KEY,
    "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
    "Content-Type": "application/json"
}
logging.basicConfig(level=logging.INFO)

# Состояния диалога
ASK_NAME, ASK_PHONE, ASK_SERVICE, ASK_DATE, ASK_TIME, CONFIRM = range(6)
user_data = {}

SERVICES = {
    "1": "✂️ Мужская стрижка (200 ₽)",
    "2": "💎 Комплекс VIP (250 ₽)"
}
ALL_TIMES = ["20:00", "20:30", "21:00", "21:30", "22:00", "23:00", "23:30", "00:00"]

# Случайные факты о барбершопе
BARBER_FACTS = [
    "💈 Первые парикмахеры появились в Древнем Египте около 5000 лет назад.",
    "✂️ В средневековой Европе парикмахеры также выполняли операции и удаляли зубы.",
    "💈 Знаменитая красно-синяя вывеска парикмахерской символизирует кровь и вены (исторически).",
    "✂️ Мужская стрижка может сделать лицо визуально стройнее и моложе.",
    "💈 В Японии парикмахеров называют «токуя» и они проходят 3-летнее обучение.",
    "✂️ Самая дорогая стрижка в мире стоила около 16 000 долларов.",
    "💈 Регулярная стрижка помогает сохранить здоровье волос и кожи головы.",
    "✂️ В Древнем Риме парикмахер был важной фигурой – он не только стриг, но и брил, и делал массаж.",
    "💈 Первые электрические машинки для стрижки появились в 1920-х годах.",
    "✂️ В среднем мужчина посещает барбера 10–12 раз в год."
]

# Админ-сессии (храним ID пользователей, которые вошли)
admin_sessions = set()

# ---------- ФУНКЦИИ НАПОМИНАНИЙ ----------
async def send_reminder(chat_id, name, date, time, service):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    text = (
        f"📅 <b>Напоминание о записи!</b>\n\n"
        f"👤 {name}, вы записаны на <b>{date}</b> в <b>{time}</b>\n"
        f"✂️ Услуга: {service}\n\n"
        f"Ждём вас в нашем барбершопе! Если нужно отменить или перенести запись – нажмите «📋 Мои записи»."
    )
    try:
        requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})
        logging.info(f"Напоминание отправлено пользователю {chat_id}")
    except Exception as e:
        logging.error(f"Ошибка отправки напоминания: {e}")

async def check_and_send_reminders():
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/appointments?date=eq.{tomorrow}&reminder_sent=eq.false&select=*",
        headers=headers
    )
    if resp.status_code != 200:
        logging.error(f"Ошибка получения записей для напоминаний: {resp.status_code}")
        return
    records = resp.json()
    for rec in records:
        user_id = rec.get('user_telegram_id')
        if user_id:
            await send_reminder(user_id, rec['name'], rec['date'], rec['time'], rec['service'])
            requests.patch(
                f"{SUPABASE_URL}/rest/v1/appointments?id=eq.{rec['id']}",
                headers=headers,
                json={"reminder_sent": True}
            )
            await asyncio.sleep(1)

async def reminder_loop(application: Application):
    while True:
        now = datetime.now()
        target = now.replace(hour=10, minute=0, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)
        sleep_seconds = (target - now).total_seconds()
        logging.info(f"Следующая проверка напоминаний через {sleep_seconds/3600:.1f} часов")
        await asyncio.sleep(sleep_seconds)
        await check_and_send_reminders()

# ---------- АДМИНСКИЕ ФУНКЦИИ ----------
async def admin_login(update: Update, context):
    if update.effective_user.id != int(ADMIN_CHAT_ID):
        await update.message.reply_text("⛔ У вас нет доступа к этой команде.")
        return
    await update.message.reply_text("🔐 Введите пароль для входа в админ-режим:")
    return 1

async def admin_password(update: Update, context):
    if update.message.text == ADMIN_PASSWORD:
        admin_sessions.add(update.effective_user.id)
        await update.message.reply_text(
            "✅ Доступ предоставлен! Теперь вам доступна кнопка «📋 Все записи» в меню.\n"
            "Используйте её для просмотра всех записей.",
            reply_markup=get_main_menu(is_admin=True)
        )
    else:
        await update.message.reply_text("❌ Неверный пароль. Доступ не предоставлен.")
    return ConversationHandler.END

async def all_records(update: Update, context):
    user_id = update.effective_user.id
    if user_id not in admin_sessions:
        await update.message.reply_text("⛔ У вас нет доступа. Используйте /admin для входа.")
        return
    resp = requests.get(f"{SUPABASE_URL}/rest/v1/appointments?order=date.asc,time.asc", headers=headers)
    if resp.status_code != 200:
        await update.message.reply_text("❌ Ошибка получения записей.")
        return
    records = resp.json()
    if not records:
        await update.message.reply_text("📭 Нет записей.")
        return
    # Группировка по дате
    current_date = None
    message_lines = []
    for rec in records:
        if rec['date'] != current_date:
            current_date = rec['date']
            message_lines.append(f"\n📅 <b>{current_date}</b>")
        message_lines.append(f"   🕒 {rec['time']} – {rec['name']} ({rec['service']})")
    full_message = "🗓 <b>Все записи:</b>\n" + "\n".join(message_lines)
    # Отправляем частями, если длинное
    for i in range(0, len(full_message), 4000):
        await update.message.reply_text(full_message[i:i+4000], parse_mode="HTML")
    # Кнопка экспорта JSON
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Экспорт в JSON", callback_data="export_json")]
    ])
    await update.message.reply_text("Нажмите кнопку, чтобы выгрузить все записи в JSON.", reply_markup=keyboard)

async def export_json_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if user_id not in admin_sessions:
        await query.edit_message_text("⛔ Нет доступа.")
        return
    resp = requests.get(f"{SUPABASE_URL}/rest/v1/appointments?order=date.asc,time.asc", headers=headers)
    if resp.status_code != 200:
        await query.edit_message_text("Ошибка получения данных.")
        return
    data = resp.json()
    json_str = json.dumps(data, ensure_ascii=False, indent=2)
    await query.message.reply_document(
        document=('appointments.json', json_str.encode('utf-8')),
        caption="📊 Все записи в формате JSON"
    )

# ---------- ОСНОВНОЕ МЕНЮ (динамическое) ----------
def get_main_menu(is_admin=False):
    buttons = [
        [KeyboardButton("✂️ Записаться"), KeyboardButton("📋 Мои записи")],
        [KeyboardButton("🎲 Случайный факт"), KeyboardButton("🌐 Наш сайт")],
        [KeyboardButton("❓ Помощь")]
    ]
    if is_admin:
        buttons[1].insert(1, KeyboardButton("📋 Все записи"))
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

# ---------- ОБЩИЕ ФУНКЦИИ ----------
async def notify_admin(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": ADMIN_CHAT_ID, "text": message, "parse_mode": "HTML"})
    except Exception as e:
        logging.error(f"Не удалось отправить уведомление: {e}")

def get_booked_times(date):
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/appointments?date=eq.{date}&select=time",
        headers=headers
    )
    if resp.status_code != 200:
        return []
    return [rec['time'] for rec in resp.json()]

async def start(update: Update, context):
    user_id = update.effective_user.id
    is_admin = user_id in admin_sessions
    await update.message.reply_text(
        "✨ <b>Добро пожаловать в наш барбершоп!</b> ✨\n\n"
        "Я помогу вам записаться на стрижку, посмотреть ваши записи и отменить их.\n\n"
        "Используйте кнопки меню ниже 👇",
        parse_mode="HTML",
        reply_markup=get_main_menu(is_admin)
    )

async def handle_main_menu(update: Update, context):
    text = update.message.text
    user_id = update.effective_user.id
    is_admin = user_id in admin_sessions

    if text == "✂️ Записаться":
        await record_start(update, context)
    elif text == "📋 Мои записи":
        await my_records(update, context)
    elif text == "📋 Все записи" and is_admin:
        await all_records(update, context)
    elif text == "🎲 Случайный факт":
        fact = random.choice(BARBER_FACTS)
        await update.message.reply_text(fact)
    elif text == "🌐 Наш сайт":
        await update.message.reply_text(
            "🌐 <b>Наш сайт:</b>\nhttps://kakosik3416.github.io/-barber-dima/\n\n"
            "Здесь вы можете записаться онлайн, посмотреть все записи и управлять ими.\n"
            "Также вы можете войти в панель администратора (пароль: admin123).",
            parse_mode="HTML"
        )
    elif text == "❓ Помощь":
        await help_command(update, context)
    else:
        await update.message.reply_text("Пожалуйста, используйте кнопки меню.")

async def help_command(update: Update, context):
    await update.message.reply_text(
        "📌 <b>Как пользоваться ботом</b>\n\n"
        "• «✂️ Записаться» – запись на стрижку.\n"
        "• «📋 Мои записи» – ваши активные записи с возможностью отмены.\n"
        "• «🎲 Случайный факт» – интересный факт о барбершопе.\n"
        "• «🌐 Наш сайт» – ссылка на сайт.\n"
        "• «❓ Помощь» – эта справка.\n\n"
        "Если вы администратор, используйте /admin для входа – появится кнопка «📋 Все записи».",
        parse_mode="HTML"
    )

# ---------- ДИАЛОГ ЗАПИСИ ----------
async def record_start(update: Update, context):
    user_id = update.effective_user.id
    user_data[user_id] = {}
    await update.message.reply_text("👤 <b>Как вас зовут?</b> (имя и фамилия)", parse_mode="HTML")
    return ASK_NAME

async def ask_name(update: Update, context):
    user_id = update.effective_user.id
    user_data[user_id]['name'] = update.message.text
    await update.message.reply_text("📞 <b>Ваш номер телефона</b> (для связи)", parse_mode="HTML")
    return ASK_PHONE

async def ask_phone(update: Update, context):
    user_id = update.effective_user.id
    user_data[user_id]['phone'] = update.message.text
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(SERVICES["1"], callback_data="service_1")],
        [InlineKeyboardButton(SERVICES["2"], callback_data="service_2")]
    ])
    await update.message.reply_text("💈 <b>Выберите услугу:</b>", parse_mode="HTML", reply_markup=keyboard)
    return ASK_SERVICE

async def service_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    service_code = query.data.split('_')[1]
    user_data[user_id]['service'] = SERVICES[service_code]
    await show_date_buttons(query, user_id)
    return ASK_DATE

async def show_date_buttons(query, user_id):
    today = datetime.now()
    buttons = []
    for i in range(1, 8):
        date = (today + timedelta(days=i)).strftime("%Y-%m-%d")
        dt = datetime.strptime(date, "%Y-%m-%d")
        weekday = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"][dt.weekday()]
        label = f"{dt.day} {['янв','фев','мар','апр','май','июн','июл','авг','сен','окт','ноя','дек'][dt.month-1]} ({weekday})"
        buttons.append([InlineKeyboardButton(label, callback_data=f"date_{date}")])
    keyboard = InlineKeyboardMarkup(buttons)
    await query.edit_message_text("📅 <b>Выберите дату:</b>", parse_mode="HTML", reply_markup=keyboard)

async def date_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    date = query.data.split('_')[1]
    user_data[user_id]['date'] = date
    booked = get_booked_times(date)
    free_slots = [t for t in ALL_TIMES if t not in booked]
    if not free_slots:
        await query.edit_message_text("😞 На эту дату нет свободного времени. Выберите другую дату.")
        await show_date_buttons(query, user_id)
        return
    buttons = [[InlineKeyboardButton(t, callback_data=f"time_{t}")] for t in free_slots]
    keyboard = InlineKeyboardMarkup(buttons)
    await query.edit_message_text(f"🕒 <b>Выберите время</b> на {date}:", parse_mode="HTML", reply_markup=keyboard)
    return ASK_TIME

async def time_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    time_slot = query.data.split('_')[1]
    user_data[user_id]['time'] = time_slot
    data = user_data[user_id]
    text = (
        f"📝 <b>Проверьте данные:</b>\n\n"
        f"👤 Имя: {data['name']}\n"
        f"📞 Телефон: {data['phone']}\n"
        f"💈 Услуга: {data['service']}\n"
        f"📅 Дата: {data['date']}\n"
        f"🕒 Время: {data['time']}\n\n"
        f"✅ Всё верно? Запись будет сохранена."
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Да, записать", callback_data="confirm_yes")],
        [InlineKeyboardButton("❌ Нет, отменить", callback_data="confirm_no")]
    ])
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)
    return CONFIRM

async def confirm_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = user_data.get(user_id)
    if not data:
        await query.edit_message_text("❌ Ошибка: данные не найдены. Начните запись заново /record")
        return ConversationHandler.END

    if query.data == "confirm_yes":
        record = {
            "name": data['name'],
            "surname": "",
            "user_group": "—",
            "phone": data['phone'],
            "service": data['service'],
            "barber": "Дмитрий The Old school",
            "date": data['date'],
            "time": data['time'],
            "comment": "Запись через Telegram",
            "user_telegram_id": str(user_id),
            "reminder_sent": False
        }
        resp = requests.post(f"{SUPABASE_URL}/rest/v1/appointments", headers=headers, json=record)
        if resp.status_code == 201:
            await query.message.delete()
            await update.effective_chat.send_message(
                f"✅ <b>Вы успешно записаны!</b>\n\n"
                f"✂️ {data['service']}\n"
                f"📅 {data['date']} в {data['time']}\n"
                f"👤 Мастер: Дмитрий\n\n"
                f"🌐 <a href='https://kakosik3416.github.io/-barber-dima/'>Наш сайт</a> – здесь можно посмотреть все записи.\n\n"
                f"Если понадобится отменить запись – нажмите «📋 Мои записи».",
                parse_mode="HTML",
                reply_markup=get_main_menu(user_id in admin_sessions)
            )
            await notify_admin(
                f"✂️ <b>Новая запись через бота!</b>\n"
                f"Клиент: {data['name']}\nТелефон: {data['phone']}\n"
                f"Услуга: {data['service']}\nДата: {data['date']} {data['time']}"
            )
        else:
            error_text = resp.text[:200]
            await query.message.delete()
            await update.effective_chat.send_message(
                f"❌ <b>Ошибка при записи.</b>\n\n"
                f"Код ошибки: {resp.status_code}\n"
                f"<code>{error_text}</code>\n\n"
                f"Пожалуйста, попробуйте позже или свяжитесь с администратором.",
                parse_mode="HTML",
                reply_markup=get_main_menu(user_id in admin_sessions)
            )
            logging.error(f"Supabase error: {resp.status_code} {resp.text}")
    else:
        await query.edit_message_text("❌ Запись отменена.", reply_markup=get_main_menu(user_id in admin_sessions))

    user_data.pop(user_id, None)
    return ConversationHandler.END

async def cancel(update: Update, context):
    user_id = update.effective_user.id
    user_data.pop(user_id, None)
    await update.message.reply_text("❌ Запись отменена.", reply_markup=get_main_menu(user_id in admin_sessions))
    return ConversationHandler.END

async def my_records(update: Update, context):
    user_id = str(update.effective_user.id)
    resp = requests.get(f"{SUPABASE_URL}/rest/v1/appointments?user_telegram_id=eq.{user_id}", headers=headers)
    if resp.status_code != 200:
        await update.message.reply_text("Ошибка получения записей.")
        return
    records = resp.json()
    if not records:
        await update.message.reply_text("📭 У вас нет активных записей.\n\n🌐 <a href='https://kakosik3416.github.io/-barber-dima/'>Записаться можно на сайте</a>", parse_mode="HTML", reply_markup=get_main_menu(int(user_id) in admin_sessions))
        return
    for rec in records:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Отменить", callback_data=f"cancel_{rec['id']}")]
        ])
        await update.message.reply_text(
            f"📅 <b>{rec['date']}</b> в <b>{rec['time']}</b>\n"
            f"✂️ {rec['service']}\n"
            f"👤 Мастер: {rec.get('barber', 'Дмитрий')}",
            parse_mode="HTML",
            reply_markup=keyboard
        )

async def cancel_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    record_id = query.data.split('_')[1]
    user_id = str(query.from_user.id)
    resp = requests.delete(
        f"{SUPABASE_URL}/rest/v1/appointments?id=eq.{record_id}&user_telegram_id=eq.{user_id}",
        headers=headers
    )
    if resp.status_code == 200:
        await query.edit_message_text("✅ Запись отменена.", reply_markup=get_main_menu(int(user_id) in admin_sessions))
        await notify_admin(f"❌ <b>Отмена записи</b>\nID: {record_id}")
    else:
        await query.edit_message_text("❌ Ошибка при отмене.")

# ---------- ЗАПУСК ----------
def main():
    application = Application.builder().token(TOKEN).build()
    # Диалог записи
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("record", record_start),
            MessageHandler(filters.Text("✂️ Записаться"), record_start)
        ],
        states={
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_name)],
            ASK_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_phone)],
            ASK_SERVICE: [CallbackQueryHandler(service_callback, pattern="^service_")],
            ASK_DATE: [CallbackQueryHandler(date_callback, pattern="^date_")],
            ASK_TIME: [CallbackQueryHandler(time_callback, pattern="^time_")],
            CONFIRM: [CallbackQueryHandler(confirm_callback, pattern="^confirm_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    # Админ-диалог
    admin_conv = ConversationHandler(
        entry_points=[CommandHandler("admin", admin_login)],
        states={1: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_password)]},
        fallbacks=[]
    )
    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("my_records", my_records))
    application.add_handler(CommandHandler("all_records", all_records))
    application.add_handler(admin_conv)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_main_menu))
    application.add_handler(CallbackQueryHandler(cancel_callback, pattern="^cancel_"))
    application.add_handler(CallbackQueryHandler(export_json_callback, pattern="^export_json"))

    # Запуск напоминаний
    loop = asyncio.get_event_loop()
    loop.create_task(reminder_loop(application))

    application.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
