import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, filters
import requests

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

ASK_NAME, ASK_PHONE, ASK_SERVICE, ASK_DATE, ASK_TIME = range(5)
user_data = {}

async def notify_admin(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": ADMIN_CHAT_ID, "text": message, "parse_mode": "HTML"})
    except Exception as e:
        logging.error(f"Не удалось отправить уведомление: {e}")

async def start(update: Update, context):
    await update.message.reply_text(
        "✂️ Добро пожаловать в барбершоп!\n\n"
        "/record – записаться\n"
        "/my_records – мои записи"
    )

async def record_start(update: Update, context):
    user_id = update.effective_user.id
    user_data[user_id] = {}
    await update.message.reply_text("Как вас зовут? (имя и фамилия)")
    return ASK_NAME

async def ask_name(update: Update, context):
    user_id = update.effective_user.id
    user_data[user_id]['name'] = update.message.text
    await update.message.reply_text("Ваш номер телефона:")
    return ASK_PHONE

async def ask_phone(update: Update, context):
    user_id = update.effective_user.id
    user_data[user_id]['phone'] = update.message.text
    await update.message.reply_text("Выберите услугу:\n1 - Мужская стрижка (200₽)\n2 - Комплекс VIP (250₽)")
    return ASK_SERVICE

async def ask_service(update: Update, context):
    user_id = update.effective_user.id
    service_map = {"1": "Мужская стрижка (200 ₽)", "2": "Комплекс VIP (250 ₽)"}
    user_data[user_id]['service'] = service_map.get(update.message.text, update.message.text)
    await update.message.reply_text("Введите желаемую дату в формате ГГГГ-ММ-ДД:")
    return ASK_DATE

async def ask_date(update: Update, context):
    user_id = update.effective_user.id
    user_data[user_id]['date'] = update.message.text
    await update.message.reply_text("Введите время (ЧЧ:ММ):")
    return ASK_TIME

async def ask_time(update: Update, context):
    user_id = update.effective_user.id
    user_data[user_id]['time'] = update.message.text
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
    resp = requests.post(f"{SUPABASE_URL}/rest/v1/appointments", headers=headers, json=record)
    if resp.status_code == 201:
        await update.message.reply_text("✅ Вы успешно записаны!")
        await notify_admin(
            f"✂️ <b>Новая запись через бота!</b>\n"
            f"Клиент: {record['name']}\nТелефон: {record['phone']}\n"
            f"Услуга: {record['service']}\nДата: {record['date']} {record['time']}"
        )
    else:
        await update.message.reply_text("❌ Ошибка при записи. Попробуйте позже.")
        logging.error(f"Supabase error: {resp.text}")
    user_data.pop(user_id, None)
    return ConversationHandler.END

async def cancel(update: Update, context):
    user_id = update.effective_user.id
    user_data.pop(user_id, None)
    await update.message.reply_text("Запись отменена.")
    return ConversationHandler.END

async def my_records(update: Update, context):
    user_id = str(update.effective_user.id)
    resp = requests.get(f"{SUPABASE_URL}/rest/v1/appointments?user_telegram_id=eq.{user_id}", headers=headers)
    if resp.status_code != 200:
        await update.message.reply_text("Ошибка получения записей.")
        return
    records = resp.json()
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
        await query.edit_message_text("✅ Запись отменена.")
        await notify_admin(f"❌ <b>Отмена записи</b>\nID: {record_id}")
    else:
        await query.edit_message_text("❌ Ошибка при отмене.")

def main():
    application = Application.builder().token(TOKEN).build()
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
    # Ключевой параметр drop_pending_updates помогает избежать конфликта
    application.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
