import logging
import sqlite3
import csv
import os
import asyncio
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

# Render xato bermasligi uchun soxta veb-server
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot ishlayapti")

def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), DummyHandler)
    server.serve_forever()

keep_alive_thread = threading.Thread(target=run_dummy_server)
keep_alive_thread.daemon = True
keep_alive_thread.start()
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils import executor
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton
)

# ================= SOZLAMALAR =================
# 1. BotFather tokeni
API_TOKEN = '9057684732:AAE1s5Qrv1UEoBw9rNBKvY3yMCIIZd-epjQ'

# 2. Kanal sozlamalari (Bot kanalda ADMIN bo'lishi shart!)
CHANNEL_ID = '@rimxabarlari'  # Masalan: '@rishton_im' yoki '-100123456789'
CHANNEL_URL = 'https://t.me/rimxabarlari'

# 3. Admin Telegram ID raqami (@userinfobot orqali bilib olasiz, faqat raqam yoziladi)
ADMIN_ID = 5552269930

# 4. Maktab manzili va koordinatalari
MAKTAB_LATITUDE = 40.357112
MAKTAB_LONGITUDE = 71.282834
MAKTAB_MANZILI = "Farg'ona viloyati, Rishton tumani, Rishton ixtisoslashgan maktabi"
MAP_LINK = f"https://www.google.com/maps/search/?api=1&query={40.382771507773214},{ 71.25811799868156}"

# 5. Maktab rasmi: kompyuterdagi fayl nomi ('school.jpg') yoki internetdagi rasm ssilkasi
SCHOOL_PHOTO = 'school.jpg'  # Papka ichiga school.jpg nomli rasm tashlab qo'ysangiz avtomatik yuboradi
# ==============================================

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN, parse_mode=types.ParseMode.HTML)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# --- SQLITE BAZASINI SOZLASH ---
def init_db():
    conn = sqlite3.connect('school_olympiad.db')
    cursor = conn.cursor()
    # O'quvchilar jadvali
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            fullname TEXT,
            school TEXT,
            grade TEXT,
            phone TEXT
        )
    ''')
    # Savol-javoblar (FAQ) jadvali
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS faqs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT,
            answer TEXT
        )
    ''')
    # Boshlang'ich bazaviy savollarni qo'shish (agar baza bo'sh bo'lsa)
    cursor.execute('SELECT COUNT(*) FROM faqs')
    if cursor.fetchone()[0] == 0:
        default_faqs = [
            ("Olimpiada qachon va soat nechada bo'ladi?", "📅 Olimpiada 12-dekabr kuni soat 09:00 da Rishton ixtisoslashgan maktabi binosida boshlanadi."),
            ("Olimpiadada qatnashish pullikmi?", "🆓 Yo'q, RISHTON IXTISOSLASHTIRILGAN MAKTABI DIREKTORINING OCHIQ OLIMPIADASI mutlaqo BEPUL!"),
            ("O'zim bilan nima olib borishim kerak?", "🪪 O'zingiz bilan tug'ilganlik haqida guvohnoma (yoki ID karta) hamda ko'k ruchka olib kelishingiz so'raladi.")
        ]
        cursor.executemany('INSERT INTO faqs (question, answer) VALUES (?, ?)', default_faqs)
    conn.commit()
    conn.close()

init_db()

# --- FSM BOSQICHLARI ---
class Registration(StatesGroup):
    fullname = State()
    school = State()
    custom_school = State()
    grade = State()
    phone = State()

class AdminState(StatesGroup):
    broadcast = State()
    faq_q = State()
    faq_a = State()

# --- TUGMALAR (KEYBOARDS) ---
# 1. Kanal obunasi
def get_sub_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("📢 Kanalga obuna bo'lish", url=CHANNEL_URL),
        InlineKeyboardButton("✅ Obunani tekshirish", callback_data="check_sub")
    )
    return keyboard

# 2. Maktablar ro'yxati (1 dan 66 gacha + Xususiy maktab)
def get_schools_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=4)
    # 1-maktabdan 66-maktabgacha tugmalar
    buttons = [KeyboardButton(f"{i}-maktab") for i in range(1, 67)]
    keyboard.add(*buttons)
    # Xususiy yoki boshqa maktab uchun alohida katta tugma
    keyboard.row(KeyboardButton("🏫 Xususiy maktab / Boshqa (nomini kiritish)"))
    return keyboard

# 3. Sinflar
def get_grade_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    keyboard.add(KeyboardButton("4-sinf"), KeyboardButton("6-sinf"))
    return keyboard

