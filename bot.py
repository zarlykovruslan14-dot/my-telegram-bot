import asyncio
import logging
import os
import sqlite3
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Токен вашего бота от @BotFather
BOT_TOKEN = "ВАШ_ТОКЕН_БОТА"

# Ссылка или путь к файлу (до 50 МБ), который отдается после проверки подписки
FILE_TO_SEND = "https://example.com/your_file.pdf"

# Создаем папку data для постоянного диска на Koyeb
os.makedirs("/app/data", exist_ok=True)
DB_PATH = "/app/data/database.db"

# --- ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            channel_id TEXT PRIMARY KEY,
            channel_url TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# --- ФУНКЦИИ РАБОТЫ С БД ---
def add_user(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users

def set_admin(admin_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('admin_id', ?)", (str(admin_id),))
    conn.commit()
    conn.close()

def get_admin():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key='admin_id'")
    row = cursor.fetchone()
    conn.close()
    return int(row[0]) if row else None

def add_channel(channel_id: str, url: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO channels (channel_id, channel_url) VALUES (?, ?)", (channel_id, url))
    conn.commit()
    conn.close()

def clear_channels():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM channels")
    conn.commit()
    conn.close()

def get_channels():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT channel_id, channel_url FROM channels")
    rows = cursor.fetchall()
    conn.close()
    return rows

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- ПРОВЕРКА ПОДПИСКИ ---
async def check_user_subscriptions(user_id: int) -> tuple[bool, list]:
    channels = get_channels()
    unsubscribed = []
    
    for ch_id, ch_url in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch_id, user_id=user_id)
            if member.status in ["left", "kicked"]:
                unsubscribed.append((ch_id, ch_url))
        except Exception as e:
            logging.error(f"Ошибка проверки канала {ch_id}: {e}")
            unsubscribed.append((ch_id, ch_url))
            
    return (len(unsubscribed) == 0, unsubscribed)

def build_subscribe_keyboard():
    channels = get_channels()
    buttons = []
    
    for idx, (ch_id, ch_url) in enumerate(channels, 1):
        buttons.append([InlineKeyboardButton(text=f"📌 Подписаться на Канал #{idx}", url=ch_url)])
        
    buttons.append([InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_sub")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- ОБРАБОТЧИКИ ПОЛЬЗОВАТЕЛЕЙ ---
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    add_user(message.from_user.id)
    is_subbed, _ = await check_user_subscriptions(message.from_user.id)
    
    if is_subbed:
        await message.answer("✅ Вы подписаны на все каналы! Вот ваш файл:")
        await message.answer_document(FILE_TO_SEND)
    else:
        kb = build_subscribe_keyboard()
        await message.answer(
            "👋 Чтобы получить файл, пожалуйста, подпишитесь на наши каналы:",
            reply_markup=kb
        )

@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(callback: types.CallbackQuery):
    is_subbed, _ = await check_user_subscriptions(callback.from_user.id)
    
    if is_subbed:
        await callback.message.edit_text("🎉 Подписка подтверждена! Отправляю файл...")
        await bot.send_document(chat_id=callback.from_user.id, document=FILE_TO_SEND)
    else:
        await callback.answer("❌ Вы подписались не на все каналы!", show_alert=True)

# --- АДМИН-ПАНЕЛЬ ---
@dp.message(Command("admin67"))
async def admin_auth(message: types.Message):
    set_admin(message.from_user.id)
    add_user(message.from_user.id)
    await message.answer(
        "⚙️ **Вы вошли как администратор!**\n\n"
        "• **Добавить канал:** Перешлите сюда любой пост из канала ИЛИ отправьте ссылку в формате:\n"
        "`@username_kanala https://t.me/username_kanala`\n\n"
        "• `/del_channels` — Очистить список каналов\n"
        "• `/broadcast ТЕКСТ` — Сделать рассылку всем\n"
        "• **Ответить пользователю:** Нажмите «Ответить» (Reply) на пересланное сообщение."
    )

@dp.message(Command("del_channels"))
async def del_channels_cmd(message: types.Message):
    admin_id = get_admin()
    if message.from_user.id != admin_id:
        return
    clear_channels()
    await message.answer("🗑 Все каналы из проверки удалены!")

@dp.message(Command("broadcast"))
async def broadcast_cmd(message: types.Message):
    admin_id = get_admin()
    if message.from_user.id != admin_id:
        return
    
    text = message.text.replace("/broadcast", "").strip()
    if not text:
        await message.answer("Укажите текст рассылки: `/broadcast Привет всем!`")
        return
        
    users = get_all_users()
    count = 0
    for uid in users:
        try:
            await bot.send_message(chat_id=uid, text=text)
            count += 1
        except Exception:
            pass
    await message.answer(f"📢 Рассылка отправлена {count} пользователям.")

# Добавление канала через пересылку поста
@dp.message(F.forward_from_chat)
async def add_channel_by_forward(message: types.Message):
    admin_id = get_admin()
    if message.from_user.id != admin_id:
        return
    
    chat = message.forward_from_chat
    ch_id = str(chat.id)
    username = chat.username
    url = f"https://t.me/{username}" if username else "https://t.me/"
    
    add_channel(ch_id, url)
    await message.answer(f"✅ Канал `{chat.title}` добавлен в проверку!")

# Ответ админа (Reply)
@dp.message(F.reply_to_message)
async def reply_handler(message: types.Message):
    admin_id = get_admin()
    if message.from_user.id != admin_id:
        return
        
    if message.reply_to_message.forward_from:
        target_id = message.reply_to_message.forward_from.id
        try:
            await bot.send_message(chat_id=target_id, text=message.text)
            await message.answer("✅ Ответ отправлен пользователю.")
        except Exception as e:
            await message.answer(f"❌ Не удалось отправить: {e}")

# Пересылка сообщений пользователей админу
@dp.message()
async def forward_to_admin(message: types.Message):
    add_user(message.from_user.id)
    admin_id = get_admin()
    
    if message.from_user.id == admin_id:
        if message.text and message.text.startswith("@"):
            parts = message.text.split()
            if len(parts) >= 2:
                add_channel(parts[0], parts[1])
                await message.answer(f"✅ Канал {parts[0]} сохранен!")
                return

    if admin_id and message.from_user.id != admin_id:
        await bot.forward_message(
            chat_id=admin_id,
            from_chat_id=message.chat.id,
            message_id=message.message_id
        )
        await message.answer("Сообщение отправлено администратору.")

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())