import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
import requests

# Настройки
TELEGRAM_TOKEN = "8693807260:AAGDZ3121GHyRtnrwJALSHnBrotBrQQTAFc"
SUPABASE_URL = "https://uqenkackpzlslyjrmwkw.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVxZW5rYWNrcHpsc2x5anJtd2t3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzUzMTMzMTAsImV4cCI6MjA5MDg4OTMxMH0.yji4nZOzVvlc64zaogcMrpdsWwqWpkhHlKb29fx6rWs"
ADMIN_CHAT_ID = "689626594"

headers = {
    "apikey": SUPABASE_ANON_KEY,
    "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
    "Content-Type": "application/json"
}

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# Состояния FSM
class RecordStates(StatesGroup):
    name = State()
    phone = State()
    service = State()
    date = State()
    time = State()

async def notify_admin(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": ADMIN_CHAT_ID, "text": message, "parse_mode": "HTML"})
    except Exception as e:
        logging.error(f"Не удалось отправить уведомление: {e}")

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "✂️ Добро пожаловать в барбершоп!\n\n"
        "/record – записаться на стрижку\n"
        "/my_records – мои записи"
    )

@dp.message(Command("record"))
async def cmd_record(message: types.Message, state: FSMContext):
    await state.set_state(RecordStates.name)
    await message.answer("Как вас зовут? (имя и фамилия)")

@dp.message(RecordStates.name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(RecordStates.phone)
    await message.answer("Ваш номер телефона (для связи):")

@dp.message(RecordStates.phone)
async def process_phone(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text)
    await state.set_state(RecordStates.service)
    await message.answer("Выберите услугу:\n1 - Мужская стрижка (200₽)\n2 - Комплекс VIP (250₽)")

@dp.message(RecordStates.service)
async def process_service(message: types.Message, state: FSMContext):
    service_map = {"1": "Мужская стрижка (200 ₽)", "2": "Комплекс VIP (250 ₽)"}
    service = service_map.get(message.text, message.text)
    await state.update_data(service=service)
    await state.set_state(RecordStates.date)
    await message.answer("Введите желаемую дату в формате ГГГГ-ММ-ДД (например, 2026-04-10):")

@dp.message(RecordStates.date)
async def process_date(message: types.Message, state: FSMContext):
    await state.update_data(date=message.text)
    await state.set_state(RecordStates.time)
    await message.answer("Введите время (например, 20:00):")

@dp.message(RecordStates.time)
async def process_time(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = message.from_user.id
    record = {
        "name": data['name'],
        "surname": "",
        "user_group": "—",
        "phone": data['phone'],
        "service": data['service'],
        "barber": "Дмитрий The Old school",
        "date": data['date'],
        "time": message.text,
        "comment": "Запись через Telegram",
        "user_telegram_id": str(user_id)
    }
    resp = requests.post(f"{SUPABASE_URL}/rest/v1/appointments", headers=headers, json=record)
    if resp.status_code == 201:
        await message.answer("✅ Вы успешно записаны!")
        await notify_admin(
            f"✂️ <b>Новая запись через бота!</b>\n"
            f"Клиент: {record['name']}\nТелефон: {record['phone']}\n"
            f"Услуга: {record['service']}\nДата: {record['date']} {record['time']}"
        )
    else:
        await message.answer("❌ Ошибка при записи. Попробуйте позже.")
        logging.error(f"Supabase error: {resp.text}")
    await state.clear()

@dp.message(Command("my_records"))
async def cmd_my_records(message: types.Message):
    user_id = str(message.from_user.id)
    resp = requests.get(f"{SUPABASE_URL}/rest/v1/appointments?user_telegram_id=eq.{user_id}", headers=headers)
    if resp.status_code != 200:
        await message.answer("Ошибка получения записей.")
        return
    records = resp.json()
    if not records:
        await message.answer("У вас нет активных записей.")
        return
    for rec in records:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel_{rec['id']}")]
        ])
        await message.answer(
            f"📅 {rec['date']} {rec['time']}\n✂️ {rec['service']}\n👤 Мастер: {rec.get('barber', 'Дмитрий')}",
            reply_markup=keyboard
        )

@dp.callback_query(lambda c: c.data and c.data.startswith('cancel_'))
async def cancel_callback(callback: CallbackQuery):
    record_id = callback.data.split('_')[1]
    user_id = str(callback.from_user.id)
    resp = requests.delete(
        f"{SUPABASE_URL}/rest/v1/appointments?id=eq.{record_id}&user_telegram_id=eq.{user_id}",
        headers=headers
    )
    if resp.status_code == 200:
        await callback.message.edit_text("✅ Запись отменена.")
        await notify_admin(f"❌ <b>Отмена записи</b>\nID: {record_id}")
    else:
        await callback.message.edit_text("❌ Ошибка при отмене.")
    await callback.answer()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
