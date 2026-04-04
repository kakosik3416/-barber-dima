import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, filters
import requests

# Настройки
TELEGRAM_TOKEN = "8693807260:AAGDZ3121GHyRtnrwJALSHnBrotBrQQTAFc"
SUPABASE_URL = "https://uqenkackpzlslyjrmwkw.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVxZW5rYWNrcHpsc2x5anJtd2t3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzUzMTMzMTAsImV4cCI6MjA5MDg4OTMxMH0.yji4nZOzVvlc64zaogcMrpdsWwqWpkhHlKb29fx6rWs"
ADMIN_CHAT_ID = "689626594"

# Состояния для диалога
ASK_NAME, ASK_PHONE, ASK_SERVICE, ASK_DATE, ASK_TIME = range(5)

# Заголовки для Supabase
headers = {
    "apikey": SUPABASE_ANON_KEY,
    "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
    "Content-Type": "application/json"
}

# Включим логирование
logging.basicConfig(level=logging.INFO)

# Хранилище временных данных (в реальности лучше использовать базу, но для старта сойдёт)
user_data = {}

# Функция отправки уведомления админу
async def notify_admin(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": ADMIN_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        logging.error(f"Не удалось отправить уведомление админу: {e}")

# Команда /start
async def start(update, context):
    await update.message.reply_text(
        "✂️ Добро пожаловать в барбершоп!\n\n"
        "/record – записаться на стрижку\n"
        "/my_records – мои записи"
    )

# Начало диалога записи
async def record_start(update, context):
    user_id = update.effective_user.id
    user_data[user_id] = {}
    await update.message.reply_text("Как вас зовут? (имя и фамилия)")
    return ASK_NAME

async def ask_name(update, context):
    user_id = update.effective_user.id
    user_data[user_id]['name'] = update.message.text
    await update.message.reply_text("Ваш номер телефона (для связи):")
    return ASK_PHONE

async def ask_phone(update, context):
    user_id = update.effective_user.id
    user_data[user_id]['phone'] = update.message.text
    await update.message.reply_text("Выберите услугу:\n1 - Мужская стрижка (200₽)\n2 - Комплекс VIP (250₽)")
    return ASK_SERVICE

async def ask_service(update, context):
    user_id = update.effective_user.id
    service_map = {"1": "Мужская стрижка (200 ₽)", "2": "Комплекс VIP (250 ₽)"}
    user_data[user_id]['service'] = service_map.get(update.message.text, update.message.text)
    await update.message.reply_text("Введите желаемую дату в формате ГГГГ-ММ-ДД (например, 2026-04-10):")
    return ASK_DATE

async def ask_date(update, context):
    user_id = update.effective_user.id
    user_data[user_id]['date'] = update.message.text
    await update.message.reply_text("Введите время (например, 20:00):")
    return ASK_TIME

async def ask_time(update, context):
    user_id = update.effective_user.id
    user_data[user_id]['time'] = update.message.text

    # Сохраняем в Supabase
    record = {
        "name": user_data[user_id]['name'],
        "surname": "",
        "user_group": "—",
        "phone": user_data[user_id]['phone'],
        "service": user_data[user_id]['service'],
        "barber": "Дмитрий The Old school",
        "date": user_data[user_id]['date'],
        "time": user_data[user_id]['time'],
        "comment": "Запись через Telegram",
        "user_telegram_id": str(user_id)
    }
    response = requests.post(f"{SUPABASE_URL}/rest/v1/appointments", headers=headers, json=record)
    if response.status_code == 201:
        await update.message.reply_text("✅ Вы успешно записаны!")
        await notify_admin(
            f"✂️ <b>Новая запись через бота!</b>\n"
            f"Клиент: {record['name']}\nТелефон: {record['phone']}\n"
            f"Услуга: {record['service']}\nДата: {record['date']} {record['time']}"
        )
    else:
        await update.message.reply_text("❌ Ошибка при записи. Попробуйте позже.")
        logging.error(f"Supabase error: {response.text}")

    # Очищаем данные пользователя
    user_data.pop(user_id, None)
    return ConversationHandler.END

# Отмена диалога
async def cancel(update, context):
    user_id = update.effective_user.id
    user_data.pop(user_id, None)
    await update.message.reply_text("Запись отменена.")
    return ConversationHandler.END

# Показать мои записи
async def my_records(update, context):
    user_id = str(update.effective_user.id)
    response = requests.get(
        f"{SUPABASE_URL}/rest/v1/appointments?user_telegram_id=eq.{user_id}",
        headers=headers
    )
    if response.status_code != 200:
        await update.message.reply_text("Ошибка получения записей.")
        return
    records = response.json()
    if not records:
        await update.message.reply_text("У вас нет активных записей.")
        return
    for rec in records:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Отменить", callback_data=f"cancel_{rec['id']}")]
        ])
        await update.message.reply_text(
            f"📅 {rec['date']} {rec['time']}\n✂️ {rec['service']}\n👤 Мастер: {rec.get('barber', 'Дмитрий')}",
            reply_markup=keyboard
        )

# Обработка нажатий на кнопку "Отменить"
async def cancel_callback(update, context):
    query = update.callback_query
    await query.answer()
    record_id = query.data.split('_')[1]
    user_id = str(query.from_user.id)
    # Удаляем запись
    response = requests.delete(
        f"{SUPABASE_URL}/rest/v1/appointments?id=eq.{record_id}&user_telegram_id=eq.{user_id}",
        headers=headers
    )
    if response.status_code == 200:
        await query.edit_message_text("✅ Запись отменена.")
        await notify_admin(f"❌ <b>Отмена записи</b>\nID: {record_id}")
    else:
        await query.edit_message_text("❌ Ошибка при отмене.")

def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # ConversationHandler для записи
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("record", record_start)],
        states={
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_name)],
            ASK_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_phone)],
            ASK_SERVICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_service)],
            ASK_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_date)],
            ASK_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_time)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("my_records", my_records))
    application.add_handler(CallbackQueryHandler(cancel_callback, pattern="^cancel_"))

    # Запускаем бота (вебхук для Railway, или поллинг для локального теста)
    PORT = int(os.environ.get("PORT", "8443"))
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TELEGRAM_TOKEN,
        webhook_url=f"https://ваш-проект.railway.app/{TELEGRAM_TOKEN}"
    )

if __name__ == "__main__":
    main()