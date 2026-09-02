import asyncio
import logging
import sqlite3
import os
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Токен исправлен на корректный формат (без лишней восьмерки в начале)
BOT_TOKEN = "8616351451:AAGxnymMvfp0ltfb0ZTkueh8p4WYievaGCs"

os.makedirs("/app/data", exist_ok=True)
DB_PATH = "/app/data/database.db"

class AddFileState(StatesGroup):
    waiting_for_button_title = State()

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
    cursor.execute("CREATE TABLE IF NOT EXISTS channels (channel_id TEXT PRIMARY KEY, channel_url TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            file_id TEXT NOT NULL,
            file_type TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

init_db()

# --- Работа с БД ---

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

def add_file_to_db(title: str, file_id: str, file_type: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO files (title, file_id, file_type) VALUES (?, ?, ?)", (title, file_id, file_type))
    conn.commit()
    conn.close()

def get_all_files():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, file_id, file_type FROM files")
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_file_by_id(file_row_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT file_id, file_type FROM files WHERE id = ?", (file_row_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def clear_files():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM files")
    conn.commit()
    conn.close()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- Проверка подписок ---

async def check_user_subscriptions(user_id: int) -> tuple[bool, list]:
    channels = get_channels()
    unsubscribed = []
    for ch_id, ch_url in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch_id, user_id=user_id)
            if member.status in ["left", "kicked", "restricted"]:
                unsubscribed.append((ch_id, ch_url))
        except Exception as e:
            logging.error(f"Ошибка проверки {ch_id}: {e}")
            unsubscribed.append((ch_id, ch_url))
    return (len(unsubscribed) == 0, unsubscribed)

def build_subscribe_keyboard():
    channels = get_channels()
    buttons = []
    for idx, (ch_id, ch_url) in enumerate(channels, 1):
        buttons.append([InlineKeyboardButton(text=f"📌 Подписаться на Канал #{idx}", url=ch_url)])
    buttons.append([InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_sub")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def build_files_keyboard():
    files = get_all_files()
    buttons = []
    for f_id, title, _, _ in files:
        buttons.append([InlineKeyboardButton(text=f"📁 {title}", callback_data=f"get_file_{f_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

async def send_file_to_user(chat_id: int, file_id: str, file_type: str):
    try:
        if file_type == "document":
            await bot.send_document(chat_id=chat_id, document=file_id)
        elif file_type == "photo":
            await bot.send_photo(chat_id=chat_id, photo=file_id)
        elif file_type == "video":
            await bot.send_video(chat_id=chat_id, video=file_id)
    except Exception as e:
        logging.error(f"Ошибка отправки файла: {e}")

# --- Хэндлеры ---

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    add_user(message.from_user.id)
    is_subbed, _ = await check_user_subscriptions(message.from_user.id)
    if is_subbed:
        files = get_all_files()
        if not files:
            await message.answer("✅ Вы подписаны! Но пока нет доступных файлов для скачивания.")
        else:
            kb = build_files_keyboard()
            await message.answer("✅ Вы подписаны! Выберите нужный файл из списка:", reply_markup=kb)
    else:
        kb = build_subscribe_keyboard()
        await message.answer("👋 Чтобы получить файлы, подпишитесь на каналы ниже:", reply_markup=kb)

@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(callback: types.CallbackQuery):
    is_subbed, _ = await check_user_subscriptions(callback.from_user.id)
    if is_subbed:
        files = get_all_files()
        if not files:
            await callback.message.edit_text("🎉 Подписка подтверждена! Но файлы пока не добавлены.")
        else:
            kb = build_files_keyboard()
            await callback.message.edit_text("🎉 Подписка подтверждена! Выберите файл:", reply_markup=kb)
    else:
        await callback.answer("❌ Вы подписались не на все каналы!", show_alert=True)

@dp.callback_query(F.data.startswith("get_file_"))
async def get_file_callback(callback: types.CallbackQuery):
    is_subbed, _ = await check_user_subscriptions(callback.from_user.id)
    if not is_subbed:
        await callback.answer("❌ Вы отписались от каналов! Проверьте подписку.", show_alert=True)
        return

    file_row_id = int(callback.data.replace("get_file_", ""))
    file_info = get_file_by_id(file_row_id)
    if file_info:
        file_id, file_type = file_info
        await callback.answer("Отправляю файл...")
        await send_file_to_user(callback.from_user.id, file_id, file_type)
    else:
        await callback.answer("⚠️ Файл не найден или был удален.", show_alert=True)

# --- АДМИН ПАНЕЛЬ ---

@dp.message(Command("admin67"))
async def admin_auth(message: types.Message):
    set_admin(message.from_user.id)
    add_user(message.from_user.id)
    await message.answer(
        "⚙️ **Режим админа активирован!**\n\n"
        "• **Добавление файла**: просто пришлите боту документ/фото/видео\n"
        "• **Добавление канала**: перешлите пост из него ИЛИ отправьте `@username https://t.me/username`\n"
        "• `/del_channels` — очистить список каналов\n"
        "• `/del_files` — очистить список файлов\n"
        "• `/broadcast ТЕКСТ` — рассылка пользователям\n"
        "• Ответьте (Reply) на сообщение пользователя, чтобы написать ему в ЛС."
    )

@dp.message(Command("del_channels"))
async def del_channels_cmd(message: types.Message):
    admin_id = get_admin()
    if not admin_id or message.from_user.id != admin_id:
        return
    clear_channels()
    await message.answer("🗑 Список каналов очищен!")

@dp.message(Command("del_files"))
async def del_files_cmd(message: types.Message):
    admin_id = get_admin()
    if not admin_id or message.from_user.id != admin_id:
        return
    clear_files()
    await message.answer("🗑 Все файлы удалены из списка!")

@dp.message(Command("broadcast"))
async def broadcast_cmd(message: types.Message):
    admin_id = get_admin()
    if not admin_id or message.from_user.id != admin_id:
        return
    text = message.text.replace("/broadcast", "").strip()
    if not text:
        await message.answer("Укажите текст: `/broadcast Ваш текст`")
        return
    users = get_all_users()
    count = sum(1 for uid in users if await send_safe(uid, text))
    await message.answer(f"📢 Рассылка отправлена {count} пользователям.")

async def send_safe(uid, text):
    try:
        await bot.send_message(chat_id=uid, text=text)
        return True
    except Exception:
        return False

# --- Прием файлов от Админа ---

@dp.message(F.content_type.in_({'document', 'photo', 'video'}))
async def handle_admin_file(message: types.Message, state: FSMContext):
    admin_id = get_admin()
    if not admin_id or message.from_user.id != admin_id:
        return

    if message.document:
        f_id = message.document.file_id
        f_type = "document"
    elif message.photo:
        f_id = message.photo[-1].file_id
        f_type = "photo"
    elif message.video:
        f_id = message.video.file_id
        f_type = "video"
    else:
        return

    await state.update_data(file_id=f_id, file_type=f_type)
    await state.set_state(AddFileState.waiting_for_button_title)
    await message.answer("📥 Файл получен! Теперь напишите **название для кнопки**, которая будет выдавать этот файл:")

@dp.message(AddFileState.waiting_for_button_title)
async def process_file_title(message: types.Message, state: FSMContext):
    admin_id = get_admin()
    if not admin_id or message.from_user.id != admin_id:
        return

    title = message.text.strip()
    data = await state.get_data()
    
    add_file_to_db(title=title, file_id=data['file_id'], file_type=data['file_type'])
    await state.clear()
    await message.answer(f"✅ Файл сохранен! Добавлена кнопка: **«{title}»**")

# --- Добавление каналов и пересылка ---

@dp.message(F.forward_origin)
async def add_channel_by_forward(message: types.Message):
    admin_id = get_admin()
    if not admin_id or message.from_user.id != admin_id:
        return
    
    # Обновленная безопасная логика получения данных канала для aiogram 3.x
    origin = message.forward_origin
    if getattr(origin, 'type', None) == 'channel':
        chat = origin.chat
        url = f"https://t.me/{chat.username}" if getattr(chat, 'username', None) else "https://t.me/"
        add_channel(str(chat.id), url)
        await message.answer(f"✅ Канал `{chat.title}` добавлен!")

@dp.message(F.reply_to_message)
async def reply_handler(message: types.Message):
    admin_id = get_admin()
    if not admin_id or message.from_user.id != admin_id:
        return
    
    # Безопасное извлечение ID пользователя, от которого переслано сообщение
    replied = message.reply_to_message
    target_id = None
    
    if replied.forward_origin and getattr(replied.forward_origin, 'type', None) == 'user':
        target_id = replied.forward_origin.sender_user.id
    elif replied.forward_from:
        target_id = replied.forward_from.id
        
    if target_id:
        try:
            await bot.send_message(chat_id=target_id, text=message.text)
            await message.answer("✅ Ответ отправлен пользователю.")
        except Exception as e:
            await message.answer(f"❌ Не удалось отправить: {e}")
    else:
        await message.answer("⚠️ Не удалось определить пользователя. У него скрыт профиль при пересылке.")

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
        try:
            await bot.forward_message(chat_id=admin_id, from_chat_id=message.chat.id, message_id=message.message_id)
            await message.answer("Сообщение отправлено администратору.")
        except Exception as e:
            logging.error(f"Ошибка пересылки админу: {e}")

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