# 4. Telefon raqam
def get_phone_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    keyboard.add(KeyboardButton("📱 Telegram raqamimni yuborish", request_contact=True))
    return keyboard

# 5. Ro'yxatdan o'tgandan keyingi asosiy menyu
def get_main_menu():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add(
        KeyboardButton("📄 Mening ma'lumotnomam"),
        KeyboardButton("📍 Maktab manzili"),
        KeyboardButton("❓ Ko'p beriladigan savollar")
    )
    return keyboard

# 6. Admin panel menyusi
def get_admin_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add(
        KeyboardButton("📊 Statistika"),
        KeyboardButton("📥 Excel (CSV) yuklab olish"),
        KeyboardButton("📢 Xabar yuborish (Broadcast)"),
        KeyboardButton("➕ Savol-javob qo'shish"),
        KeyboardButton("🗑 Savol-javobni o'chirish"),
        KeyboardButton("🔙 Foydalanuvchi menyusi")
    )
    return keyboard

# --- OBUNANI TEKSHIRISH FUNKSIYASI ---
async def check_subscription(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logging.error(f"Obunani tekshirish xatosi: {e}")
        return False

# --- MA'LUMOTNOMA MATNINI YASASH ---
def generate_certificate_text(fullname, school, grade, phone):
    return (
        f"📋 <b>RO'YXATDAN O'TGANLIK MA'LUMOTNOMASI</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖➖➖➖➖\n"
        f"🏆 <b>Olimpiada:</b> RISHTON IXTISOSLASHTIRILGAN MAKTABI DIREKTORINING OCHIQ OLIMPIADASI\n"
        f"📚 <b>Fan:</b> Ingliz tili\n"
        f"👤 <b>O'quvchi F.I.O:</b> {fullname}\n"
        f"🏫 <b>Maktabi:</b> {school}\n"
        f"🎓 <b>Sinfi:</b> {grade}\n"
        f"☎️ <b>Telefon raqami:</b> {phone}\n"
        f"🆓 <b>Ishtirok etish:</b> MUTLAQO BEPUL\n"
        f"➖➖➖➖➖➖➖➖➖➖➖➖➖➖\n"
        f"📍 <b>Manzil:</b> {MAKTAB_MANZILI}\n"
        f"🗺 <a href='{MAP_LINK}'>👉 Xaritada ko'rish (Lokatsiya)</a>"
    )

# --- KIRISH VA /START BUYRUG'I ---
@dp.message_handler(commands=['start'], state='*')
async def cmd_start(message: types.Message, state: FSMContext):
    await state.finish()
    user_id = message.from_user.id

    # 1-BOSQICH: Maktab rasmini ko'rsatish (agar papkada school.jpg bo'lsa)
    welcome_caption = (
        "🏛 <b>RISHTON IXTISOSLASHTIRILGAN MAKTABI DIREKTORINING OCHIQ OLIMPIADASI</b> rasmiy botiga xush kelibsiz!\n\n"
        "🇬🇧 Fan: <b>Ingliz tili</b> (4- va 6-sinflar uchun)\n"
        "🆓 Olimpiadada ishtirok etish: <b>MUTLAQO BEPUL!</b>"
    )
    if os.path.exists(SCHOOL_PHOTO):
        with open(SCHOOL_PHOTO, 'rb') as photo:
            await message.answer_photo(photo, caption=welcome_caption)
    else:
        await message.answer(welcome_caption)

    # 2-BOSQICH: Kanal obunasini tekshirish
    is_sub = await check_subscription(user_id)
    if not is_sub:
        await message.answer(
            "❗️ Ro'yxatdan o'tishni boshlash uchun avval maktabimizning rasmiy kanaliga obuna bo'ling va <b>«✅ Obunani tekshirish»</b> tugmasini bosing:",
            reply_markup=get_sub_keyboard()
        )
        return

    await continue_after_sub(message.chat.id, user_id)

async def continue_after_sub(chat_id: int, user_id: int):
    conn = sqlite3.connect('school_olympiad.db')
    cursor = conn.cursor()
    cursor.execute('SELECT fullname, school, grade, phone FROM students WHERE user_id = ?', (user_id,))
    student = cursor.fetchone()
    conn.close()

    if student:
        fullname, school, grade, phone = student
        await bot.send_message(
            chat_id,
            "Siz allaqachon ro'yxatdan o'tgansiz! Quyidagi tugmalar orqali ma'lumotnomangizni ko'rishingiz yoki savollarga javob olishingiz mumkin:",
            reply_markup=get_main_menu()
        )
        await bot.send_message(
            chat_id,
            generate_certificate_text(fullname, school, grade, phone),
            disable_web_page_preview=True
        )
    else:
        await bot.send_message(
            chat_id,
            "✍️ Ro'yxatdan o'tishni boshlaymiz!\n\n"
            "Iltimos, o'quvchining <b>Familiyasi va Ismini</b> to'liq kiriting (masalan: <i>Aliyev Vali</i>):",
            reply_markup=ReplyKeyboardRemove()
        )
        await Registration.fullname.set()

# --- OBUNANI TEKSHIRISH CALLBACK ---
@dp.callback_query_handler(text="check_sub", state='*')
async def process_check_sub(call: types.CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    if await check_subscription(user_id):
        await call.message.delete()
        await continue_after_sub(call.message.chat.id, user_id)
    else:
        await call.answer("❌ Siz hali kanalga obuna bo'lmadingiz! Iltimos, avval a'zo bo'ling.", show_alert=True)

# --- 3-BOSQICH: ISM-FAMILIYA ---
@dp.message_handler(state=Registration.fullname, content_types=types.ContentTypes.TEXT)
async def process_fullname(message: types.Message, state: FSMContext):
    await state.update_data(fullname=message.text.strip())
    await message.reply(
        "🏫 Qaysi maktabda o'qiysiz?\n\n"
        "Pastdagi tugmalardan maktabingiz raqamini tanlang (1 dan 66 gacha). Agar xususiy yoki boshqa maktab bo'lsa, eng pastdagi <b>«🏫 Xususiy maktab / Boshqa»</b> tugmasini bosing:",
        reply_markup=get_schools_keyboard()
    )
    await Registration.school.set()

# --- 4-BOSQICH: MAKTAB TANLASH (1-66 yoki Xususiy) ---
@dp.message_handler(state=Registration.school, content_types=types.ContentTypes.TEXT)
async def process_school(message: types.Message, state: FSMContext):
    if message.text == "🏫 Xususiy maktab / Boshqa (nomini kiritish)":
        await message.reply(
            "✍️ Iltimos, o'zingiz o'qiydigan xususiy maktab (yoki muassasa) nomini yozib yuboring:",
            reply_markup=ReplyKeyboardRemove()
        )
        await Registration.custom_school.set()
    else:
        await state.update_data(school=message.text.strip())
        await message.reply(
            "🎓 Nechanchi sinfda o'qiysiz? Quyidagi tugmalardan birini bosing:",
            reply_markup=get_grade_keyboard()
        )
        await Registration.grade.set()

@dp.message_handler(state=Registration.custom_school, content_types=types.ContentTypes.TEXT)
async def process_custom_school(message: types.Message, state: FSMContext):
    await state.update_data(school=message.text.strip())
    await message.reply(
        "🎓 Nechanchi sinfda o'qiysiz? Quyidagi tugmalardan birini bosing:",
        reply_markup=get_grade_keyboard()
    )
    await Registration.grade.set()

# --- 5-BOSQICH: SINF TANLASH ---
@dp.message_handler(state=Registration.grade, content_types=types.ContentTypes.TEXT)
async def process_grade(message: types.Message, state: FSMContext):
    if message.text not in ["4-sinf", "6-sinf"]:
        await message.reply("Iltimos, pastdagi tugmalardan birini tanlang: 4-sinf yoki 6-sinf", reply_markup=get_grade_keyboard())
        return

    await state.update_data(grade=message.text)
    await message.reply(
        "☎️ Aloqa uchun telefon raqamingizni yuboring.\n\n"
        "Pastdagi <b>«📱 Telegram raqamimni yuborish»</b> tugmasini bosing yoki boshqa raqam bo'lsa, o'zingiz yozib yuboring (masalan: +998901234567):",
        reply_markup=get_phone_keyboard()
    )
    await Registration.phone.set()

# --- 6-BOSQICH: TELEFON RAQAM VA MA'LUMOTNOMA ---
@dp.message_handler(state=Registration.phone, content_types=[types.ContentType.CONTACT, types.ContentType.TEXT])
async def process_phone(message: types.Message, state: FSMContext):
    if message.contact is not None:
        phone = message.contact.phone_number
        if not phone.startswith('+'):
            phone = '+' + phone
    else:
        phone = message.text.strip()

    user_data = await state.get_data()
    fullname = user_data['fullname']
    school = user_data['school']
    grade = user_data['grade']
    user_id = message.from_user.id

    # Bazaga saqlash
    conn = sqlite3.connect('school_olympiad.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO students (user_id, fullname, school, grade, phone)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, fullname, school, grade, phone))
    conn.commit()
    conn.close()

    # Ma'lumotnomani yuborish
    cert_text = generate_certificate_text(fullname, school, grade, phone)
    await message.reply(
        "🎉 <b>Tabriklaymiz! Siz olimpiadaga muvaffaqiyatli ro'yxatdan o'tdingiz!</b>\n\n" + cert_text,
        reply_markup=get_main_menu(),
        disable_web_page_preview=True
    )

    # Xaritadagi joylashuvni (Venue) yuborish
    await bot.send_venue(
        chat_id=message.chat.id,
        latitude=MAKTAB_LATITUDE,
        longitude=MAKTAB_LONGITUDE,
        title="Rishton ixtisoslashgan maktabi",
        address=MAKTAB_MANZILI
    )

    await state.finish()

# ================= FOYDALANUVCHI MENYUSI VA SAVOL-JAVOBLAR =================
@dp.message_handler(lambda message: message.text == "📄 Mening ma'lumotnomam", state='*')
async def show_my_cert(message: types.Message):
    conn = sqlite3.connect('school_olympiad.db')
    cursor = conn.cursor()
    cursor.execute('SELECT fullname, school, grade, phone FROM students WHERE user_id = ?', (message.from_user.id,))
    student = cursor.fetchone()
    conn.close()

    if student:
        await message.reply(generate_certificate_text(*student), disable_web_page_preview=True)
    else:
        await message.reply("Siz hali ro'yxatdan o'tmagansiz. Ro'yxatdan o'tish uchun /start tugmasini bosing.")

@dp.message_handler(lambda message: message.text == "📍 Maktab manzili", state='*')
async def show_location(message: types.Message):
    await bot.send_venue(
        chat_id=message.chat.id,
        latitude=MAKTAB_LATITUDE,
        longitude=MAKTAB_LONGITUDE,
        title="Rishton ixtisoslashgan maktabi",
        address=f"{MAKTAB_MANZILI}\nKarta ssilkasi: {MAP_LINK}"
    )

@dp.message_handler(lambda message: message.text == "❓ Ko'p beriladigan savollar", state='*')
async def show_faqs(message: types.Message):
    conn = sqlite3.connect('school_olympiad.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, question FROM faqs')
    faqs = cursor.fetchall()
    conn.close()

    if not faqs:
        await message.reply("Hozircha savol-javoblar kiritilmagan.")
        return

    keyboard = InlineKeyboardMarkup(row_width=1)
    for faq_id, question in faqs:
        keyboard.add(InlineKeyboardButton(f"❓ {question}", callback_data=f"faq_{faq_id}"))

    await message.reply("O'zingizni qiziqtirgan savol ustiga bosing:", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith('faq_'), state='*')
async def answer_faq(call: types.CallbackQuery):
    faq_id = int(call.data.split('_')[1])
    conn = sqlite3.connect('school_olympiad.db')
    cursor = conn.cursor()
    cursor.execute('SELECT question, answer FROM faqs WHERE id = ?', (faq_id,))
    row = cursor.fetchone()
    conn.close()

    if row:
        q, a = row
        await call.message.answer(f"❓ <b>{q}</b>\n\n💡 {a}")
        await call.answer()
    else:
        await call.answer("Bu savol topilmadi.", show_alert=True)

# ================= ADMIN PANEL =================
@dp.message_handler(commands=['admin'], state='*')
async def admin_panel(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await message.reply("⛔️ Sizda admin huquqi yo'q!")
        return
    await state.finish()
    await message.reply("👨‍💻 <b>Admin panelga xush kelibsiz!</b>\nKerakli bo'limni tanlang:", reply_markup=get_admin_keyboard())

@dp.message_handler(lambda m: m.text == "🔙 Foydalanuvchi menyusi", state='*')
async def back_to_user_menu(message: types.Message, state: FSMContext):
    await state.finish()
    await message.reply("Asosiy menyu:", reply_markup=get_main_menu())

# 1. Statistika
@dp.message_handler(lambda m: m.text == "📊 Statistika", state='*')
async def admin_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    conn = sqlite3.connect('school_olympiad.db')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM students')
    total = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM students WHERE grade = '4-sinf'")
    g4 = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM students WHERE grade = '6-sinf'")
    g6 = cursor.fetchone()[0]
    conn.close()

    await message.reply(
        f"📊 <b>Olimpiada statistikasi:</b>\n\n"
        f"👥 Jami ro'yxatdan o'tganlar: <b>{total}</b> nafar\n"
        f"🔹 4-sinflar: <b>{g4}</b> nafar\n"
        f"🔸 6-sinflar: <b>{g6}</b> nafar"
    )

# 2. Excel (CSV) yuklab olish
@dp.message_handler(lambda m: m.text == "📥 Excel (CSV) yuklab olish", state='*')
async def admin_export(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    conn = sqlite3.connect('school_olympiad.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, user_id, fullname, school, grade, phone FROM students')
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await message.reply("Bazada hozircha hech kim yo'q.")
        return

    filename = 'olimpiada_royxati.csv'
    with open(filename, mode='w', encoding='utf-8-sig', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['T/R', 'Telegram ID', 'F.I.O', 'Maktabi', 'Sinfi', 'Telefon raqami'])
        writer.writerows(rows)

    with open(filename, 'rb') as file:
        await message.reply_document(file, caption=f"📊 Jami ro'yxatdan o'tganlar: {len(rows)} nafar.")

# 3. Ommaviy xabar yuborish (Broadcast)
@dp.message_handler(lambda m: m.text == "📢 Xabar yuborish (Broadcast)", state='*')
async def start_broadcast(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.reply(
        "✍️ Barcha ro'yxatdan o'tgan o'quvchilarga yuboriladigan xabar matnini (yoki rasm/video) yuboring.\n"
        "Bekor qilish uchun /admin deb yozing:"
    )
    await AdminState.broadcast.set()

@dp.message_handler(state=AdminState.broadcast, content_types=types.ContentTypes.ANY)
async def process_broadcast(message: types.Message, state: FSMContext):
    if message.text == "/admin":
        await state.finish()
        await message.reply("Bekor qilindi.", reply_markup=get_admin_keyboard())
        return

    conn = sqlite3.connect('school_olympiad.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM students')
    users = cursor.fetchall()
    conn.close()

    sent_count = 0
    await message.reply("⏳ Xabarlar yuborilmoqda...")
    for (uid,) in users:
        try:
            await message.copy_to(chat_id=uid)
            sent_count += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass

    await state.finish()
    await message.reply(f"✅ Xabar jami <b>{sent_count}</b> nafar foydalanuvchiga yetkazildi!", reply_markup=get_admin_keyboard())

# 4. Savol-javob (FAQ) qo'shish
@dp.message_handler(lambda m: m.text == "➕ Savol-javob qo'shish", state='*')
async def add_faq_start(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.reply("❓ Yangi <b>savol</b> matnini kiriting (Bekor qilish uchun /admin):")
    await AdminState.faq_q.set()

@dp.message_handler(state=AdminState.faq_q, content_types=types.ContentTypes.TEXT)
async def add_faq_question(message: types.Message, state: FSMContext):
    if message.text == "/admin":
        await state.finish()
        await message.reply("Bekor qilindi.", reply_markup=get_admin_keyboard())
        return
    await state.update_data(question=message.text)
    await message.reply("💡 Endi ushbu savolga <b>javob</b> matnini kiriting:")
    await AdminState.faq_a.set()

@dp.message_handler(state=AdminState.faq_a, content_types=types.ContentTypes.TEXT)
async def add_faq_answer(message: types.Message, state: FSMContext):
    data = await state.get_data()
    q = data['question']
    a = message.text

    conn = sqlite3.connect('school_olympiad.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO faqs (question, answer) VALUES (?, ?)', (q, a))
    conn.commit()
    conn.close()

    await state.finish()
    await message.reply("✅ Yangi savol-javob bazaga muvaffaqiyatli qo'shildi!", reply_markup=get_admin_keyboard())

# 5. Savol-javobni o'chirish
@dp.message_handler(lambda m: m.text == "🗑 Savol-javobni o'chirish", state='*')
async def delete_faq_menu(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    conn = sqlite3.connect('school_olympiad.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, question FROM faqs')
    faqs = cursor.fetchall()
    conn.close()

    if not faqs:
        await message.reply("O'chirish uchun savollar yo'q.")
        return

    keyboard = InlineKeyboardMarkup(row_width=1)
    for faq_id, q in faqs:
        keyboard.add(InlineKeyboardButton(f"❌ {q}", callback_data=f"delfaq_{faq_id}"))

    await message.reply("O'chirmoqchi bo'lgan savolingiz ustiga bosing:", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith('delfaq_'), state='*')
async def delete_faq_confirm(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    faq_id = int(call.data.split('_')[1])
    conn = sqlite3.connect('school_olympiad.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM faqs WHERE id = ?', (faq_id,))
    conn.commit()
    conn.close()

    await call.message.edit_text("✅ Savol bazadan o'chirildi!")
    await call.answer()

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
