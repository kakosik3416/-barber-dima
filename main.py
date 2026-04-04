import asyncio
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, filters
import requests

# ---------- НАСТРОЙКИ ----------
TOKEN = "8693807260:AAGDZ3121GHyRtnrwJALSHnBrotBrQQTAFc"
SUPABASE_URL = "https://uqenkackpzlslyjrmwkw.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVxZW5rYWNrcHpsc2x5anJtd2t3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzUzMTMzMTAsImV4cCI6MjA5MDg4OTMxMH0.yji4nZOzVvlc64zaogcMrpdsWwqWpkhHlKb29fx6rWs"
ADMIN_CHAT_ID = "689626594"

headers = {
    "apikey": SUPABASE_ANON_KEY,
    "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
    "Content-Type": "application/json"
}
logging.basicConfig(level=logging.INFO)

# Состояния диалога
ASK_NAME, ASK_PHONE, ASK_SERVICE, ASK_DATE, ASK_TIME, CONFIRM = range(6)
user_data = {}

# Доступные услуги (кнопки)
SERVICES = {
    "1": "✂️ Мужская стрижка (200 ₽)",
    "2": "💎 Комплекс VIP (250 ₽)"
}
# Список всех возможных временных слотов
ALL_TIMES = ["20:00", "20:30", "21:00", "21:30", "22:00", "23:00", "23:30", "00:00"]

# Главное меню (ReplyKeyboard)
main_menu = ReplyKeyboardMarkup(
    [
        [KeyboardButton("✂️ Записаться"), KeyboardButton("📋 Мои записи")],
        [KeyboardButton("❓ Помощь")]
    ],
    resize_keyboard=True
)

async def notify_admin(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": ADMIN_CHAT_ID, "text": message, "parse_mode": "HTML"})
    except Exception as e:
        logging.error(f"Не удалось отправить уведомление: {e}")

# Получение занятых слотов на конкретную дату
def get_booked_times(date):
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/appointments?date=eq.{date}&select=time",
        headers=headers
    )
    if resp.status_code != 200:
        return []
    return [rec['time'] for rec in resp.json()]

async def start(update: Update, context):
    await update.message.reply_text(
        "✨ <b>Добро пожаловать в наш барбершоп!</b> ✨\n\n"
        "Я помогу вам записаться на стрижку, посмотреть ваши записи и отменить их.\n\n"
        "Используйте кнопки меню ниже 👇",
        parse_mode="HTML",
        reply_markup=main_menu
    )

# Обработка нажатий на главные кнопки
async def handle_main_menu(update: Update, context):
    text = update.message.text
    if text == "✂️ Записаться":
        await record_start(update, context)
    elif text == "📋 Мои записи":
        await my_records(update, context)
    elif text == "❓ Помощь":
        await help_command(update, context)
    else:
        await update.message.reply_text("Пожалуйста, используйте кнопки меню.")

async def help_command(update: Update, context):
    await update.message.reply_text(
        "📌 <b>Как пользоваться ботом</b>\n\n"
        "• Нажмите «✂️ Записаться» – бот задаст несколько вопросов.\n"
        "• «📋 Мои записи» – покажет ваши активные записи с возможностью отмены.\n"
        "• Если возникнут трудности, напишите администратору: @kakosik3416",
        parse_mode="HTML"
    )

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
    # Показываем кнопки выбора услуги
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
    # Показываем выбор даты на ближайшие 7 дней
    await show_date_buttons(query, user_id)
    return ASK_DATE

async def show_date_buttons(query, user_id):
    today = datetime.now()
    buttons = []
    for i in range(1, 8):  # следующие 7 дней
        date = (today + timedelta(days=i)).strftime("%Y-%m-%d")
        # Преобразуем дату в читаемый вид: "5 апреля (сб)"
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
    # Получаем занятые слоты на эту дату
    booked = get_booked_times(date)
    free_slots = [t for t in ALL_TIMES if t not in booked]
    if not free_slots:
        await query.edit_message_text("😞 На эту дату нет свободного времени. Выберите другую дату.")
        await show_date_buttons(query, user_id)
        return
    # Показываем кнопки со свободным временем
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
    # Показываем подтверждение
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
    if query.data == "confirm_yes":
        data = user_data.get(user_id)
        if not data:
            await query.edit_message_text("❌ Ошибка: данные не найдены. Начните запись заново /record")
            return ConversationHandler.END
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
            "user_telegram_id": str(user_id)
        }
        resp = requests.post(f"{SUPABASE_URL}/rest/v1/appointments", headers=headers, json=record)
        if resp.status_code == 201:
            await query.edit_message_text(
                f"✅ <b>Вы успешно записаны!</b>\n\n"
                f"✂️ {data['service']}\n"
                f"📅 {data['date']} в {data['time']}\n"
                f"👤 Мастер: Дмитрий\n\n"
                f"Если понадобится отменить запись – нажмите «📋 Мои записи».",
                parse_mode="HTML",
                reply_markup=main_menu
            )
            await notify_admin(
                f"✂️ <b>Новая запись через бота!</b>\n"
                f"Клиент: {data['name']}\nТелефон: {data['phone']}\n"
                f"Услуга: {data['service']}\nДата: {data['date']} {data['time']}"
            )
        else:
            await query.edit_message_text("❌ Ошибка при записи. Попробуйте позже.")
            logging.error(f"Supabase error: {resp.text}")
    else:
        await query.edit_message_text("❌ Запись отменена.", reply_markup=main_menu)
    user_data.pop(user_id, None)
    return ConversationHandler.END

async def cancel(update: Update, context):
    user_id = update.effective_user.id
    user_data.pop(user_id, None)
    await update.message.reply_text("❌ Запись отменена.", reply_markup=main_menu)
    return ConversationHandler.END

async def my_records(update: Update, context):
    user_id = str(update.effective_user.id)
    resp = requests.get(f"{SUPABASE_URL}/rest/v1/appointments?user_telegram_id=eq.{user_id}", headers=headers)
    if resp.status_code != 200:
        await update.message.reply_text("Ошибка получения записей.")
        return
    records = resp.json()
    if not records:
        await update.message.reply_text("📭 У вас нет активных записей.", reply_markup=main_menu)
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
        await query.edit_message_text("✅ Запись отменена.", reply_markup=main_menu)
        await notify_admin(f"❌ <b>Отмена записи</b>\nID: {record_id}")
    else:
        await query.edit_message_text("❌ Ошибка при отмене.")

def main():
    application = Application.builder().token(TOKEN).build()
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
    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("my_records", my_records))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_main_menu))
    application.add_handler(CallbackQueryHandler(cancel_callback, pattern="^cancel_"))
    application.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
