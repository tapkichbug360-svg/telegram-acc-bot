import asyncio
import pytz
import aiohttp
import os
import psycopg2
import logging
import threading
import uvicorn
from datetime import datetime, timedelta
from sepay import app as sepay_app
from datetime import datetime
from psycopg2.extras import RealDictCursor
from typing import Dict, List, Tuple
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties

# ==================== MIGRATE DATABASE LOCAL ====================
def fix_ref_code():
    """Sửa ref_code cho user cũ trên local"""
    conn = get_db_connection()
    c = conn.cursor()
    
    # Kiểm tra xem cột ref_code có tồn tại chưa
    try:
        c.execute("SELECT ref_code FROM users LIMIT 1")
    except Exception:
        print("⚠️ Cột ref_code chưa tồn tại, đang thêm...")
        try:
            c.execute("ALTER TABLE users ADD COLUMN ref_by BIGINT DEFAULT NULL")
            c.execute("ALTER TABLE users ADD COLUMN ref_code TEXT UNIQUE")
            c.execute("ALTER TABLE users ADD COLUMN total_ref_commission BIGINT DEFAULT 0")
            print("✅ Đã thêm các cột mới")
        except Exception as e:
            print(f"Lỗi: {e}")
    
    # Cập nhật ref_code cho user bị NULL
    try:
        c.execute("SELECT telegram_id FROM users WHERE ref_code IS NULL")
        null_users = c.fetchall()
        import random
        import string
        for user in null_users:
            new_ref_code = f"REF{user[0]}{''.join(random.choices(string.digits, k=4))}"
            c.execute("UPDATE users SET ref_code = %s WHERE telegram_id = %s", (new_ref_code, user[0]))
            print(f"✅ Đã tạo ref_code cho user {user[0]}: {new_ref_code}")
        conn.commit()
    except Exception as e:
        print(f"Lỗi cập nhật: {e}")
    
    conn.close()

# ==================== CẤU HÌNH ====================
BOT_TOKEN = "8246231057:AAHjwHpgQxt6AiU-67h12Fpm6F500k-wYUI"
ADMIN_IDS = [5180190297]
ADMIN_USERNAMES = ["makkllai"]
VIETNAM_TZ = pytz.timezone('Asia/Ho_Chi_Minh')  # Thêm dòng này

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:Manh123@103.152.164.136:5432/telegram_bot")

SITES = ["SC88", "C168", "CM88", "FLY88", "F168"]
SITE_EMOJI = {"SC88": "🎰", "C168": "🎲", "CM88": "🃏", "FLY88": "✈️", "F168": "🏆"}
SITE_PRICE = {"SC88": 20000, "C168": 20000, "CM88": 20000, "FLY88": 20000, "F168": 20000}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==================== DATABASE ====================
def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    # Thêm vào hàm init_db()
    c.execute('''CREATE TABLE IF NOT EXISTS otp_rentals (
        id SERIAL PRIMARY KEY,
        user_id BIGINT,
        request_id TEXT,
        phone_number TEXT,
        service_name TEXT,
        price INTEGER,
        code TEXT,
        sms_content TEXT,
        status INTEGER DEFAULT 0,
        rented_at TEXT,
        refunded INTEGER DEFAULT 0
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        telegram_id BIGINT PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        balance BIGINT DEFAULT 0,
        total_recharge BIGINT DEFAULT 0,
        total_spent BIGINT DEFAULT 0,
        created_at TEXT,
        ref_by BIGINT DEFAULT NULL,
        ref_code TEXT UNIQUE,
        total_ref_commission BIGINT DEFAULT 0
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS ref_commissions (
        id SERIAL PRIMARY KEY,
        user_id BIGINT,
        ref_user_id BIGINT,
        amount INTEGER,
        note TEXT,
        created_at TEXT
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS accounts (
        id SERIAL PRIMARY KEY,
        site TEXT, username TEXT, password TEXT, 
        withdraw_password TEXT, real_name TEXT, bank_number TEXT, phone TEXT,
        price INTEGER DEFAULT 20000,
        is_sold INTEGER DEFAULT 0, sold_to INTEGER, sold_at TEXT, created_at TEXT,
        note TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS purchases (
        id SERIAL PRIMARY KEY,
        user_id BIGINT, account_id INTEGER, site TEXT, amount INTEGER, 
        purchased_at TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS recharge_history (
        id SERIAL PRIMARY KEY,
        user_id BIGINT, amount INTEGER, note TEXT, created_at TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS admin_logs (
        id SERIAL PRIMARY KEY,
        admin_id BIGINT, action TEXT, target_id BIGINT, details TEXT, created_at TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS site_settings (
        site TEXT PRIMARY KEY, price INTEGER, is_active INTEGER DEFAULT 1)''')
    
    for site in SITES:
        c.execute("INSERT INTO site_settings (site, price) VALUES (%s, %s) ON CONFLICT (site) DO NOTHING", (site, SITE_PRICE[site]))
    
    conn.commit()
    conn.close()
    logger.info("✅ Database on VPS initialized")

def get_user(telegram_id: int, username: str = None, full_name: str = None, ref_by: int = None):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE telegram_id = %s", (telegram_id,))
    user = c.fetchone()
    
    if not user:
        # User chưa tồn tại - Tạo mới
        ref_code = generate_ref_code(telegram_id)
        print(f"[DEBUG] Tạo user mới: {telegram_id}, ref_by={ref_by}")
        
        c.execute("""INSERT INTO users (telegram_id, username, full_name, created_at, ref_by, ref_code) 
                     VALUES (%s, %s, %s, %s, %s, %s)""", 
                  (telegram_id, username, full_name, datetime.now(VIETNAM_TZ).isoformat(), ref_by, ref_code))
        conn.commit()
        
        if ref_by:
            try:
                import asyncio
                asyncio.create_task(bot.send_message(
                    ref_by,
                    f"👥 <b>GIỚI THIỆU MỚI</b>\n\n"
                    f"🎉 Bạn vừa giới thiệu user mới: @{username or full_name or str(telegram_id)}\n"
                    f"💰 Sẽ nhận 5% hoa hồng từ mỗi lần nạp của user này!"
                ))
                print(f"[DEBUG] Đã gửi thông báo cho người giới thiệu {ref_by}")
            except Exception as e:
                print(f"[DEBUG] Lỗi gửi thông báo: {e}")
        
        c.execute("SELECT * FROM users WHERE telegram_id = %s", (telegram_id,))
        user = c.fetchone()
    else:
        # User đã tồn tại - Không cập nhật ref_by (chỉ cập nhật tên)
        print(f"[DEBUG] User đã tồn tại: {telegram_id}, bỏ qua ref_by")
        need_update = False
        if username and user[1] != username:
            c.execute("UPDATE users SET username = %s WHERE telegram_id = %s", (username, telegram_id))
            need_update = True
        if full_name and user[2] != full_name:
            c.execute("UPDATE users SET full_name = %s WHERE telegram_id = %s", (full_name, telegram_id))
            need_update = True
        if need_update:
            conn.commit()
            c.execute("SELECT * FROM users WHERE telegram_id = %s", (telegram_id,))
            user = c.fetchone()
    conn.close()
    return user

def update_balance(telegram_id: int, amount: int, note: str = ""):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + %s WHERE telegram_id = %s", (amount, telegram_id))
    if amount > 0:
        c.execute("UPDATE users SET total_recharge = total_recharge + %s WHERE telegram_id = %s", (amount, telegram_id))
        
        # KIỂM TRA CÓ PHẢI HOÀN TIỀN KHÔNG
        is_refund = "hoàn tiền" in note.lower() or "hết 6 phút" in note.lower()
        
        # CHỈ TÍNH HOA HỒNG KHI KHÔNG PHẢI HOÀN TIỀN
        if not is_refund:
            # Tính hoa hồng 5% cho người giới thiệu
            c.execute("SELECT ref_by FROM users WHERE telegram_id = %s", (telegram_id,))
            ref_by = c.fetchone()
            
            if ref_by and ref_by[0]:
                commission = int(amount * 0.05)
                if commission > 0:
                    add_ref_commission(telegram_id, ref_by[0], commission, f"Hoa hồng 5% từ nạp {amount:,}đ của user {telegram_id}")
                    
                    try:
                        import asyncio
                        asyncio.create_task(bot.send_message(
                            ref_by[0],
                            f"💰 <b>NHẬN HOA HỒNG GIỚI THIỆU</b>\n\n"
                            f"👤 User bạn giới thiệu: <code>{telegram_id}</code>\n"
                            f"💵 Nạp: {amount:,}đ\n"
                            f"🎁 Hoa hồng 5%: <b>{commission:,}đ</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━\n"
                            f"💡 Tiền đã được cộng vào số dư của bạn!"
                        ))
                    except:
                        pass
    else:
        c.execute("UPDATE users SET total_spent = total_spent + %s WHERE telegram_id = %s", (-amount, telegram_id))
    
    c.execute("INSERT INTO recharge_history (user_id, amount, note, created_at) VALUES (%s, %s, %s, %s)",
              (telegram_id, amount, note, datetime.now(VIETNAM_TZ).isoformat()))
    conn.commit()
    conn.close()

def add_admin_log(admin_id: int, action: str, target_id: int = None, details: str = ""):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT INTO admin_logs (admin_id, action, target_id, details, created_at) VALUES (%s, %s, %s, %s, %s)",
              (admin_id, action, target_id, details, datetime.now(VIETNAM_TZ).isoformat()))
    conn.commit()
    conn.close()

def get_available_account(site: str):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM accounts WHERE site = %s AND is_sold = 0 LIMIT 1", (site,))
    acc = c.fetchone()
    conn.close()
    return acc

def mark_sold(account_id: int, user_id: int):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE accounts SET is_sold = 1, sold_to = %s, sold_at = %s WHERE id = %s",
              (user_id, datetime.now(VIETNAM_TZ).isoformat(), account_id))
    conn.commit()
    conn.close()

def save_purchase(user_id: int, account_id: int, site: str, amount: int):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT INTO purchases (user_id, account_id, site, amount, purchased_at) VALUES (%s, %s, %s, %s, %s)",
              (user_id, account_id, site, amount, datetime.now(VIETNAM_TZ).isoformat()))
    conn.commit()
    conn.close()

def add_account(site: str, username: str, password: str, 
                withdraw_password: str = "", real_name: str = "", 
                bank_number: str = "", phone: str = "", note: str = ""):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""INSERT INTO accounts 
              (site, username, password, withdraw_password, real_name, bank_number, phone, created_at, note) 
              VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
              (site, username, password, withdraw_password, real_name, bank_number, phone, datetime.now(VIETNAM_TZ).isoformat(), note))
    conn.commit()
    conn.close()

def bulk_add_accounts(site: str, accounts: List[Tuple[str, str]]):
    conn = get_db_connection()
    c = conn.cursor()
    for username, password in accounts:
        c.execute("INSERT INTO accounts (site, username, password, created_at) VALUES (%s, %s, %s, %s)",
                  (site, username, password, datetime.now(VIETNAM_TZ).isoformat()))
    conn.commit()
    conn.close()

def get_inventory() -> Dict:
    conn = get_db_connection()
    c = conn.cursor()
    inv = {}
    for site in SITES:
        c.execute("SELECT COUNT(*) FROM accounts WHERE site = %s AND is_sold = 0", (site,))
        inv[site] = c.fetchone()[0]
    conn.close()
    return inv

def get_sold_stats() -> Tuple[Dict, Dict]:
    conn = get_db_connection()
    c = conn.cursor()
    sold = {}
    revenue = {}
    for site in SITES:
        c.execute("SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM purchases WHERE site = %s", (site,))
        count, total = c.fetchone()
        sold[site] = count or 0
        revenue[site] = total or 0
    conn.close()
    return sold, revenue
# ==================== MIGRATE DATABASE ====================
def migrate_db():
    """Thêm các cột mới cho tính năng referral nếu chưa có"""
    conn = get_db_connection()
    c = conn.cursor()
    
    # Thêm cột ref_by
    try:
        c.execute("ALTER TABLE users ADD COLUMN ref_by BIGINT DEFAULT NULL")
        print("✅ Đã thêm cột ref_by")
    except Exception as e:
        if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
            print("ℹ️ Cột ref_by đã tồn tại")
        else:
            print(f"⚠️ Lỗi khi thêm ref_by: {e}")
    
    # Thêm cột ref_code
    try:
        c.execute("ALTER TABLE users ADD COLUMN ref_code TEXT UNIQUE")
        print("✅ Đã thêm cột ref_code")
    except Exception as e:
        if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
            print("ℹ️ Cột ref_code đã tồn tại")
        else:
            print(f"⚠️ Lỗi khi thêm ref_code: {e}")
    
    # Thêm cột total_ref_commission
    try:
        c.execute("ALTER TABLE users ADD COLUMN total_ref_commission BIGINT DEFAULT 0")
        print("✅ Đã thêm cột total_ref_commission")
    except Exception as e:
        if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
            print("ℹ️ Cột total_ref_commission đã tồn tại")
        else:
            print(f"⚠️ Lỗi khi thêm total_ref_commission: {e}")
    
    # Tạo bảng ref_commissions nếu chưa có
    try:
        c.execute('''CREATE TABLE IF NOT EXISTS ref_commissions (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            ref_user_id BIGINT,
            amount INTEGER,
            note TEXT,
            created_at TEXT
        )''')
        print("✅ Đã tạo bảng ref_commissions")
    except Exception as e:
        print(f"⚠️ Lỗi tạo bảng ref_commissions: {e}")
    
    # Cập nhật ref_code cho user cũ bị NULL
    try:
        c.execute("SELECT telegram_id FROM users WHERE ref_code IS NULL")
        null_users = c.fetchall()
        for user in null_users:
            new_ref_code = generate_ref_code(user[0])
            c.execute("UPDATE users SET ref_code = %s WHERE telegram_id = %s", (new_ref_code, user[0]))
        print(f"✅ Đã cập nhật ref_code cho {len(null_users)} user cũ")
    except Exception as e:
        print(f"⚠️ Lỗi cập nhật ref_code: {e}")
    
    conn.commit()
    conn.close()
def get_user_history(user_id: int, limit: int = 20) -> List[Dict]:
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM purchases WHERE user_id = %s ORDER BY purchased_at DESC LIMIT %s", (user_id, limit))
    purchases = c.fetchall()
    history = []
    for p in purchases:
        c.execute("SELECT username, password, withdraw_password, real_name, bank_number, phone FROM accounts WHERE id = %s", (p[2],))
        acc = c.fetchone()
        if acc:
            # Chuyển đổi thời gian từ UTC sang VN
            try:
                from datetime import timezone
                utc_time = datetime.fromisoformat(p[5].replace('T', ' '))
                # Nếu là UTC, chuyển sang VN (UTC+7)
                if utc_time.tzinfo is None:
                    # Giả sử dữ liệu cũ là UTC, cộng thêm 7 giờ
                    vn_time = utc_time + timedelta(hours=7)
                else:
                    vn_time = utc_time.astimezone(VIETNAM_TZ)
                formatted_date = vn_time.strftime('%H:%M:%S %d/%m/%Y')
            except:
                formatted_date = p[5][:19].replace('T', ' ')
            
            history.append({
                'site': p[3],
                'username': acc[0],
                'password': acc[1],
                'withdraw_password': acc[2] or "Chưa có",
                'real_name': acc[3] or "Chưa có",
                'bank_number': acc[4] or "Chưa có",
                'phone': acc[5] or "Chưa có",
                'amount': p[4],
                'date': formatted_date
            })
    conn.close()
    return history

def get_all_users(limit: int = 50) -> List[Tuple]:
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT telegram_id, username, full_name, balance, total_recharge, total_spent, created_at FROM users ORDER BY balance DESC LIMIT %s", (limit,))
    users = c.fetchall()
    conn.close()
    return users

def get_user_count() -> int:
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    count = c.fetchone()[0]
    conn.close()
    return count

def get_daily_stats() -> Dict:
    conn = get_db_connection()
    c = conn.cursor()
    today = datetime.now(VIETNAM_TZ).date().isoformat()
    c.execute("SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM purchases WHERE DATE(purchased_at) = %s", (today,))
    sales_count, revenue = c.fetchone()
    c.execute("SELECT COUNT(*) FROM users WHERE DATE(created_at) = %s", (today,))
    new_users = c.fetchone()[0]
    conn.close()
    return {'sales': sales_count or 0, 'revenue': revenue or 0, 'new_users': new_users}

# ==================== REFERRAL ====================
import random
import string

def generate_ref_code(telegram_id: int) -> str:
    """Tạo mã giới thiệu duy nhất"""
    return f"REF{telegram_id}{''.join(random.choices(string.digits, k=4))}"

def get_user_by_ref_code(ref_code: str):
    """Tìm user theo mã giới thiệu"""
    if not ref_code or ref_code == "None" or ref_code == "null":
        return None
    conn = get_db_connection()
    c = conn.cursor()
    ref_code = ref_code.strip()
    c.execute("SELECT telegram_id FROM users WHERE ref_code = %s", (ref_code,))
    user = c.fetchone()
    conn.close()
    print(f"[DEBUG] Tìm ref_code '{ref_code}': {user[0] if user else 'Không tìm thấy'}")
    return user[0] if user else None

def add_ref_commission(user_id: int, ref_user_id: int, amount: int, note: str = ""):
    """Thêm hoa hồng cho người giới thiệu"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + %s, total_ref_commission = total_ref_commission + %s WHERE telegram_id = %s", 
              (amount, amount, ref_user_id))
    c.execute("INSERT INTO ref_commissions (user_id, ref_user_id, amount, note, created_at) VALUES (%s, %s, %s, %s, %s)",
              (user_id, ref_user_id, amount, note, datetime.now(VIETNAM_TZ).isoformat()))
    conn.commit()
    conn.close()
# ==================== THÔNG BÁO USER ====================
async def notify_user(user_id: int, title: str, message: str, success: bool = True):
    """Gửi thông báo đến user"""
    try:
        icon = "✅" if success else "❌"
        text = f"{icon} <b>{title}</b>\n\n{message}"
        await bot.send_message(user_id, text)
    except Exception as e:
        logger.error(f"Không thể gửi thông báo cho user {user_id}: {e}")
# ==================== BOT ====================
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

class AddAccountState(StatesGroup):
    waiting_for_site = State()
    waiting_for_account = State()

class MoneyState(StatesGroup):
    waiting_for_user = State()
    waiting_for_amount = State()

class PriceState(StatesGroup):
    waiting_for_site = State()
    waiting_for_price = State()
class RechargeState(StatesGroup):
    waiting_for_amount = State()
    waiting_for_bill = State()

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def main_menu(user_balance: int = 0):
    return ReplyKeyboardMarkup(
        keyboard=[
            # Dịch vụ chính
            [KeyboardButton(text="🛒 MUA ACC"), KeyboardButton(text="🔐 THUÊ OTP")],
            # Tiện ích
            [KeyboardButton(text="💰 SỐ DƯ"), KeyboardButton(text="📜 LỊCH SỬ"), KeyboardButton(text="💳 NẠP TIỀN")],
            # Khác
            [KeyboardButton(text="👥 GIỚI THIỆU"), KeyboardButton(text="👤 THÔNG TIN"), KeyboardButton(text="🆘 HỖ TRỢ")],
        ],
        resize_keyboard=True,
        input_field_placeholder="🔽 Chọn chức năng"
    )

def admin_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 DASHBOARD"), KeyboardButton(text="➕ THÊM ACC")],
            [KeyboardButton(text="📦 NHẬP NHIỀU"), KeyboardButton(text="🔍 TRA CỨU USER")],
            [KeyboardButton(text="💰 CỘNG TIỀN"), KeyboardButton(text="💸 TRỪ TIỀN")],
            [KeyboardButton(text="👥 DANH SÁCH USER"), KeyboardButton(text="📦 KHO ACC")],
            [KeyboardButton(text="💰 DOANH THU"), KeyboardButton(text="⚙️ CÀI GIÁ")],
            [KeyboardButton(text="🔙 QUAY LẠI MENU CHÍNH")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Chọn chức năng admin..."
    )
# ==================== XỬ LÝ MENU CHÍNH (REPLY KEYBOARD) ====================

@dp.message(F.text == "🛒 MUA ACC")
async def handle_buy(msg: Message):
    user = get_user(msg.from_user.id)
    balance = user[3] if user and isinstance(user[3], int) else 0
    
    inv = get_inventory()
    text = "🛒 <b>CHỌN SITE MUA ACC</b>\n\n"
    for site in SITES:
        price = SITE_PRICE.get(site, 20000)
        text += f"{SITE_EMOJI[site]} {site}: {price:,}đ/acc | ✅ {inv.get(site, 0)} còn\n"
    
    buttons = []
    for site in SITES:
        count = inv.get(site, 0)
        status = "✅" if count > 0 else "❌"
        buttons.append([InlineKeyboardButton(text=f"{SITE_EMOJI[site]} {site} {status} ({count})", callback_data=f"buy_{site}")])
    buttons.append([InlineKeyboardButton(text="🔙 Quay lại", callback_data="menu")])
    
    await msg.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.message(F.text == "🔐 THUÊ OTP")
async def handle_otp(msg: Message):
    # Đếm số OTP đang chờ từ database
    conn = get_db_connection()
    c = conn.cursor()
    time_limit = (datetime.now(VIETNAM_TZ) - timedelta(minutes=6)).isoformat()
    c.execute("""
        SELECT COUNT(*) FROM otp_rentals 
        WHERE user_id = %s AND status = 0 AND rented_at > %s
    """, (msg.from_user.id, time_limit))
    active_count = c.fetchone()[0]
    conn.close()
    
    text = f"""
🔐 <b>THUÊ OTP</b>

💰 <b>Giá mỗi số:</b> {OTP_PRICE:,}đ
📱 <b>Đang thuê:</b> {active_count} số

📋 <b>Chọn dịch vụ:</b>
"""
    await msg.answer(text, reply_markup=otp_service_menu())

@dp.message(F.text == "💰 SỐ DƯ")
async def handle_balance(msg: Message):
    user = get_user(msg.from_user.id)
    bal = user[3] if user and isinstance(user[3], int) else 0
    total_recharge = user[4] if user and isinstance(user[4], int) else 0
    total_spent = user[5] if user and isinstance(user[5], int) else 0
    
    text = f"""
💰 <b>SỐ DƯ CỦA BẠN</b>

💵 <b>Số dư:</b> {bal:,} VND
📥 <b>Tổng nạp:</b> {total_recharge:,} VND
📤 <b>Tổng chi:</b> {total_spent:,} VND
"""
    await msg.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Quay lại", callback_data="menu")]
    ]))

@dp.message(F.text == "📜 LỊCH SỬ")
async def handle_history(msg: Message):
    history = get_user_history(msg.from_user.id, limit=10)
    if not history:
        await msg.answer("📭 Bạn chưa mua acc nào!", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛒 Mua ngay", callback_data="buy")],
            [InlineKeyboardButton(text="🔙 Quay lại", callback_data="menu")]
        ]))
        return
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM purchases WHERE user_id = %s", (msg.from_user.id,))
    total_purchases = c.fetchone()[0]
    conn.close()
    
    text = f"📜 <b>LỊCH SỬ MUA HÀNG</b> <i>({len(history)}/{total_purchases} acc mới nhất)</i>\n\n"
    
    for i, h in enumerate(history, 1):
        try:
            dt = datetime.fromisoformat(h['date'].replace('T', ' '))
            formatted_date = dt.strftime('%H:%M:%S %d/%m/%Y')
        except:
            formatted_date = h['date']
        
        text += f"""🔹 <b>#{i}</b>
🎮 <b>Site:</b> {SITE_EMOJI[h['site']]} {h['site']}
👤 <b>Username:</b> <code>{h['username']}</code>
🔑 <b>Password:</b> <code>{h['password']}</code>
🔐 <b>MK Rút:</b> <code>{h.get('withdraw_password', 'Chưa có')}</code>
📝 <b>Tên thật:</b> {h.get('real_name', 'Chưa có')}
🏦 <b>STK:</b> {h.get('bank_number', 'Chưa có')}
📱 <b>SĐT:</b> {h.get('phone', 'Chưa có')}
💰 <b>Giá:</b> {h['amount']:,}đ
📅 <b>Ngày mua:</b> {formatted_date}

"""
    
    if total_purchases > 10:
        text += f"\n... và {total_purchases - 10} acc khác."
    
    await msg.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Mua tiếp", callback_data="buy")],
        [InlineKeyboardButton(text="🔙 Quay lại", callback_data="menu")]
    ]))

@dp.message(F.text == "💳 NẠP TIỀN")
async def handle_recharge(msg: Message, state: FSMContext):
    user = get_user(msg.from_user.id)
    balance = user[3] if user and isinstance(user[3], int) else 0
    
    await msg.answer(
        f"💳 <b>NẠP TIỀN VÀO TÀI KHOẢN</b>\n\n"
        f"💰 <b>Số dư hiện tại:</b> {balance:,}đ\n\n"
        f"📝 <b>Nhập số tiền muốn nạp:</b>\n"
        f"(Tối thiểu 20,000đ)\n\n"
        f"Gửi /cancel để hủy",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Quay lại", callback_data="menu")]
        ])
    )
    await state.set_state(RechargeState.waiting_for_amount)

@dp.message(F.text == "👥 GIỚI THIỆU")
async def handle_ref(msg: Message):
    user = get_user(msg.from_user.id)
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users WHERE ref_by = %s", (msg.from_user.id,))
    ref_count = c.fetchone()[0]
    c.execute("SELECT total_ref_commission, ref_code FROM users WHERE telegram_id = %s", (msg.from_user.id,))
    row = c.fetchone()
    total_commission = row[0] if row[0] else 0
    ref_code = row[1]
    conn.close()
    
    bot_username = (await bot.get_me()).username
    
    if not ref_code or ref_code == "None":
        ref_code = generate_ref_code(msg.from_user.id)
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("UPDATE users SET ref_code = %s WHERE telegram_id = %s", (ref_code, msg.from_user.id))
        conn.commit()
        conn.close()
    
    text = f"""
👥 <b>GIỚI THIỆU BẠN BÈ</b>

🔗 <b>Link giới thiệu:</b>
<code>https://t.me/{bot_username}?start={ref_code}</code>

📋 <b>Mã giới thiệu:</b>
<code>{ref_code}</code>

━━━━━━━━━━━━━━━━━━━━━━━
📊 <b>Thống kê của bạn:</b>
• Số người đã giới thiệu: {ref_count}
• Tổng hoa hồng nhận được: {total_commission:,}đ

💰 <b>Hoa hồng:</b> 5% mỗi lần người được giới thiệu nạp tiền

💡 <b>Hướng dẫn:</b>
1. Gửi link trên cho bạn bè
2. Bạn bè đăng ký qua link của bạn
3. Bạn nhận 5% hoa hồng từ mỗi lần họ nạp tiền
"""
    await msg.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Quay lại", callback_data="menu")]
    ]))

@dp.message(F.text == "👤 THÔNG TIN")
async def handle_myinfo(msg: Message):
    user = get_user(msg.from_user.id)
    if not user:
        await msg.answer("❌ Không tìm thấy thông tin!")
        return
    
    balance = user[3] if isinstance(user[3], int) else 0
    total_recharge = user[4] if isinstance(user[4], int) else 0
    total_spent = user[5] if isinstance(user[5], int) else 0
    
    if user[6]:
        try:
            dt = datetime.fromisoformat(user[6].replace('T', ' '))
            created_at = dt.strftime('%H:%M:%S %d/%m/%Y')
        except:
            created_at = user[6][:19].replace('T', ' ')
    else:
        created_at = "Không rõ"
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM purchases WHERE user_id = %s", (msg.from_user.id,))
    purchase_count = c.fetchone()[0]
    conn.close()
    
    text = f"""
👤 <b>THÔNG TIN CỦA BẠN</b>

🆔 <b>User ID:</b> <code>{msg.from_user.id}</code>
📝 <b>Tên:</b> {msg.from_user.full_name}
💬 <b>Username:</b> @{msg.from_user.username or 'chưa có'}

━━━━━━━━━━━━━━━━━━━━━━━
💰 <b>Số dư:</b> {balance:,}đ
📥 <b>Tổng nạp:</b> {total_recharge:,}đ
📤 <b>Tổng chi:</b> {total_spent:,}đ
📦 <b>Số lần mua:</b> {purchase_count}

📅 <b>Ngày tham gia:</b> {created_at}
"""
    
    await msg.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Quay lại", callback_data="menu")]
    ]))

@dp.message(F.text == "🆘 HỖ TRỢ")
async def handle_support(msg: Message):
    buttons = []
    for username in ADMIN_USERNAMES:
        buttons.append([InlineKeyboardButton(text=f"📩 @{username}", url=f"https://t.me/{username}")])
    buttons.append([InlineKeyboardButton(text="🔙 Quay lại", callback_data="menu")])
    
    support_text = f"""
🆘 <b>HỖ TRỢ KHÁCH HÀNG</b>

📌 <b>Các vấn đề cần hỗ trợ:</b>
• 🎮 Lỗi đăng nhập account
• 💳 Nạp tiền chưa nhận được
• 🔐 Quên mật khẩu rút tiền
• 📝 Khiếu nại, thắc mắc khác

━━━━━━━━━━━━━━━━━━━━

<b>📞 Liên hệ admin:</b>
Bấm vào tên admin bên dưới để chat trực tiếp!

⏳ <b>Thời gian phản hồi:</b> 8h - 22h hàng ngày

💡 <b>Lưu ý:</b> Ghi rõ vấn đề và kèm ảnh/video nếu có
"""
    await msg.answer(support_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.message(F.text == "🔙 QUAY LẠI MENU CHÍNH")
async def handle_back_to_main(msg: Message):
    user = get_user(msg.from_user.id)
    balance = user[3] if user and isinstance(user[3], int) else 0
    await msg.answer("🏠 <b>MENU CHÍNH</b>\n\n👇 Chọn chức năng:", reply_markup=main_menu(balance))
# ==================== XỬ LÝ MENU ADMIN (REPLY KEYBOARD) ====================

@dp.message(F.text == "📊 DASHBOARD")
async def handle_admin_dashboard(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        await msg.answer("⛔ Không có quyền!")
        return
    fake_call = types.CallbackQuery(id="1", from_user=msg.from_user, chat_instance="1", data="admin_dashboard", message=msg)
    await admin_dash(fake_call)

@dp.message(F.text == "➕ THÊM ACC")
async def handle_admin_add(msg: Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        await msg.answer("⛔ Không có quyền!")
        return
    fake_call = types.CallbackQuery(id="1", from_user=msg.from_user, chat_instance="1", data="admin_add", message=msg)
    await admin_add_menu(fake_call, state)

@dp.message(F.text == "📦 NHẬP NHIỀU")
async def handle_admin_bulk(msg: Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        await msg.answer("⛔ Không có quyền!")
        return
    fake_call = types.CallbackQuery(id="1", from_user=msg.from_user, chat_instance="1", data="admin_bulk_add", message=msg)
    await admin_bulk_add(fake_call, state)

@dp.message(F.text == "🔍 TRA CỨU USER")
async def handle_admin_search(msg: Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        await msg.answer("⛔ Không có quyền!")
        return
    fake_call = types.CallbackQuery(id="1", from_user=msg.from_user, chat_instance="1", data="admin_search_user", message=msg)
    await admin_search_user(fake_call, state)

@dp.message(F.text == "💰 CỘNG TIỀN")
async def handle_admin_add_money(msg: Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        await msg.answer("⛔ Không có quyền!")
        return
    fake_call = types.CallbackQuery(id="1", from_user=msg.from_user, chat_instance="1", data="admin_add_money", message=msg)
    await admin_add_money(fake_call, state)

@dp.message(F.text == "💸 TRỪ TIỀN")
async def handle_admin_sub_money(msg: Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        await msg.answer("⛔ Không có quyền!")
        return
    fake_call = types.CallbackQuery(id="1", from_user=msg.from_user, chat_instance="1", data="admin_sub_money", message=msg)
    await admin_sub_money(fake_call, state)

@dp.message(F.text == "👥 DANH SÁCH USER")
async def handle_admin_users(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        await msg.answer("⛔ Không có quyền!")
        return
    fake_call = types.CallbackQuery(id="1", from_user=msg.from_user, chat_instance="1", data="admin_users", message=msg)
    await admin_users(fake_call)

@dp.message(F.text == "📦 KHO ACC")
async def handle_admin_inventory(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        await msg.answer("⛔ Không có quyền!")
        return
    fake_call = types.CallbackQuery(id="1", from_user=msg.from_user, chat_instance="1", data="admin_inventory", message=msg)
    await admin_inventory(fake_call)

@dp.message(F.text == "💰 DOANH THU")
async def handle_admin_revenue(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        await msg.answer("⛔ Không có quyền!")
        return
    fake_call = types.CallbackQuery(id="1", from_user=msg.from_user, chat_instance="1", data="admin_revenue", message=msg)
    await admin_revenue(fake_call)

@dp.message(F.text == "⚙️ CÀI GIÁ")
async def handle_admin_price(msg: Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        await msg.answer("⛔ Không có quyền!")
        return
    fake_call = types.CallbackQuery(id="1", from_user=msg.from_user, chat_instance="1", data="admin_price", message=msg)
    await admin_price_menu(fake_call, state)

@dp.message(F.text == "🔙 QUAY LẠI MENU CHÍNH")
async def handle_admin_back_to_main(msg: Message):
    user = get_user(msg.from_user.id)
    balance = user[3] if user and isinstance(user[3], int) else 0
    await msg.answer("🏠 <b>MENU CHÍNH</b>\n\n👇 Chọn chức năng:", reply_markup=main_menu(balance))
@dp.callback_query(F.data == "ref_info")
async def ref_info_callback(call: CallbackQuery):
    user = get_user(call.from_user.id)
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users WHERE ref_by = %s", (call.from_user.id,))
    ref_count = c.fetchone()[0]
    c.execute("SELECT total_ref_commission, ref_code FROM users WHERE telegram_id = %s", (call.from_user.id,))
    row = c.fetchone()
    total_commission = row[0] if row[0] else 0
    ref_code = row[1]
    conn.close()
    
    bot_username = (await bot.get_me()).username
    
    # Nếu ref_code bị None, tạo mới
    if not ref_code or ref_code == "None":
        ref_code = generate_ref_code(call.from_user.id)
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("UPDATE users SET ref_code = %s WHERE telegram_id = %s", (ref_code, call.from_user.id))
        conn.commit()
        conn.close()
        print(f"[DEBUG] Đã tạo ref_code mới cho user {call.from_user.id}: {ref_code}")
    
    text = f"""
👥 <b>GIỚI THIỆU BẠN BÈ</b>

🔗 <b>Link giới thiệu:</b>
<code>https://t.me/{bot_username}?start={ref_code}</code>

📋 <b>Mã giới thiệu:</b>
<code>{ref_code}</code>

━━━━━━━━━━━━━━━━━━━━━━━
📊 <b>Thống kê của bạn:</b>
• Số người đã giới thiệu: {ref_count}
• Tổng hoa hồng nhận được: {total_commission:,}đ

💰 <b>Hoa hồng:</b> 5% mỗi lần người được giới thiệu nạp tiền

💡 <b>Hướng dẫn:</b>
1. Gửi link trên cho bạn bè
2. Bạn bè đăng ký qua link của bạn
3. Bạn nhận 5% hoa hồng từ mỗi lần họ nạp tiền
"""
    await call.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Quay lại", callback_data="menu")]
    ]))
# ==================== USER ====================
@dp.message(Command("start"))
async def start(msg: Message):
    # Xử lý mã giới thiệu
    args = msg.text.split()
    ref_code = args[1] if len(args) > 1 else None
    
    print(f"[DEBUG] User {msg.from_user.id} start với ref_code: {ref_code}")
    
    ref_by = None
    if ref_code and ref_code != "None" and ref_code != "null":
        ref_by = get_user_by_ref_code(ref_code)
        print(f"[DEBUG] Tìm thấy ref_by: {ref_by}")
        if ref_by == msg.from_user.id:
            ref_by = None
            print(f"[DEBUG] Không tự giới thiệu chính mình")
    
    # Kiểm tra user đã tồn tại chưa
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT telegram_id FROM users WHERE telegram_id = %s", (msg.from_user.id,))
    existing_user = c.fetchone()
    conn.close()
    
    if existing_user:
        # User đã tồn tại, không cập nhật ref_by
        print(f"[DEBUG] User {msg.from_user.id} đã tồn tại, bỏ qua ref_by")
        user = get_user(msg.from_user.id, msg.from_user.username, msg.from_user.full_name)
    else:
        # User mới, cập nhật ref_by
        print(f"[DEBUG] Tạo user mới {msg.from_user.id} với ref_by={ref_by}")
        user = get_user(msg.from_user.id, msg.from_user.username, msg.from_user.full_name, ref_by)
    
    balance = user[3] if user and isinstance(user[3], int) else 0
    
    welcome_text = f"""
🎉 <b>CHÀO MỪNG {msg.from_user.first_name}!</b>

💰 <b>Số dư:</b> {balance:,}đ
🎮 <b>Giá mỗi acc:</b> 20,000đ
📦 <b>Các site:</b> {', '.join(SITES)}

💡 <b>Hướng dẫn:</b>
• Chọn MUA ACC để mua tài khoản
• Lưu ý: Mọi người khi mua acc quay video từ lúc mua tới lúc đăng nhập để được bảo hành nhé!

👇 <b>Chọn chức năng:</b>
"""
    await msg.answer(welcome_text, reply_markup=main_menu(balance))

@dp.callback_query(F.data == "balance")
async def show_balance(call: CallbackQuery):
    user = get_user(call.from_user.id)
    bal = user[3] if user and isinstance(user[3], int) else 0
    total_recharge = user[4] if user and isinstance(user[4], int) else 0
    total_spent = user[5] if user and isinstance(user[5], int) else 0
    
    text = f"""
💰 <b>SỐ DƯ CỦA BẠN</b>

💵 <b>Số dư:</b> {bal:,} VND
📥 <b>Tổng nạp:</b> {total_recharge:,} VND
📤 <b>Tổng chi:</b> {total_spent:,} VND
"""
    await call.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Quay lại", callback_data="menu")]
    ]))
    try:
        await call.message.delete()
    except:
        pass

@dp.callback_query(F.data == "buy")
async def buy_menu(call: CallbackQuery):
    inv = get_inventory()
    text = "🛒 <b>CHỌN SITE MUA ACC</b>\n\n"
    for site in SITES:
        price = SITE_PRICE.get(site, 20000)
        text += f"{SITE_EMOJI[site]} {site}: {price:,}đ/acc | ✅ {inv.get(site, 0)} còn\n"
    
    buttons = []
    for site in SITES:
        count = inv.get(site, 0)
        status = "✅" if count > 0 else "❌"
        buttons.append([InlineKeyboardButton(text=f"{SITE_EMOJI[site]} {site} {status} ({count})", callback_data=f"buy_{site}")])
    buttons.append([InlineKeyboardButton(text="🔙 Quay lại", callback_data="menu")])
    
    await call.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    try:
        await call.message.delete()
    except:
        pass

@dp.callback_query(F.data.startswith("buy_"))
async def process_buy(call: CallbackQuery):
    site = call.data.split("_")[1]
    user = get_user(call.from_user.id)
    balance = user[3] if user and isinstance(user[3], int) else 0
    price = SITE_PRICE.get(site, 20000)
    
    if balance < price:
        await call.answer(f"❌ Số dư không đủ! Cần {price:,}đ. Bạn có {balance:,}đ", show_alert=True)
        return
    
    account = get_available_account(site)
    if not account:
        await call.answer(f"❌ Site {site} đã hết hàng!", show_alert=True)
        return
    
    update_balance(call.from_user.id, -price, f"Mua acc {site}")
    mark_sold(account[0], call.from_user.id)
    save_purchase(call.from_user.id, account[0], site, price)
    
    # Gửi thông báo cho admin
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"🛒 <b>CÓ USER MUA ACC</b>\n\n"
                f"👤 User: {call.from_user.id} (@{call.from_user.username or 'no username'})\n"
                f"📝 Tên: {call.from_user.full_name}\n"
                f"🎮 Site: {SITE_EMOJI[site]} {site}\n"
                f"👤 Username: {account[2]}\n"
                f"🔑 Password: {account[3]}\n"
                f"💰 Giá: {price:,}đ\n"
                f"📅 Thời gian: {datetime.now(VIETNAM_TZ).strftime('%H:%M:%S %d/%m/%Y')}"
            )
        except:
            pass
    
    new_balance = balance - price
    
    # Lấy thêm thông tin từ account (index trong tuple)
    # account = (id, site, username, password, withdraw_password, real_name, bank_number, phone, ...)
    username = account[2]
    password = account[3]
    withdraw_password = account[4] if len(account) > 4 and account[4] else "Chưa có"
    real_name = account[5] if len(account) > 5 and account[5] else "Chưa có"
    bank_number = account[6] if len(account) > 6 and account[6] else "Chưa có"
    phone = account[7] if len(account) > 7 and account[7] else "Chưa có"
    
    await call.message.edit_text(
        f"✅ <b>MUA THÀNH CÔNG!</b>\n\n"
        f"🎮 <b>Site:</b> {SITE_EMOJI[site]} {site}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Username:</b> <code>{username}</code>\n"
        f"🔑 <b>Password:</b> <code>{password}</code>\n"
        f"🔐 <b>MK Rút:</b> <code>{withdraw_password}</code>\n"
        f"📝 <b>Tên thật:</b> {real_name}\n"
        f"🏦 <b>STK:</b> {bank_number}\n"
        f"📱 <b>SĐT:</b> {phone}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Giá:</b> {price:,}đ\n"
        f"💵 <b>Số dư còn:</b> {new_balance:,}đ",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛒 Mua tiếp", callback_data="buy")],
            [InlineKeyboardButton(text="🏠 Menu", callback_data="menu")]
        ])
    )

@dp.callback_query(F.data == "history")
async def show_history(call: CallbackQuery):
    history = get_user_history(call.from_user.id, limit=10)
    if not history:
        await call.message.answer("📭 Bạn chưa mua acc nào!", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛒 Mua ngay", callback_data="buy")],
            [InlineKeyboardButton(text="🔙 Quay lại", callback_data="menu")]
        ]))
        return
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM purchases WHERE user_id = %s", (call.from_user.id,))
    total_purchases = c.fetchone()[0]
    conn.close()
    
    text = f"📜 <b>LỊCH SỬ MUA HÀNG</b> <i>({len(history)}/{total_purchases} acc mới nhất)</i>\n\n"
    
    for i, h in enumerate(history, 1):
        try:
            dt = datetime.fromisoformat(h['date'].replace('T', ' '))
            formatted_date = dt.strftime('%H:%M:%S %d/%m/%Y')
        except:
            formatted_date = h['date']
        
        text += f"""🔹 <b>#{i}</b>
🎮 <b>Site:</b> {SITE_EMOJI[h['site']]} {h['site']}
👤 <b>Username:</b> <code>{h['username']}</code>
🔑 <b>Password:</b> <code>{h['password']}</code>
🔐 <b>MK Rút:</b> <code>{h.get('withdraw_password', 'Chưa có')}</code>
📝 <b>Tên thật:</b> {h.get('real_name', 'Chưa có')}
🏦 <b>STK:</b> {h.get('bank_number', 'Chưa có')}
📱 <b>SĐT:</b> {h.get('phone', 'Chưa có')}
💰 <b>Giá:</b> {h['amount']:,}đ
📅 <b>Ngày mua:</b> {formatted_date}

"""
    
    if total_purchases > 10:
        text += f"\n... và {total_purchases - 10} acc khác."
    
    await call.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Mua tiếp", callback_data="buy")],
        [InlineKeyboardButton(text="🔙 Quay lại", callback_data="menu")]
    ]))
    try:
        await call.message.delete()
    except:
        pass

# ==================== THUÊ OTP (OKEDA - 5 SITE) ====================
import asyncio
import aiohttp
import json

# Cấu hình OKVIP API
OKVIP_TOKEN = "239e39474dfb4e72903ff527c2b26d46"
OKVIP_API_URL = "https://api.viotp.com"
# ==================== CẤU HÌNH HupSMS ====================
HUPSMS_API_KEY = "hup_MHaWCuF_3vWeYQdrnhQP1I4UEScX6XoZSoGKZ-ZJ1OS-ZEVd"
HUPSMS_API_URL = "https://hupsms.com/api/v1"
HUPSMS_PRICE = 2680  # Giá thuê SMS VIP
HUPSMS_SERVER = 3  # Server 3
HUPSMS_SERVICE_NAME = "Test 3"  # Dịch vụ Test 3
# Service ID của Okeda (tự động lấy từ API)
OKEDA_SERVICE_ID = None

# Giá thuê OTP
OTP_PRICE = 2520

# Danh sách 5 dịch vụ (chỉ để hiển thị, tất cả đều dùng OKEDA)
OTP_SERVICES = ["CM88", "SC88", "FLY88", "F168", "C168"]
OTP_SERVICE_EMOJI = {"CM88": "🎰", "SC88": "🎲", "FLY88": "✈️", "F168": "🏆", "C168": "🃏"}

# Dịch vụ SMS VIP (riêng)
SMS_VIP_SERVICES = ["SMS VIP"]
SMS_VIP_EMOJI = {"SMS VIP": "💎"}

# Lưu trữ nhiều phiên thuê OTP (cho phép nhiều số cùng lúc)
# Cấu trúc: {user_id: [session1, session2, ...]}
otp_sessions = {}

async def call_viotp_api(endpoint: str, params: dict = None) -> dict:
    """Gọi API ViOTP"""
    if params is None:
        params = {}
    params['token'] = OKVIP_TOKEN
    url = f"{OKVIP_API_URL}/{endpoint}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            return await resp.json()

async def get_okeda_service_id() -> int:
    """Lấy service ID của Okeda từ API"""
    global OKEDA_SERVICE_ID
    if OKEDA_SERVICE_ID:
        return OKEDA_SERVICE_ID
    
    result = await call_viotp_api("service/getv2", {"country": "vn"})
    if result.get('success'):
        services = result.get('data', [])
        for sv in services:
            if 'okeda' in sv.get('name', '').lower():
                OKEDA_SERVICE_ID = sv.get('id')
                print(f"✅ Tìm thấy OKEDA Service ID: {OKEDA_SERVICE_ID}")
                return OKEDA_SERVICE_ID
    print("❌ Không tìm thấy OKEDA trong danh sách dịch vụ")
    return None

def otp_service_menu():
    """Menu chọn dịch vụ OTP và SMS VIP"""
    buttons = []
    # Các dịch vụ OTP thường
    for i in range(0, len(OTP_SERVICES), 2):
        row = []
        row.append(InlineKeyboardButton(text=f"{OTP_SERVICE_EMOJI[OTP_SERVICES[i]]} {OTP_SERVICES[i]}", callback_data=f"otp_buy_{OTP_SERVICES[i]}"))
        if i + 1 < len(OTP_SERVICES):
            row.append(InlineKeyboardButton(text=f"{OTP_SERVICE_EMOJI[OTP_SERVICES[i+1]]} {OTP_SERVICES[i+1]}", callback_data=f"otp_buy_{OTP_SERVICES[i+1]}"))
        buttons.append(row)
    
    # Thêm dòng SMS VIP
    buttons.append([InlineKeyboardButton(text=f"{SMS_VIP_EMOJI['SMS VIP']} SMS VIP (2680đ)", callback_data="sms_vip_buy")])
    
    # Hàng cuối: 2 nút chức năng
    buttons.append([InlineKeyboardButton(text="📜 Lịch sử thuê", callback_data="otp_history"), InlineKeyboardButton(text="🔙 Quay lại", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@dp.callback_query(F.data == "otp_menu")
async def otp_service_handler(call: CallbackQuery):
    """Hiển thị menu chọn 5 dịch vụ OTP"""
    
    # Kiểm tra và đồng bộ session từ database
    conn = get_db_connection()
    c = conn.cursor()
    
    # Lấy các OTP đang chờ (status = 0) và chưa quá 6 phút
    time_limit = (datetime.now(VIETNAM_TZ) - timedelta(minutes=6)).isoformat()
    c.execute("""
        SELECT request_id, phone_number, service_name, rented_at 
        FROM otp_rentals 
        WHERE user_id = %s AND status = 0 AND rented_at > %s
    """, (call.from_user.id, time_limit))
    db_sessions = c.fetchall()
    conn.close()
    
    # Đồng bộ với otp_sessions trong RAM
    if call.from_user.id not in otp_sessions:
        otp_sessions[call.from_user.id] = []
    
    # Xóa session cũ trong RAM không còn trong DB
    current_session_ids = [s['request_id'] for s in otp_sessions.get(call.from_user.id, [])]
    db_session_ids = [s[0] for s in db_sessions]
    
    for session_id in current_session_ids:
        if session_id not in db_session_ids:
            # Xóa session không còn trong DB
            otp_sessions[call.from_user.id] = [s for s in otp_sessions[call.from_user.id] if s['request_id'] != session_id]
    
    # Thêm session từ DB vào RAM nếu chưa có
    for db_s in db_sessions:
        if db_s[0] not in current_session_ids:
            otp_sessions[call.from_user.id].append({
                'id': f"{db_s[2]}_{db_s[0]}_{int(datetime.now().timestamp())}",
                'service': db_s[2],
                'request_id': db_s[0],
                'phone': db_s[1],
                'start_time': datetime.fromisoformat(db_s[3])
            })
    
    if not otp_sessions.get(call.from_user.id):
        otp_sessions[call.from_user.id] = []
    
    # Đếm số phiên đang thuê
    user_sessions = otp_sessions.get(call.from_user.id, [])
    active_count = len(user_sessions)
    
    text = f"""
🔐 <b>THUÊ OTP</b>

💰 <b>Giá mỗi số:</b> {OTP_PRICE:,}đ
📱 <b>Đang thuê:</b> {active_count} số

📋 <b>Chọn dịch vụ:</b>
"""
    await call.message.answer(text, reply_markup=otp_service_menu())

@dp.callback_query(F.data.startswith("otp_buy_"))
async def otp_buy_handler(call: CallbackQuery):
    """Xử lý thuê OTP - Tất cả site đều dùng OKEDA, cho phép thuê nhiều số cùng lúc"""
    service = call.data.split("_")[2]  # CM88, SC88, FLY88, F168, C168
    
    user = get_user(call.from_user.id)
    balance = user[3] if isinstance(user[3], int) else 0
    
    if balance < OTP_PRICE:
        await call.answer(f"❌ Số dư không đủ! Cần {OTP_PRICE:,}đ. Bạn có {balance:,}đ", show_alert=True)
        return
    
    # Lấy service ID của Okeda
    service_id = await get_okeda_service_id()
    if not service_id:
        await call.answer("❌ Không tìm thấy dịch vụ ! Vui lòng liên hệ Admin.", show_alert=True)
        return
    
    # Gọi API thuê số OTP - DÙNG CHUNG OKEDA
    result = await call_viotp_api("request/getv2", {"serviceId": service_id})
    
    if not result.get('success'):
        error_msg = result.get('message', 'Lỗi không xác định')
        await call.answer(f"❌ Lỗi API : {error_msg}", show_alert=True)
        return
    
    data = result.get('data', {})
    phone = data.get('phone_number')
    re_phone_number = data.get('re_phone_number')  # Thêm dòng này
    request_id = data.get('request_id')
    
    if not phone or not request_id:
        await call.answer("❌ Không lấy được số điện thoại từ API!", show_alert=True)
        return
    
    # Trừ tiền SAU KHI API thành công
    update_balance(call.from_user.id, -OTP_PRICE, f"Thuê OTP {service}")
    new_balance = balance - OTP_PRICE
    
    # Tạo session mới
    session_id = f"{service}_{request_id}_{int(datetime.now().timestamp())}"
    session = {
        'id': session_id,
        'service': service,
        'request_id': request_id,
        'phone': phone,
        'start_time': datetime.now(VIETNAM_TZ)
    }
    
    # Thêm vào danh sách session của user (cho phép nhiều số)
    if call.from_user.id not in otp_sessions:
        otp_sessions[call.from_user.id] = []
    otp_sessions[call.from_user.id].append(session)
    
    current_time = datetime.now(VIETNAM_TZ).strftime("%H:%M:%S %d/%m/%Y")
    active_count = len(otp_sessions[call.from_user.id])
    
    # Gửi tin nhắn báo thuê thành công (HIỂN THỊ ĐẦY ĐỦ SDT + DỊCH VỤ + THỜI GIAN)
    await call.message.answer(
        f"✅ <b>THUÊ OTP THÀNH CÔNG!</b>\n\n"
        f"🎮 <b>Dịch vụ:</b> {OTP_SERVICE_EMOJI[service]} {service}\n"
        f"📱 <b>Số điện thoại:</b> <code>{phone}</code>\n"
        f"⏰ <b>Thời gian:</b> {current_time}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Giá:</b> {OTP_PRICE:,}đ\n"
        f"💵 <b>Số dư còn:</b> {new_balance:,}đ\n"
        f"📊 <b>Đang thuê:</b> {active_count} số\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⏳ <b>Đang chờ OTP...</b> (tối đa 6 phút/số)\n"
        f"💡 Bạn có thể <b>thuê thêm số khác</b> ngay bây giờ!\n\n"
        f"📌 <b>Lưu ý:</b> Hãy xin lại OTP vài lần để tăng tỉ lệ mã về nhé!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔐 Thuê tiếp số khác", callback_data="otp_menu")],
            [InlineKeyboardButton(text="📜 Lịch sử thuê", callback_data="otp_history")],
            [InlineKeyboardButton(text="🏠 Menu", callback_data="menu")]
        ])
    )
    
    # Chạy vòng lặp check OTP riêng cho từng session
    asyncio.create_task(check_otp_loop(call.from_user.id, session_id, request_id, service, phone))

@dp.callback_query(F.data == "sms_vip_buy")
async def sms_vip_buy_handler(call: CallbackQuery):
    """Xử lý thuê SMS VIP từ HupSMS"""
    service = "SMS VIP"
    
    user = get_user(call.from_user.id)
    balance = user[3] if isinstance(user[3], int) else 0
    
    if balance < HUPSMS_PRICE:
        await call.answer(f"❌ Số dư không đủ! Cần {HUPSMS_PRICE:,}đ. Bạn có {balance:,}đ", show_alert=True)
        return
    
    # Gọi API thuê SMS
    result = await rent_hupsms_sms()
    
    if not result:
        await call.answer("❌ Không thể thuê SMS VIP! Vui lòng thử lại sau.", show_alert=True)
        return
    
    phone = format_phone_number(result.get('phone'))  # Bỏ số 0 đầu
    order_id = result.get('orderId')
    price = result.get('price', HUPSMS_PRICE)
    
    if not phone or not order_id:
        await call.answer("❌ Không lấy được số điện thoại từ API!", show_alert=True)
        return
    
    # Trừ tiền
    update_balance(call.from_user.id, -HUPSMS_PRICE, f"Thuê SMS VIP - số {phone}")
    new_balance = balance - HUPSMS_PRICE
    
    # Tạo session
    session_id = f"SMSVIP_{order_id}_{int(datetime.now().timestamp())}"
    session = {
        'id': session_id,
        'service': service,
        'request_id': order_id,
        'phone': phone,
        'start_time': datetime.now(VIETNAM_TZ),
        'api_type': 'hupsms'  # Đánh dấu là từ HupSMS
    }
    
    if call.from_user.id not in otp_sessions:
        otp_sessions[call.from_user.id] = []
    otp_sessions[call.from_user.id].append(session)
    
    current_time = datetime.now(VIETNAM_TZ).strftime("%H:%M:%S %d/%m/%Y")
    active_count = len(otp_sessions[call.from_user.id])
    
    await call.message.answer(
        f"✅ <b>THUÊ SMS VIP THÀNH CÔNG!</b>\n\n"
        f"💎 <b>Dịch vụ:</b> SMS VIP\n"
        f"📱 <b>Số điện thoại:</b> <code>{phone}</code>\n"
        f"⏰ <b>Thời gian:</b> {current_time}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Giá:</b> {HUPSMS_PRICE:,}đ\n"
        f"💵 <b>Số dư còn:</b> {new_balance:,}đ\n"
        f"📊 <b>Đang thuê:</b> {active_count} số\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⏳ <b>Đang chờ SMS...</b> (tối đa 6 phút)\n"
        f"🔄 Hệ thống tự động kiểm tra mỗi 2 giây\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Chính sách hoàn tiền:</b>\n"
        f"• Nếu sau 6 phút không nhận được SMS\n"
        f"• Hệ thống sẽ <b>TỰ ĐỘNG HOÀN TIỀN</b>\n"
        f"• Số tiền {HUPSMS_PRICE:,}đ sẽ được cộng lại\n\n"
        f"💡 Bạn có thể <b>thuê thêm số khác</b> ngay bây giờ!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔐 Thuê tiếp số khác", callback_data="otp_menu")],
            [InlineKeyboardButton(text="📜 Lịch sử thuê", callback_data="otp_history")],
            [InlineKeyboardButton(text="🏠 Menu", callback_data="menu")]
        ])
    )
    
    # Chạy vòng lặp check OTP cho HupSMS
    asyncio.create_task(check_hupsms_loop(call.from_user.id, session_id, order_id, service, phone))
async def check_hupsms_loop(user_id: int, session_id: str, order_id: str, service: str, phone: str):
    """Vòng lặp check OTP từ HupSMS mỗi 2 giây, tự động hoàn tiền sau 6 phút"""
    start_time = datetime.now(VIETNAM_TZ)
    timeout_minutes = 6
    
    while True:
        elapsed = (datetime.now(VIETNAM_TZ) - start_time).total_seconds() / 60
        
        # Hết 6 phút -> hoàn tiền
        if elapsed >= timeout_minutes:
            update_balance(user_id, HUPSMS_PRICE, f"Hoàn tiền thuê SMS VIP - hết 6 phút")
            
            await bot.send_message(
                user_id,
                f"❌ <b>HẾT THỜI GIAN CHỜ SMS</b>\n\n"
                f"💎 <b>Dịch vụ:</b> SMS VIP\n"
                f"📱 <b>Số:</b> <code>{phone}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"⏰ Đã chờ {timeout_minutes} phút nhưng không nhận được SMS.\n"
                f"💰 <b>Đã hoàn tiền:</b> {HUPSMS_PRICE:,}đ\n"
                f"💡 Vui lòng thử lại sau!"
            )
            
            # Xóa session
            if user_id in otp_sessions:
                otp_sessions[user_id] = [s for s in otp_sessions[user_id] if s['id'] != session_id]
                if not otp_sessions[user_id]:
                    del otp_sessions[user_id]
            return
        
        # Gọi API check OTP
        try:
            result = await check_hupsms_otp(order_id)
            
            if result.get('status') == 'success':
                otp_code = result.get('otp')
                sms_content = result.get('smsContent', '')
                is_voice = result.get('is_voice_otp', False)
                audio_url = result.get('audio_url', '')
                
                if otp_code:
                    # Lưu vào database
                    conn = get_db_connection()
                    c = conn.cursor()
                    c.execute("""
                        INSERT INTO otp_rentals (user_id, request_id, phone_number, service_name, price, code, sms_content, status, rented_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (user_id, order_id, phone, f"SMS VIP", HUPSMS_PRICE, otp_code, sms_content, 1, datetime.now(VIETNAM_TZ).isoformat()))
                    conn.commit()
                    conn.close()
                    
                    # Gửi thông báo cho admin
                    # Trong check_hupsms_loop, khi gửi thông báo cho admin
                    for admin_id in ADMIN_IDS:
                        profit = HUPSMS_PRICE - 2000  # 2680 - 2000 = 680đ
                        await bot.send_message(
                            admin_id,
                            f"🔐 <b>CÓ SMS VIP MỚI</b>\n\n"
                            f"👤 User: {user_id}\n"
                            f"💎 DV: SMS VIP\n"
                            f"📱 Số: {phone}\n"
                            f"🔑 Mã: {otp_code}\n"
                            f"🎵 Audio: {is_voice}\n"
                            f"💰 Lợi nhuận: {profit:,}đ"
                        )
                    
                    # Gửi thông báo cho user (kèm menu thuê lại)
                    if is_voice and audio_url:
                        await bot.send_message(
                            user_id,
                            f"✅ <b>NHẬN MÃ SMS VIP THÀNH CÔNG!</b>\n\n"
                            f"💎 <b>Dịch vụ:</b> SMS VIP\n"
                            f"📱 <b>Số điện thoại:</b> <code>{phone}</code>\n"
                            f"🔑 <b>Mã:</b> <code>{otp_code}</code>\n"
                            f"🎵 <b>Audio:</b> <a href='{audio_url}'>Nhấn để nghe</a>\n"
                            f"📝 <b>Nội dung:</b> {sms_content[:100]}\n"
                            f"━━━━━━━━━━━━━━━━━━━━\n"
                            f"💰 <b>Giá thuê mới:</b> {HUPSMS_PRICE:,}đ\n"
                            f"♻️ <b>Giá thuê lại:</b> 3,600đ\n"
                            f"⏱️ <b>Thời gian nhận:</b> {int(elapsed * 60)} giây\n\n"
                            f"⚠️ Mã có hiệu lực trong 2 phút!",
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                [InlineKeyboardButton(text="♻️ THUÊ LẠI SỐ NÀY (3,600đ)", callback_data=f"sms_vip_rent_again_{order_id}_{phone}")],
                                [InlineKeyboardButton(text="💎 Thuê SMS VIP mới", callback_data="otp_menu")],
                                [InlineKeyboardButton(text="🏠 Menu", callback_data="menu")]
                            ])
                        )
                    else:
                        await bot.send_message(
                            user_id,
                            f"✅ <b>NHẬN MÃ SMS VIP THÀNH CÔNG!</b>\n\n"
                            f"💎 <b>Dịch vụ:</b> SMS VIP\n"
                            f"📱 <b>Số điện thoại:</b> <code>{phone}</code>\n"
                            f"🔑 <b>Mã:</b> <code>{otp_code}</code>\n"
                            f"📝 <b>Nội dung:</b> {sms_content[:200]}\n"
                            f"━━━━━━━━━━━━━━━━━━━━\n"
                            f"💰 <b>Giá thuê mới:</b> {HUPSMS_PRICE:,}đ\n"
                            f"♻️ <b>Giá thuê lại:</b> 3,600đ\n"
                            f"⏱️ <b>Thời gian nhận:</b> {int(elapsed * 60)} giây\n\n"
                            f"⚠️ Mã có hiệu lực trong 2 phút!",
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                [InlineKeyboardButton(text="♻️ THUÊ LẠI SỐ NÀY (3,600đ)", callback_data=f"sms_vip_rent_again_{order_id}_{phone}")],
                                [InlineKeyboardButton(text="💎 Thuê SMS VIP mới", callback_data="otp_menu")],
                                [InlineKeyboardButton(text="🏠 Menu", callback_data="menu")]
                            ])
                        )
                    
                    # Xóa session
                    if user_id in otp_sessions:
                        otp_sessions[user_id] = [s for s in otp_sessions[user_id] if s['id'] != session_id]
                        if not otp_sessions[user_id]:
                            del otp_sessions[user_id]
                    return
        except Exception as e:
            print(f"Lỗi check HupSMS: {e}")
        
        await asyncio.sleep(2)
def format_phone_number(phone: str) -> str:
    """Xử lý số điện thoại - bỏ số 0 ở đầu nếu có"""
    if not phone:
        return "Chưa có"
    phone = str(phone).strip()
    # Nếu bắt đầu bằng số 0, bỏ số 0 đầu
    if phone.startswith('0'):
        return phone[1:]
    return phone
@dp.callback_query(F.data.startswith("sms_vip_rent_again_"))
async def sms_vip_rent_again_handler(call: CallbackQuery):
    """Xử lý thuê lại số SMS VIP với giá 3,600đ"""
    data_parts = call.data.split("_")
    # sms_vip_rent_again_orderId_phone
    order_id = data_parts[4]
    phone = data_parts[5]
    
    user = get_user(call.from_user.id)
    balance = user[3] if isinstance(user[3], int) else 0
    rent_again_price = 3600
    
    if balance < rent_again_price:
        await call.answer(f"❌ Số dư không đủ! Cần {rent_again_price:,}đ. Bạn có {balance:,}đ", show_alert=True)
        return
    
    # Gọi API thuê lại số
    result = await call_hupsms_api("rerent", {"phone": phone})
    
    if result.get('status') != 'success':
        error_msg = result.get('message', 'Lỗi không xác định')
        await call.answer(f"❌ Lỗi thuê lại: {error_msg}", show_alert=True)
        return
    
    data = result.get('data', {})
    new_order_id = data.get('orderId')
    new_phone = format_phone_number(data.get('phone', phone))  # Bỏ số 0 đầu
    price = data.get('price', rent_again_price)
    
    if not new_order_id:
        await call.answer("❌ Không thể thuê lại số này!", show_alert=True)
        return
    
    # Trừ tiền
    update_balance(call.from_user.id, -rent_again_price, f"Thuê lại SMS VIP - số {phone}")
    new_balance = balance - rent_again_price
    
    # Tạo session mới
    session_id = f"SMSVIP_rentagain_{new_order_id}_{int(datetime.now().timestamp())}"
    session = {
        'id': session_id,
        'service': "SMS VIP",
        'request_id': new_order_id,
        'phone': new_phone,
        'start_time': datetime.now(VIETNAM_TZ),
        'api_type': 'hupsms'
    }
    
    if call.from_user.id not in otp_sessions:
        otp_sessions[call.from_user.id] = []
    otp_sessions[call.from_user.id].append(session)

    profit = rent_again_price - 2000  # 3600 - 2000 = 1600đ
    for admin_id in ADMIN_IDS:
        await bot.send_message(
            admin_id,
            f"🔐 <b>THUÊ LẠI SMS VIP</b>\n\n"
            f"👤 User: {call.from_user.id}\n"
            f"💎 DV: SMS VIP\n"
            f"📱 Số: {new_phone}\n"
            f"💰 Lợi nhuận: {profit:,}đ"
        )
    
    current_time = datetime.now(VIETNAM_TZ).strftime("%H:%M:%S %d/%m/%Y")
    active_count = len(otp_sessions[call.from_user.id])
    
    await call.message.answer(
        f"✅ <b>THUÊ LẠI SMS VIP THÀNH CÔNG!</b>\n\n"
        f"💎 <b>Dịch vụ:</b> SMS VIP\n"
        f"📱 <b>Số điện thoại:</b> <code>{new_phone}</code>\n"
        f"♻️ <b>Thuê lại</b> (đã từng thuê trước đó)\n"
        f"⏰ <b>Thời gian:</b> {current_time}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Giá:</b> {rent_again_price:,}đ\n"
        f"💵 <b>Số dư còn:</b> {new_balance:,}đ\n"
        f"📊 <b>Đang thuê:</b> {active_count} số\n\n"
        f"⏳ <b>Đang chờ SMS...</b> (tối đa 6 phút)",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💎 Thuê SMS VIP mới", callback_data="otp_menu")],
            [InlineKeyboardButton(text="🏠 Menu", callback_data="menu")]
        ])
    )
    
    # Chạy vòng lặp check OTP cho thuê lại
    asyncio.create_task(check_hupsms_loop(call.from_user.id, session_id, new_order_id, "SMS VIP", new_phone))

async def check_otp_loop(user_id: int, session_id: str, request_id: str, service: str, phone: str):
    """Vòng lặp check OTP mỗi 2 giây, tự động hoàn tiền sau 6 phút"""
    start_time = datetime.now(VIETNAM_TZ)
    timeout_minutes = 6
    
    while True:
        elapsed = (datetime.now(VIETNAM_TZ) - start_time).total_seconds() / 60
        
        # Hết 6 phút -> hoàn tiền
        if elapsed >= timeout_minutes:
            update_balance(user_id, OTP_PRICE, f"Hoàn tiền thuê OTP {service} - hết 6 phút")
            
            await bot.send_message(
                user_id,
                f"❌ <b>HẾT THỜI GIAN CHỜ OTP</b>\n\n"
                f"🎮 <b>Dịch vụ:</b> {OTP_SERVICE_EMOJI[service]} {service}\n"
                f"📱 <b>Số:</b> <code>{phone}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"⏰ Đã chờ {timeout_minutes} phút nhưng không nhận được OTP.\n"
                f"💰 <b>Đã hoàn tiền:</b> {OTP_PRICE:,}đ\n"
                f"💡 Vui lòng thử lại sau!"
            )
            
            # Xóa session khỏi danh sách
            if user_id in otp_sessions:
                otp_sessions[user_id] = [s for s in otp_sessions[user_id] if s['id'] != session_id]
                if not otp_sessions[user_id]:
                    del otp_sessions[user_id]
            return
        
        # Gọi API check OTP
        try:
            result = await call_viotp_api("session/getv2", {"requestId": request_id})
            
            if result.get('success'):
                data = result.get('data', {})
                status = data.get('Status')
                
                # Status = 1 là đã có OTP
                if status == 1:
                    code = data.get('Code', '')
                    sms_content = data.get('SmsContent', '')
                    is_sound = data.get('IsSound', False)
                    phone = data.get('Phone', '')
                    re_phone = data.get('PhoneOriginal', phone)
                    
                    # Lưu vào database
                    conn = get_db_connection()
                    c = conn.cursor()
                    c.execute("""
                        INSERT INTO otp_rentals (user_id, request_id, phone_number, service_name, price, code, sms_content, status, rented_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (user_id, request_id, phone, service, OTP_PRICE, code, sms_content, 1, datetime.now(VIETNAM_TZ).isoformat()))
                    conn.commit()
                    conn.close()
                    
                    # Gửi thông báo cho admin
                    for admin_id in ADMIN_IDS:
                        await bot.send_message(
                            admin_id,
                            f"🔐 <b>CÓ OTP MỚI</b>\n\n"
                            f"👤 User: {user_id}\n"
                            f"🎮 DV: {service}\n"
                            f"📱 Số: {phone}\n"
                            f"🔑 Mã: {code}\n"
                            f"🎵 Audio: {is_sound}\n"
                            f"💰 Lợi nhuận: 920đ"
                        )
                    
                    # Xử lý OTP dạng audio
                    if is_sound:
                        try:
                            async with aiohttp.ClientSession() as session:
                                async with session.get(sms_content, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                                    if resp.status == 200:
                                        audio_data = await resp.read()
                                        
                                        await bot.send_voice(
                                            user_id,
                                            voice=types.BufferedInputFile(audio_data, filename="otp.wav"),
                                            caption=f"✅ <b>NHẬN MÃ OTP THÀNH CÔNG!</b>\n\n"
                                                    f"🎮 <b>Dịch vụ:</b> {OTP_SERVICE_EMOJI[service]} {service}\n"
                                                    f"📱 <b>Số điện thoại:</b> <code>{phone}</code>\n"
                                                    f"🔑 <b>Mã OTP:</b> <code>{code}</code>\n"
                                                    f"━━━━━━━━━━━━━━━━━━━━\n"
                                                    f"💰 <b>Giá thuê mới:</b> {OTP_PRICE:,}đ\n"
                                                    f"♻️ <b>Giá thuê lại:</b> 3,550đ\n"
                                                    f"⏱️ <b>Thời gian nhận:</b> {int(elapsed * 60)} giây\n\n"
                                                    f"⚠️ Mã OTP có hiệu lực trong 2 phút!",
                                            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                                [InlineKeyboardButton(text="♻️ THUÊ LẠI SỐ NÀY (3,550đ)", callback_data=f"otp_rent_again_{request_id}_{re_phone}_{service}")],
                                                [InlineKeyboardButton(text="🔐 Thuê số mới", callback_data="otp_menu")],
                                                [InlineKeyboardButton(text="🏠 Menu", callback_data="menu")]
                                            ])
                                        )
                                    else:
                                        raise Exception("Failed to download audio")
                        except Exception as e:
                            # Fallback: gửi link nếu tải lỗi
                            await bot.send_message(
                                user_id,
                                f"✅ <b>NHẬN MÃ OTP THÀNH CÔNG!</b>\n\n"
                                f"🎮 <b>Dịch vụ:</b> {OTP_SERVICE_EMOJI[service]} {service}\n"
                                f"📱 <b>Số điện thoại:</b> <code>{phone}</code>\n"
                                f"🔑 <b>Mã OTP:</b> <code>{code}</code>\n"
                                f"🎵 <b>Audio OTP:</b> <a href='{sms_content}'>Nhấn để nghe</a>\n"
                                f"━━━━━━━━━━━━━━━━━━━━\n"
                                f"💰 <b>Giá thuê mới:</b> {OTP_PRICE:,}đ\n"
                                f"♻️ <b>Giá thuê lại:</b> 3,550đ\n"
                                f"⏱️ <b>Thời gian nhận:</b> {int(elapsed * 60)} giây\n\n"
                                f"⚠️ Mã OTP có hiệu lực trong 2 phút!",
                                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                    [InlineKeyboardButton(text="♻️ THUÊ LẠI SỐ NÀY (3,550đ)", callback_data=f"otp_rent_again_{request_id}_{re_phone}_{service}")],
                                    [InlineKeyboardButton(text="🔐 Thuê số mới", callback_data="otp_menu")],
                                    [InlineKeyboardButton(text="🏠 Menu", callback_data="menu")]
                                ])
                            )
                    else:
                        # OTP dạng text
                        await bot.send_message(
                            user_id,
                            f"✅ <b>NHẬN MÃ OTP THÀNH CÔNG!</b>\n\n"
                            f"🎮 <b>Dịch vụ:</b> {OTP_SERVICE_EMOJI[service]} {service}\n"
                            f"📱 <b>Số điện thoại:</b> <code>{phone}</code>\n"
                            f"🔑 <b>Mã OTP:</b> <code>{code}</code>\n"
                            f"📝 <b>Nội dung:</b> {sms_content[:200]}\n"
                            f"━━━━━━━━━━━━━━━━━━━━\n"
                            f"💰 <b>Giá thuê mới:</b> {OTP_PRICE:,}đ\n"
                            f"♻️ <b>Giá thuê lại:</b> 3,550đ\n"
                            f"⏱️ <b>Thời gian nhận:</b> {int(elapsed * 60)} giây\n\n"
                            f"⚠️ Mã OTP có hiệu lực trong 2 phút!",
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                [InlineKeyboardButton(text="♻️ THUÊ LẠI SỐ NÀY (3,550đ)", callback_data=f"otp_rent_again_{request_id}_{re_phone}_{service}")],
                                [InlineKeyboardButton(text="🔐 Thuê số mới", callback_data="otp_menu")],
                                [InlineKeyboardButton(text="🏠 Menu", callback_data="menu")]
                            ])
                        )
                    
                    # Xóa session khỏi danh sách
                    if user_id in otp_sessions:
                        otp_sessions[user_id] = [s for s in otp_sessions[user_id] if s['id'] != session_id]
                        if not otp_sessions[user_id]:
                            del otp_sessions[user_id]
                    return
        except Exception as e:
            print(f"Lỗi check OTP: {e}")
        
        await asyncio.sleep(2)
@dp.callback_query(F.data.startswith("otp_rent_again_"))
async def otp_rent_again_handler(call: CallbackQuery):
    """Xử lý thuê lại số cũ với giá 3,550đ"""
    data_parts = call.data.split("_")
    # otp_rent_again_request_id_phone_service
    request_id = data_parts[3]
    phone = data_parts[4]
    service = data_parts[5]
    
    user = get_user(call.from_user.id)
    balance = user[3] if isinstance(user[3], int) else 0
    rent_again_price = 3550
    
    if balance < rent_again_price:
        await call.answer(f"❌ Số dư không đủ! Cần {rent_again_price:,}đ. Bạn có {balance:,}đ", show_alert=True)
        return
    
    # Lấy service ID của Okeda
    service_id = await get_okeda_service_id()
    if not service_id:
        await call.answer("❌ Không tìm thấy dịch vụ OKEDA!", show_alert=True)
        return
    
    # Gọi API thuê lại số cũ
    result = await call_viotp_api("request/getv2", {"serviceId": service_id, "number": phone})
    
    if not result.get('success'):
        error_msg = result.get('message', 'Lỗi không xác định')
        await call.answer(f"❌ Lỗi thuê lại: {error_msg}", show_alert=True)
        return
    
    data = result.get('data', {})
    new_request_id = data.get('request_id')
    new_phone = data.get('phone_number', phone)
    
    if not new_request_id:
        await call.answer("❌ Không thể thuê lại số này!", show_alert=True)
        return
    
    # Trừ tiền
    update_balance(call.from_user.id, -rent_again_price, f"Thuê lại OTP {service} - số {phone}")
    new_balance = balance - rent_again_price
    
    # Tạo session mới cho thuê lại
    session_id = f"{service}_rentagain_{new_request_id}_{int(datetime.now().timestamp())}"
    session = {
        'id': session_id,
        'service': service,
        'request_id': new_request_id,
        'phone': new_phone,
        'start_time': datetime.now(VIETNAM_TZ)
    }
    
    if call.from_user.id not in otp_sessions:
        otp_sessions[call.from_user.id] = []
    otp_sessions[call.from_user.id].append(session)
    
    current_time = datetime.now(VIETNAM_TZ).strftime("%H:%M:%S %d/%m/%Y")
    active_count = len(otp_sessions[call.from_user.id])
    
    await call.message.answer(  # ✅ Đổi thành answer
        f"✅ <b>THUÊ LẠI SỐ THÀNH CÔNG!</b>\n\n"
        f"🎮 <b>Dịch vụ:</b> {OTP_SERVICE_EMOJI[service]} {service}\n"
        f"📱 <b>Số điện thoại:</b> <code>{new_phone}</code>\n"
        f"♻️ <b>Thuê lại</b> (đã từng thuê trước đó)\n"
        f"⏰ <b>Thời gian:</b> {current_time}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Giá:</b> {rent_again_price:,}đ\n"
        f"💵 <b>Số dư còn:</b> {new_balance:,}đ\n"
        f"📊 <b>Đang thuê:</b> {active_count} số\n\n"
        f"⏳ <b>Đang chờ OTP...</b> (tối đa 6 phút)",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔐 Thuê tiếp số khác", callback_data="otp_menu")],
            [InlineKeyboardButton(text="🏠 Menu", callback_data="menu")]
        ])
    )
    
    # Xóa tin nhắn cũ (tùy chọn)
    try:
        await call.message.delete()
    except:
        pass
    
    # Chạy vòng lặp check OTP cho thuê lại
    asyncio.create_task(check_otp_loop(call.from_user.id, session_id, new_request_id, service, new_phone))
# ==================== API HupSMS ====================
async def call_hupsms_api(endpoint: str, params: dict = None) -> dict:
    """Gọi API HupSMS"""
    if params is None:
        params = {}
    params['api_key'] = HUPSMS_API_KEY
    url = f"{HUPSMS_API_URL}/{endpoint}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            return await resp.json()

async def get_hupsms_balance() -> int:
    """Lấy số dư tài khoản HupSMS"""
    result = await call_hupsms_api("balance")
    if result.get('status') == 'success':
        return result.get('data', {}).get('balance', 0)
    return 0

async def rent_hupsms_sms() -> dict:
    """Thuê SMS từ HupSMS (Server 3 - Test 3)"""
    # Lấy danh sách dịch vụ
    services = await call_hupsms_api("services", {"server": HUPSMS_SERVER})
    if services.get('status') != 'success':
        return None
    
    # Tìm dịch vụ Test 3
    service_id = None
    for sv in services.get('data', []):
        if HUPSMS_SERVICE_NAME.lower() in sv.get('name', '').lower():
            service_id = sv.get('id')
            break
    
    if not service_id:
        return None
    
    # Thuê số
    result = await call_hupsms_api("rent", {"serviceId": service_id})
    if result.get('status') == 'success':
        return result.get('data', {})
    return None

async def check_hupsms_otp(order_id: str) -> dict:
    """Kiểm tra OTP từ HupSMS"""
    result = await call_hupsms_api(f"check/{order_id}")
    if result.get('status') == 'success':
        return result.get('data', {})
    return None

async def cancel_hupsms_order(order_id: str) -> dict:
    """Hủy đơn HupSMS (nếu cần)"""
    result = await call_hupsms_api(f"cancel/{order_id}")
    return result
# ==================== THÔNG TIN USER ====================
@dp.callback_query(F.data == "myinfo")
async def show_my_info(call: CallbackQuery):
    user = get_user(call.from_user.id)
    if not user:
        await call.message.edit_text("❌ Không tìm thấy thông tin!")
        return
    
    balance = user[3] if isinstance(user[3], int) else 0
    total_recharge = user[4] if isinstance(user[4], int) else 0
    total_spent = user[5] if isinstance(user[5], int) else 0
    # Định dạng thời gian
    if user[6]:
        try:
            # Chuyển đổi ISO sang datetime
            dt = datetime.fromisoformat(user[6].replace('T', ' '))
            created_at = dt.strftime('%H:%M:%S %d/%m/%Y')
        except:
            created_at = user[6][:19].replace('T', ' ')
    else:
        created_at = "Không rõ"
    
    # Lấy số lần mua
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM purchases WHERE user_id = %s", (call.from_user.id,))
    purchase_count = c.fetchone()[0]
    conn.close()
    
    text = f"""
👤 <b>THÔNG TIN CỦA BẠN</b>

🆔 <b>User ID:</b> <code>{call.from_user.id}</code>
📝 <b>Tên:</b> {call.from_user.full_name}
💬 <b>Username:</b> @{call.from_user.username or 'chưa có'}

━━━━━━━━━━━━━━━━━━━━━━━
💰 <b>Số dư:</b> {balance:,}đ
📥 <b>Tổng nạp:</b> {total_recharge:,}đ
📤 <b>Tổng chi:</b> {total_spent:,}đ
📦 <b>Số lần mua:</b> {purchase_count}

📅 <b>Ngày tham gia:</b> {created_at}
"""
    
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Quay lại", callback_data="menu")]
    ]))
# ==================== HỖ TRỢ ====================
@dp.callback_query(F.data == "support")
async def support_menu(call: CallbackQuery):
    # Tạo danh sách nút liên hệ admin
    buttons = []
    for username in ADMIN_USERNAMES:
        buttons.append([InlineKeyboardButton(text=f"📩 @{username}", url=f"https://t.me/{username}")])
    buttons.append([InlineKeyboardButton(text="🔙 Quay lại", callback_data="menu")])
    
    support_text = f"""
🆘 <b>HỖ TRỢ KHÁCH HÀNG</b>

📌 <b>Các vấn đề cần hỗ trợ:</b>
• 🎮 Lỗi đăng nhập account
• 💳 Nạp tiền chưa nhận được
• 🔐 Quên mật khẩu rút tiền
• 📝 Khiếu nại, thắc mắc khác

━━━━━━━━━━━━━━━━━━━━

<b>📞 Liên hệ admin:</b>
Bấm vào tên admin bên dưới để chat trực tiếp!

⏳ <b>Thời gian phản hồi:</b> 8h - 22h hàng ngày

💡 <b>Lưu ý:</b> Ghi rõ vấn đề và kèm ảnh/video nếu có
"""
    await call.message.edit_text(support_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
# ==================== NẠP TIỀN ====================
@dp.callback_query(F.data == "recharge")
async def recharge_menu(call: CallbackQuery, state: FSMContext):
    user = get_user(call.from_user.id)
    balance = user[3] if user and isinstance(user[3], int) else 0
    
    await call.message.edit_text(
        f"💳 <b>NẠP TIỀN VÀO TÀI KHOẢN</b>\n\n"
        f"💰 <b>Số dư hiện tại:</b> {balance:,}đ\n\n"
        f"📝 <b>Nhập số tiền muốn nạp:</b>\n"
        f"(Tối thiểu 20,000đ)\n\n"
        f"Gửi /cancel để hủy",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Quay lại", callback_data="menu")]
        ])
    )
    await state.set_state(RechargeState.waiting_for_amount)

@dp.message(RechargeState.waiting_for_amount)
async def process_recharge_amount(msg: Message, state: FSMContext):
    try:
        amount = int(msg.text.strip())
        if amount < 20000:
            await msg.answer("❌ Số tiền tối thiểu là 20,000đ! Vui lòng nhập lại.")
            return
        
        await state.update_data(amount=amount)
        
        import random
        import string
        import urllib.parse
        
        trans_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        await state.update_data(trans_code=trans_code)
        
        # Thông tin ngân hàng chính chủ
        BANK_ACC = "666666291005"
        BANK_NAME = "MBBank"
        BANK_OWNER = "NGUYEN THE LAM"
        
        # Tạo nội dung chuyển khoản
        content = f"NAP {trans_code} {msg.from_user.id}"
        encoded_content = urllib.parse.quote(content)
        
        # Tạo URL QR code từ SePay
        qr_url = f"https://qr.sepay.vn/img?acc={BANK_ACC}&bank={BANK_NAME}&amount={amount}&des={encoded_content}"
        
        # Nội dung tin nhắn kèm QR
        caption = f"""
💳 <b>QUÉT QR ĐỂ NẠP TIỀN</b>

🏦 <b>Ngân hàng:</b> {BANK_NAME}
<b>Số tài khoản:</b> <code>{BANK_ACC}</code>
<b>Chủ tài khoản:</b> {BANK_OWNER}

💰 <b>Số tiền:</b> {amount:,}đ
🔑 <b>Mã GD:</b> <code>{trans_code}</code>

━━━━━━━━━━━━━━━━━━━━

📌 <b>Hướng dẫn:</b>
1. Quét mã QR bên dưới
2. Kiểm tra lại số tiền và nội dung
3. Xác nhận chuyển khoản

⚠️ Nội dung chuyển khoản: <code>{content}</code>
✅ Sau khi chuyển, tiền sẽ tự động cộng vào tài khoản

Gửi /cancel để hủy
"""
        
        # Gửi ảnh QR kèm hướng dẫn
        await msg.answer_photo(photo=qr_url, caption=caption)
        await state.clear()
        
    except ValueError:
        await msg.answer("❌ Vui lòng nhập số tiền hợp lệ!")
    except Exception as e:
        await msg.answer(f"❌ Lỗi tạo QR: {str(e)}\nVui lòng thử lại sau!")

@dp.message(RechargeState.waiting_for_bill)
async def process_recharge_bill(msg: Message, state: FSMContext):
    data = await state.get_data()
    amount = data.get('amount')
    trans_code = data.get('trans_code')
    
    if not msg.photo:
        await msg.answer("❌ Vui lòng gửi ảnh bill giao dịch!\nGửi /cancel để hủy")
        return
    
    # Lưu ảnh bill
    photo = msg.photo[-1]
    file = await msg.bot.get_file(photo.file_id)
    
    # Gửi thông báo cho admin
    admin_text = f"""
💳 <b>YÊU CẦU NẠP TIỀN MỚI</b>

👤 <b>User ID:</b> <code>{msg.from_user.id}</code>
👤 <b>Username:</b> @{msg.from_user.username or 'không có'}
👤 <b>Tên:</b> {msg.from_user.full_name}

💰 <b>Số tiền:</b> {amount:,}đ
🔑 <b>Mã GD:</b> <code>{trans_code}</code>
📅 <b>Thời gian:</b> {datetime.now(VIETNAM_TZ).strftime('%H:%M:%S %d/%m/%Y')}

📌 <b>Hành động:</b> Dùng lệnh <code>/addmoney {msg.from_user.id} {amount}</code> để cộng tiền
"""
    
    # Gửi cho tất cả admin
    for admin_id in ADMIN_IDS:
        try:
            await msg.bot.send_photo(admin_id, photo.file_id, caption=admin_text)
        except:
            pass
    
    await msg.answer(
        f"✅ <b>ĐÃ GỬI YÊU CẦU NẠP TIỀN!</b>\n\n"
        f"💰 Số tiền: {amount:,}đ\n"
        f"🔑 Mã GD: <code>{trans_code}</code>\n\n"
        f"⏳ Admin sẽ xác nhận và cộng tiền trong 5 phút.\n"
        f"💡 Bạn có thể kiểm tra số dư sau khi được xác nhận."
    )
    await state.clear()
@dp.callback_query(F.data == "inventory")
async def show_inventory(call: CallbackQuery):
    inv = get_inventory()
    sold, revenue = get_sold_stats()
    text = "📦 <b>KHO ACCOUNT</b>\n\n"
    for site in SITES:
        text += f"{SITE_EMOJI[site]} <b>{site}</b>\n"
        text += f"   ✅ Còn: {inv.get(site, 0)} acc\n"
        text += f"   📦 Đã bán: {sold.get(site, 0)} acc\n"
        text += f"   💰 Doanh thu: {revenue.get(site, 0):,}đ\n"
        text += f"   💵 Giá: {SITE_PRICE.get(site, 20000):,}đ\n\n"
    await call.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Mua ngay", callback_data="buy")],
        [InlineKeyboardButton(text="🔙 Quay lại", callback_data="menu")]
    ]))
    try:
        await call.message.delete()
    except:
        pass

@dp.callback_query(F.data == "menu")
async def back_menu(call: CallbackQuery):
    user = get_user(call.from_user.id)
    balance = user[3] if user and isinstance(user[3], int) else 0
    
    # Gửi tin nhắn MỚI với ReplyKeyboardMarkup
    await call.message.answer(
        f"🎉 <b>MENU CHÍNH</b>\n\n💰 Số dư: {balance:,}đ\n\n👇 Chọn chức năng:",
        reply_markup=main_menu(balance)
    )
    
    # Xóa tin nhắn cũ (tùy chọn)
    try:
        await call.message.delete()
    except:
        pass
@dp.callback_query(F.data == "otp_history")
async def otp_history_handler(call: CallbackQuery):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT phone_number, service_name, price, code, status, rented_at 
        FROM otp_rentals 
        WHERE user_id = %s 
        ORDER BY id DESC 
        LIMIT 20
    """, (call.from_user.id,))
    rentals = c.fetchall()
    conn.close()
    
    if not rentals:
        await call.message.edit_text(
            "📭 Bạn chưa thuê OTP lần nào!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔐 Thuê OTP", callback_data="otp_menu")],
                [InlineKeyboardButton(text="🔙 Quay lại", callback_data="menu")]
            ])
        )
        return
    
    total = len(rentals)
    text = f"📜 <b>LỊCH SỬ THUÊ OTP</b> <i>({total}/20 số mới nhất)</i>\n\n"
    
    for i, r in enumerate(rentals, 1):
        if r[4] == 1:
            status_text = "✅ Thành công"
            status_icon = "✅"
        else:
            status_text = "⏳ Hết hạn/Hoàn tiền"
            status_icon = "❌"
        
        # Định dạng thời gian
        try:
            rented_time = r[5][:19].replace('T', ' ')
        except:
            rented_time = r[5][:19] if r[5] else "Không rõ"
        
        text += f"""
{status_icon} <b>#{i}</b>
📱 Số: <code>{r[0]}</code>
🎮 DV: {r[1]}
💰 Giá: {r[2]:,}đ
🔑 Mã: <code>{r[3] or 'Chưa có'}</code>
📅 {rented_time}
"""
    
    # Thêm nút xem thêm nếu cần
    buttons = [[InlineKeyboardButton(text="🔐 Thuê OTP mới", callback_data="otp_menu")]]
    if total == 20:
        buttons.append([InlineKeyboardButton(text="📜 Xem thêm (liên hệ Admin)", callback_data="support")])
    buttons.append([InlineKeyboardButton(text="🔙 Quay lại", callback_data="menu")])
    
    await call.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    try:
        await call.message.delete()
    except:
        pass

# ==================== ADMIN ====================
# ==================== CHAT ALL ====================
@dp.message(Command("chatall"))
async def chat_all(msg: Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        await msg.answer("⛔ Không có quyền!")
        return
    
    # Lấy nội dung tin nhắn (bỏ qua lệnh /chatall)
    text = msg.text.replace("/chatall", "").strip()
    if not text:
        await msg.answer("❌ Sai format!\nDùng: /chatall nội_dung_tin_nhắn")
        return
    
    # Thông báo đang gửi
    status_msg = await msg.answer("🔄 Đang gửi tin nhắn đến tất cả user...")
    
    # Lấy danh sách user
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT telegram_id FROM users")
    users = c.fetchall()
    conn.close()
    
    if not users:
        await status_msg.edit_text("📭 Không có user nào để gửi!")
        return
    
    success = 0
    fail = 0
    
    for i, user in enumerate(users):
        try:
            await bot.send_message(
                user[0], 
                f"📢 <b>THÔNG BÁO TỪ ADMIN</b>\n\n{text}",
                parse_mode=ParseMode.HTML
            )
            success += 1
        except Exception as e:
            fail += 1
            print(f"Lỗi gửi đến {user[0]}: {e}")
        
        # Cứ 30 user thì nghỉ 0.5 giây để tránh spam
        if (i + 1) % 30 == 0:
            await asyncio.sleep(0.5)
    
    await status_msg.edit_text(
        f"✅ <b>ĐÃ GỬI XONG!</b>\n\n"
        f"📨 Thành công: {success} user\n"
        f"❌ Thất bại: {fail} user\n"
        f"📝 Nội dung: {text[:100]}..."
    )
    
    # Ghi log
    add_admin_log(msg.from_user.id, "chat_all", None, f"Gửi tin nhắn đến {success} user")
@dp.message(Command("admin"))
async def admin_panel(msg: Message, state: FSMContext):
    # Clear state để tránh lỗi
    current_state = await state.get_state()
    if current_state:
        await state.clear()
        await msg.answer("🔄 Đã hủy thao tác trước đó!")
    
    if msg.from_user.id not in ADMIN_IDS:
        await msg.answer("⛔ Không có quyền!")
        return
    await msg.answer("👑 <b>ADMIN PANEL</b>\n\nChọn chức năng:", reply_markup=admin_menu())

@dp.callback_query(F.data == "admin_dashboard")
async def admin_dash(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Không có quyền!")
        return
    inv = get_inventory()
    sold, revenue = get_sold_stats()
    daily = get_daily_stats()
    user_count = get_user_count()
    total_revenue = sum(revenue.values())
    total_sold = sum(sold.values())
    total_inv = sum(inv.values())
    
    # Tính doanh thu OTP (lợi nhuận = 2820 - 1600 = 1220đ mỗi lần)
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM otp_rentals WHERE status = 1")
    otp_success = c.fetchone()[0]
    otp_profit = otp_success * 920
    conn.close()
    
    text = f"""
📊 <b>DASHBOARD TỔNG QUAN</b>

👥 <b>Thống kê user:</b>
• Tổng users: {user_count}
• Users mới hôm nay: {daily['new_users']}

💰 <b>Thống kê doanh thu acc:</b>
• Hôm nay: {daily['revenue']:,}đ ({daily['sales']} giao dịch)
• Tổng doanh thu acc: {total_revenue:,}đ
• Tổng acc đã bán: {total_sold}

🔐 <b>Thống kê OTP:</b>
• Số lần thuê thành công: {otp_success}
• Lợi nhuận OTP: {otp_profit:,}đ

📦 <b>Tồn kho:</b>
• Tổng acc còn: {total_inv}

📋 <b>Chi tiết theo site:</b>
"""
    for site in SITES:
        text += f"\n{SITE_EMOJI[site]} {site}: 📦{sold.get(site,0)} bán | ✅{inv.get(site,0)} còn | 💰{revenue.get(site,0):,}đ"
    
    await call.message.answer(text, reply_markup=admin_menu())
    try:
        await call.message.delete()
    except:
        pass

@dp.callback_query(F.data == "admin_revenue")
async def admin_revenue(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Không có quyền!")
        return
    sold, revenue = get_sold_stats()
    total = sum(revenue.values())
    
    text = f"💰 <b>BÁO CÁO DOANH THU</b>\n\n"
    text += f"💵 <b>Tổng doanh thu:</b> {total:,}đ\n\n"
    text += f"<b>📋 Chi tiết theo site:</b>\n"
    for site in SITES:
        text += f"{SITE_EMOJI[site]} {site}: {revenue.get(site,0):,}đ ({sold.get(site,0)} acc)\n"
    
    await call.message.answer(text, reply_markup=admin_menu())
    try:
        await call.message.delete()
    except:
        pass

@dp.callback_query(F.data == "admin_add")
async def admin_add_menu(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Không có quyền!")
        return
    buttons = [[InlineKeyboardButton(text=f"{SITE_EMOJI[s]} {s}", callback_data=f"addsite_{s}")] for s in SITES]
    buttons.append([InlineKeyboardButton(text="🔙 Quay lại", callback_data="admin_dashboard")])
    await call.message.answer("➕ <b>THÊM ACCOUNT</b>\n\nChọn site:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AddAccountState.waiting_for_site)

@dp.callback_query(F.data == "admin_bulk_add")
async def admin_bulk_add(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Không có quyền!")
        return
    buttons = [[InlineKeyboardButton(text=f"{SITE_EMOJI[s]} {s}", callback_data=f"bulk_{s}")] for s in SITES]
    buttons.append([InlineKeyboardButton(text="🔙 Quay lại", callback_data="admin_dashboard")])
    await call.message.answer("📦 <b>NHẬP NHIỀU ACCOUNT</b>\n\nChọn site:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AddAccountState.waiting_for_site)

@dp.callback_query(AddAccountState.waiting_for_site, F.data.startswith("addsite_"))
async def admin_get_acc(call: CallbackQuery, state: FSMContext):
    site = call.data.split("_")[1]
    await state.update_data(site=site, is_bulk=False)
    await call.message.edit_text(f"""📝 Nhập acc cho {SITE_EMOJI[site]} {site}

<b>Format:</b> <code>username | password | mk_rut | ten_that | stk | sdt</code>

<b>Ví dụ đầy đủ:</b>
<code>vip123 | abc123 | 123456 | Nguyen Van A | 123456789 | 0987654321</code>

<b>Chỉ cần username và password:</b>
<code>vip123 | abc123</code>

Gửi /cancel để hủy""")
    await state.set_state(AddAccountState.waiting_for_account)

@dp.callback_query(AddAccountState.waiting_for_site, F.data.startswith("bulk_"))
async def admin_bulk_input(call: CallbackQuery, state: FSMContext):
    site = call.data.split("_")[1]
    await state.update_data(site=site, is_bulk=True)
    await call.message.edit_text(
        f"📝 Nhập danh sách acc cho {SITE_EMOJI[site]} {site}\n\n"
        f"<b>Format mỗi dòng:</b> <code>username | password | mk_rut | ten_that | stk | sdt</code>\n"
        f"<b>Ví dụ:</b>\n"
        f"<code>user1 | pass1 | 123456 | Nguyen Van A | 123456789 | 0987654321</code>\n"
        f"<code>user2 | pass2 | 654321 | Tran Van B | 987654321 | 0123456789</code>\n"
        f"<code>user3 | pass3</code> (chỉ cần username và password)\n\n"
        f"Gửi /cancel để hủy"
    )
    await state.set_state(AddAccountState.waiting_for_account)

@dp.message(AddAccountState.waiting_for_account)
async def admin_save_acc(msg: Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        return
    if msg.text == "/cancel":
        await state.clear()
        await msg.answer("❌ Đã hủy!")
        return
    data = await state.get_data()
    site = data.get('site')
    is_bulk = data.get('is_bulk', False)
    
    if is_bulk:
        accounts = []
        for line in msg.text.strip().split('\n'):
            if '|' in line:
                parts = line.split('|')
                username = parts[0].strip()
                password = parts[1].strip() if len(parts) > 1 else ""
                withdraw_password = parts[2].strip() if len(parts) > 2 else ""
                real_name = parts[3].strip() if len(parts) > 3 else ""
                bank_number = parts[4].strip() if len(parts) > 4 else ""
                phone = parts[5].strip() if len(parts) > 5 else ""
                accounts.append((username, password, withdraw_password, real_name, bank_number, phone))
        if accounts:
            # Thêm từng account với đầy đủ thông tin
            conn = get_db_connection()
            c = conn.cursor()
            for acc in accounts:
                c.execute("""INSERT INTO accounts 
                          (site, username, password, withdraw_password, real_name, bank_number, phone, created_at) 
                          VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                          (site, acc[0], acc[1], acc[2], acc[3], acc[4], acc[5], datetime.now().isoformat()))
            conn.commit()
            conn.close()
            await msg.answer(f"✅ Đã thêm {len(accounts)} acc cho {SITE_EMOJI[site]} {site}")
        else:
            await msg.answer("❌ Không có acc hợp lệ nào!")
    else:
        try:
            parts = msg.text.split("|")
            if len(parts) >= 2:
                username = parts[0].strip()
                password = parts[1].strip()
                withdraw_password = parts[2].strip() if len(parts) > 2 else ""
                real_name = parts[3].strip() if len(parts) > 3 else ""
                bank_number = parts[4].strip() if len(parts) > 4 else ""
                phone = parts[5].strip() if len(parts) > 5 else ""
                
                conn = get_db_connection()
                c = conn.cursor()
                c.execute("""INSERT INTO accounts 
                          (site, username, password, withdraw_password, real_name, bank_number, phone, created_at) 
                          VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                          (site, username, password, withdraw_password, real_name, bank_number, phone, datetime.now().isoformat()))
                conn.commit()
                conn.close()
                
                inv = get_inventory()
                await msg.answer(f"""✅ Đã thêm acc {SITE_EMOJI[site]} {site}!

👤 Username: <code>{username}</code>
🔑 Password: <code>{password}</code>
🔐 MK Rút: <code>{withdraw_password or 'Chưa có'}</code>
📝 Tên thật: {real_name or 'Chưa có'}
🏦 STK: {bank_number or 'Chưa có'}
📱 SĐT: {phone or 'Chưa có'}

📦 Kho {site}: {inv.get(site, 0)} acc""")
            else:
                raise Exception("Thiếu thông tin")
        except Exception as e:
            await msg.answer("""❌ Sai format!

<b>Format đầy đủ:</b>
<code>username | password | mk_rut | ten_that | stk | sdt</code>

<b>Ví dụ:</b>
<code>vip123 | abc123 | 123456 | Nguyen Van A | 123456789 | 0987654321</code>

<b>Chỉ cần username và password (bắt buộc):</b>
<code>vip123 | abc123</code>

Các trường khác có thể bỏ trống:
<code>vip123 | abc123 | | | | </code>""")
    
    await state.clear()
    await msg.answer("👑 ADMIN PANEL", reply_markup=admin_menu())
@dp.callback_query(F.data == "admin_add_money")
async def admin_add_money(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Không có quyền!")
        return
    await state.update_data(action="add")
    await call.message.answer("💰 <b>CỘNG TIỀN CHO USER</b>\n\nFormat: <code>user_id số_tiền</code>\nVí dụ: <code>5180190297 50000</code>\n\nGửi /cancel để hủy")
    await state.set_state(MoneyState.waiting_for_user)

@dp.callback_query(F.data == "admin_sub_money")
async def admin_sub_money(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Không có quyền!")
        return
    await state.update_data(action="sub")
    await call.message.answer("💸 <b>TRỪ TIỀN CỦA USER</b>\n\nFormat: <code>user_id số_tiền</code>\nVí dụ: <code>5180190297 20000</code>\n\nGửi /cancel để hủy")
    await state.set_state(MoneyState.waiting_for_user)

@dp.message(MoneyState.waiting_for_user)
async def process_money(msg: Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        return
    if msg.text == "/cancel":
        await state.clear()
        await msg.answer("❌ Đã hủy!")
        return
    try:
        parts = msg.text.split()
        user_id = int(parts[0])
        amount = int(parts[1])
        
        user = get_user(user_id)
        if not user:
            await msg.answer(f"❌ Không tìm thấy user ID: {user_id}")
            return
        
        data = await state.get_data()
        action = data.get("action", "add")
        
        if action == "sub":
            amount = -amount
        
        old_balance = user[3] if user and isinstance(user[3], int) else 0
        update_balance(user_id, amount, f"Admin {'cộng' if amount > 0 else 'trừ'} {abs(amount)}đ")
        add_admin_log(msg.from_user.id, f"{'add' if amount > 0 else 'sub'}_money", user_id, f"{abs(amount)}đ")
        new_user = get_user(user_id)
        new_balance = new_user[3] if new_user and isinstance(new_user[3], int) else 0
        
        # Thông báo cho admin
        await msg.answer(
            f"✅ Đã {'cộng' if amount > 0 else 'trừ'} {abs(amount):,}đ cho user {user_id}\n"
            f"💰 Số dư mới: {new_balance:,}đ"
        )
        
        # Thông báo cho user
        if amount > 0:
            await notify_user(
                user_id,
                "NẠP TIỀN THÀNH CÔNG",
                f"💵 Số tiền: {amount:,}đ\n"
                f"💰 Số dư hiện tại: {new_balance:,}đ\n\n"
                f"Cảm ơn bạn đã nạp tiền! 🎉"
            )
        else:
            await notify_user(
                user_id,
                "TRỪ TIỀN TÀI KHOẢN",
                f"💸 Số tiền: {abs(amount):,}đ\n"
                f"💰 Số dư hiện tại: {new_balance:,}đ\n\n"
                f"📌 Lý do: {msg.text}",
                success=True
            )
        
        await state.clear()
        await msg.answer("👑 ADMIN PANEL", reply_markup=admin_menu())
        
    except Exception as e:
        await msg.answer(f"❌ Lỗi! Format: user_id số_tiền\nVí dụ: 5180190297 50000")

# ==================== DANH SÁCH USER CÓ PHÂN TRANG ====================
user_page_cache = {}  # Lưu trang hiện tại của từng admin

@dp.callback_query(F.data == "admin_users")
async def admin_users(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Không có quyền!")
        return
    await show_users_page(call, page=1)

async def show_users_page(call: CallbackQuery, page: int):
    """Hiển thị danh sách user theo trang"""
    users_per_page = 20
    offset = (page - 1) * users_per_page
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT telegram_id, username, full_name, balance, total_recharge, total_spent, created_at 
        FROM users 
        ORDER BY balance DESC 
        LIMIT %s OFFSET %s
    """, (users_per_page, offset))
    users = c.fetchall()
    
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    conn.close()
    
    if not users:
        await call.message.answer("📭 Không có user nào!")
        return
    
    total_pages = (total_users + users_per_page - 1) // users_per_page
    
    text = f"👥 <b>DANH SÁCH USER</b> <i>(Trang {page}/{total_pages} - Tổng {total_users} user)</i>\n"
    text += f"📊 <i>Sắp xếp theo số dư giảm dần</i>\n\n"
    
    for i, u in enumerate(users, 1 + offset):
        balance = u[3] if isinstance(u[3], int) else 0
        total_recharge = u[4] if isinstance(u[4], int) else 0
        total_spent = u[5] if isinstance(u[5], int) else 0
        
        if u[2] and u[2] != "None":
            display_name = u[2]
        elif u[1] and u[1] != "None":
            display_name = f"@{u[1]}"
        else:
            display_name = f"User {u[0]}"
        
        # Thêm icon theo số dư
        if balance >= 100000:
            balance_icon = "👑"
        elif balance >= 50000:
            balance_icon = "💎"
        elif balance >= 10000:
            balance_icon = "💰"
        else:
            balance_icon = "💵"
        
        text += f"{balance_icon} <b>#{i}</b> 🆔 <code>{u[0]}</code>\n"
        text += f"   👤 {display_name}\n"
        text += f"   💰 {balance:,}đ | 📥 {total_recharge:,}đ | 📤 {total_spent:,}đ\n\n"
    
    # Tạo nút phân trang
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(text="◀️ TRANG TRƯỚC", callback_data=f"users_page_{page-1}"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton(text="TRANG SAU ▶️", callback_data=f"users_page_{page+1}"))
    
    keyboard = []
    if nav_buttons:
        keyboard.append(nav_buttons)
    keyboard.append([InlineKeyboardButton(text="🔙 QUAY LẠI ADMIN", callback_data="admin_dashboard")])
    
    await call.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    try:
        await call.message.delete()
    except:
        pass

@dp.callback_query(F.data.startswith("users_page_"))
async def users_page_callback(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Không có quyền!")
        return
    page = int(call.data.split("_")[2])
    await show_users_page(call, page)

@dp.callback_query(F.data == "admin_inventory")
async def admin_inventory(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Không có quyền!")
        return
    inv = get_inventory()
    text = "📦 <b>KHO ACCOUNT (ADMIN)</b>\n\n"
    for site in SITES:
        text += f"{SITE_EMOJI[site]} {site}: {inv.get(site, 0)} acc\n"
    await call.message.answer(text, reply_markup=admin_menu())
    try:
        await call.message.delete()
    except:
        pass

@dp.callback_query(F.data == "admin_price")
async def admin_price_menu(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Không có quyền!")
        return
    buttons = [[InlineKeyboardButton(text=f"{SITE_EMOJI[s]} {s}", callback_data=f"price_{s}")] for s in SITES]
    buttons.append([InlineKeyboardButton(text="🔙 Quay lại", callback_data="admin_dashboard")])
    await call.message.answer("⚙️ <b>CÀI ĐẶT GIÁ THEO SITE</b>\n\nChọn site:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(PriceState.waiting_for_site)

@dp.callback_query(PriceState.waiting_for_site, F.data.startswith("price_"))
async def admin_set_price(call: CallbackQuery, state: FSMContext):
    site = call.data.split("_")[1]
    await state.update_data(site=site)
    current_price = SITE_PRICE.get(site, 20000)
    await call.message.answer(f"💰 Nhập giá mới cho {SITE_EMOJI[site]} {site}:\n\nGiá hiện tại: {current_price:,}đ\n\nGửi /cancel để hủy")
    await state.set_state(PriceState.waiting_for_price)

@dp.message(PriceState.waiting_for_price)
async def admin_save_price(msg: Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        return
    try:
        price = int(msg.text)
        data = await state.get_data()
        site = data.get('site')
        
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("UPDATE site_settings SET price = %s WHERE site = %s", (price, site))
        conn.commit()
        conn.close()
        
        SITE_PRICE[site] = price
        await msg.answer(f"✅ Đã cập nhật giá {SITE_EMOJI[site]} {site}: {price:,}đ")
        await state.clear()
        await msg.answer("👑 ADMIN PANEL", reply_markup=admin_menu())
    except ValueError:
        await msg.answer("❌ Vui lòng nhập số tiền hợp lệ!")
@dp.message(Command("addmoney"))
async def admin_add_money_cmd(msg: Message):
    if msg.from_user.id not in ADMIN_IDS:
        await msg.answer("⛔ Không có quyền!")
        return
    
    try:
        parts = msg.text.split()
        if len(parts) < 3:
            await msg.answer("❌ Sai format!\nDùng: <code>/addmoney user_id số_tiền</code>\nVí dụ: <code>/addmoney 5180190297 50000</code>")
            return
        
        user_id = int(parts[1])
        amount = int(parts[2])
        
        user = get_user(user_id)
        if not user:
            await msg.answer(f"❌ Không tìm thấy user ID: {user_id}")
            return
        
        old_balance = user[3] if user and isinstance(user[3], int) else 0
        update_balance(user_id, amount, f"Admin {msg.from_user.id} cộng {amount}đ")
        add_admin_log(msg.from_user.id, "add_money", user_id, f"{amount}đ")
        
        new_user = get_user(user_id)
        new_balance = new_user[3] if new_user and isinstance(new_user[3], int) else 0
        
        await msg.answer(
            f"✅ Đã cộng {amount:,}đ cho user {user_id}\n"
            f"💰 Số dư mới: {new_balance:,}đ"
        )
        
        # Thông báo cho user
        await notify_user(
            user_id,
            "NẠP TIỀN THÀNH CÔNG",
            f"💵 Số tiền: {amount:,}đ\n"
            f"💰 Số dư hiện tại: {new_balance:,}đ\n\n"
            f"Cảm ơn bạn đã nạp tiền! 🎉"
        )
        
    except Exception as e:
        await msg.answer(f"❌ Lỗi: {str(e)}\nDùng: <code>/addmoney user_id số_tiền</code>")

@dp.message(Command("cancel"))
async def cancel(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer("❌ Đã hủy thao tác!")
# ==================== KIỂM TRA GIAO DỊCH ====================
@dp.message(Command("recent"))
async def recent_transactions(msg: Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        await msg.answer("⛔ Không có quyền!")
        return
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT trans_id, user_id, amount, note, created_at FROM recharge_history ORDER BY id DESC LIMIT 10")
    results = c.fetchall()
    
    if not results:
        await msg.answer("📭 Chưa có giao dịch nào!")
        return
    
    text = "📊 **10 GIAO DỊCH GẦN ĐÂY**\n\n"
    for r in results:
        time_str = r[4].replace('T', ' ')[:19] if r[4] else 'Không rõ'
        text += f"🔑 Mã: `{r[0] or 'N/A'}`\n👤 User: `{r[1]}`\n💰 {r[2]:,}đ\n📝 Mã nạp: {r[3] or 'Không'}\n📅 {time_str}\n━━━━━━━━━━━━━━━\n"
    
    await msg.answer(text)
    conn.close()
@dp.message(Command("userinfo"))
async def user_info(msg: Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        await msg.answer("⛔ Không có quyền!")
        return
    
    parts = msg.text.split()
    if len(parts) < 2:
        await msg.answer("❌ Sai format!\nDùng: /userinfo user_id\nVí dụ: /userinfo 5180190297")
        return
    
    user_id = int(parts[1])
    conn = get_db_connection()
    c = conn.cursor()
    
    # Lấy thông tin user
    c.execute("SELECT telegram_id, username, full_name, balance, total_recharge, total_spent, created_at FROM users WHERE telegram_id = %s", (user_id,))
    user = c.fetchone()
    
    if not user:
        await msg.answer(f"❌ Không tìm thấy user ID: {user_id}")
        conn.close()
        return
    
    # Lấy 5 giao dịch nạp gần nhất
    c.execute("SELECT trans_id, amount, note, created_at FROM recharge_history WHERE user_id = %s ORDER BY id DESC LIMIT 5", (user_id,))
    recharges = c.fetchall()
    
    # Lấy 10 lần mua gần nhất
    c.execute("""
        SELECT p.site, a.username, a.password, a.withdraw_password, a.real_name, a.bank_number, a.phone, p.amount, p.purchased_at 
        FROM purchases p 
        JOIN accounts a ON p.account_id = a.id 
        WHERE p.user_id = %s 
        ORDER BY p.purchased_at DESC 
        LIMIT 10
    """, (user_id,))
    purchases = c.fetchall()
    
    # Format thời gian
    created_time = user[6].replace('T', ' ')[:19] if user[6] else 'Không rõ'
    
    text = f"""👤 <b>THÔNG TIN USER</b>

🆔 <b>ID:</b> <code>{user[0]}</code>
📝 <b>Tên:</b> {user[2] or user[1] or 'Chưa có'}
💬 <b>Username:</b> @{user[1] or 'chưa có'}

💰 <b>Số dư:</b> {user[3]:,}đ
📥 <b>Tổng nạp:</b> {user[4]:,}đ
📤 <b>Tổng chi:</b> {user[5]:,}đ
📅 <b>Tham gia:</b> {created_time}

━━━━━━━━━━━━━━━━━━━━━━━
📊 <b>5 LẦN NẠP GẦN NHẤT:</b>
"""
    
    if recharges:
        for r in recharges:
            amount = r[1]
            note = r[2] or 'Không có mã'
            time_str = r[3].replace('T', ' ')[:19] if r[3] else 'Không rõ'
            text += f"\n💰 {amount:+,}đ | {note} | {time_str}"
    else:
        text += "\n📭 Chưa có lịch sử nạp"
    
    text += f"\n\n━━━━━━━━━━━━━━━━━━━━━━━\n🎮 <b>10 ACC ĐÃ MUA GẦN NHẤT:</b>\n"
    
    if purchases:
        for i, p in enumerate(purchases, 1):
            time_str = p[8].replace('T', ' ')[:19] if p[8] else 'Không rõ'
            text += f"""
🔹 <b>#{i}</b>
   🎮 {SITE_EMOJI.get(p[0], '🎮')} {p[0]}
   👤 <code>{p[1]}:{p[2]}</code>
   🔐 MK Rút: {p[3] or 'Chưa có'}
   📝 Tên thật: {p[4] or 'Chưa có'}
   🏦 STK: {p[5] or 'Chưa có'}
   📱 SĐT: {p[6] or 'Chưa có'}
   💰 {p[7]:,}đ | 📅 {time_str}
"""
    else:
        text += "\n📭 Chưa có lịch sử mua"
    
    await msg.answer(text)
    conn.close()
class SearchUserState(StatesGroup):
    waiting_for_user_id = State()

@dp.callback_query(F.data == "admin_search_user")
async def admin_search_user(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Không có quyền!", show_alert=True)
        return
    
    await call.message.answer(  # ✅ Đổi edit_text thành answer
        "🔍 <b>TRA CỨU THÔNG TIN USER</b>\n\n"
        "Nhập ID Telegram của user cần xem:\n"
        "Ví dụ: <code>5180190297</code>\n\n"
        "Hoặc nhập username: <code>@makkllai</code>\n\n"
        "Gửi /cancel để hủy"
    )
    
    # Xóa tin nhắn cũ để tránh rối
    try:
        await call.message.delete()
    except:
        pass
    
    await state.set_state(SearchUserState.waiting_for_user_id)

@dp.message(SearchUserState.waiting_for_user_id)
async def admin_show_user_info(msg: Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        return
    if msg.text == "/cancel":
        await state.clear()
        await msg.answer("❌ Đã hủy!")
        return
    
    search_key = msg.text.strip()
    
    conn = get_db_connection()
    c = conn.cursor()
    
    # Tìm user theo ID hoặc username
    if search_key.startswith('@'):
        username = search_key[1:]
        c.execute("SELECT telegram_id, username, full_name, balance, total_recharge, total_spent, created_at FROM users WHERE username = %s", (username,))
    else:
        try:
            user_id = int(search_key)
            c.execute("SELECT telegram_id, username, full_name, balance, total_recharge, total_spent, created_at FROM users WHERE telegram_id = %s", (user_id,))
        except ValueError:
            await msg.answer("❌ ID không hợp lệ! Vui lòng nhập số ID hoặc username có @")
            conn.close()
            return
    
    user = c.fetchone()
    
    if not user:
        await msg.answer(f"❌ Không tìm thấy user: {search_key}")
        conn.close()
        return
    
    # Lấy danh sách acc đã mua - GIỚI HẠN 15 ACC GẦN NHẤT
    c.execute("""
        SELECT p.site, a.username, a.password, a.withdraw_password, a.real_name, a.bank_number, a.phone, p.amount, p.purchased_at 
        FROM purchases p 
        JOIN accounts a ON p.account_id = a.id 
        WHERE p.user_id = %s 
        ORDER BY p.purchased_at DESC
        LIMIT 15
    """, (user[0],))
    purchases = c.fetchall()
    
    # Lấy tổng số acc để hiển thị
    c.execute("SELECT COUNT(*) FROM purchases WHERE user_id = %s", (user[0],))
    total_purchases = c.fetchone()[0]
    conn.close()
    
    # Format thời gian
    created_time = user[6].replace('T', ' ')[:19] if user[6] else "Không rõ"
    
    text = f"""👤 <b>THÔNG TIN USER</b>

🆔 <b>ID:</b> <code>{user[0]}</code>
📝 <b>Tên:</b> {user[2] or user[1] or 'Chưa có'}
💬 <b>Username:</b> @{user[1] or 'chưa có'}

━━━━━━━━━━━━━━━━━━━━━━━
💰 <b>Số dư:</b> {user[3]:,}đ
📥 <b>Tổng nạp:</b> {user[4]:,}đ
📤 <b>Tổng chi:</b> {user[5]:,}đ
📦 <b>Số acc đã mua:</b> {total_purchases}
📅 <b>Ngày tham gia:</b> {created_time}

━━━━━━━━━━━━━━━━━━━━━━━
🎮 <b>DANH SÁCH ACC ĐÃ MUA (15 mới nhất):</b>
"""
    
    if purchases:
        for i, p in enumerate(purchases, 1):
            time_str = p[8].replace('T', ' ')[:19] if p[8] else "Không rõ"
            text += f"\n🔹 <b>#{i}</b> - {SITE_EMOJI.get(p[0], '🎮')} {p[0]}\n"
            text += f"   👤 {p[1]}:{p[2]}\n"
            text += f"   🔐 MK Rút: {p[3] or 'Chưa có'}\n"
            text += f"   📝 Tên thật: {p[4] or 'Chưa có'}\n"
            text += f"   🏦 STK: {p[5] or 'Chưa có'}\n"
            text += f"   📱 SĐT: {p[6] or 'Chưa có'}\n"
            text += f"   💰 Giá: {p[7]:,}đ | 📅 {time_str}\n"
    else:
        text += "\n📭 Chưa mua account nào"
    
    if total_purchases > 15:
        text += f"\n... và {total_purchases - 15} acc khác"
    
    # Thêm nút hành động
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 CỘNG TIỀN", callback_data=f"admin_add_money_user_{user[0]}")],
        [InlineKeyboardButton(text="💸 TRỪ TIỀN", callback_data=f"admin_sub_money_user_{user[0]}")],
        [InlineKeyboardButton(text="🔍 TRA CỨU USER KHÁC", callback_data="admin_search_user")],
        [InlineKeyboardButton(text="🔙 Quay lại", callback_data="admin_dashboard")]
    ])
    
    await msg.answer(text, reply_markup=keyboard)
    await state.clear()

# Hỗ trợ cộng/trừ tiền nhanh từ kết quả tra cứu
@dp.callback_query(F.data.startswith("admin_add_money_user_"))
async def admin_add_money_from_search(call: CallbackQuery, state: FSMContext):
    user_id = int(call.data.split("_")[4])
    await state.update_data(user_id=user_id, action="add")
    await call.message.answer(f"💰 Nhập số tiền muốn CỘNG cho user {user_id}:")
    await state.set_state(MoneyState.waiting_for_amount)

@dp.callback_query(F.data.startswith("admin_sub_money_user_"))
async def admin_sub_money_from_search(call: CallbackQuery, state: FSMContext):
    user_id = int(call.data.split("_")[4])
    await state.update_data(user_id=user_id, action="sub")
    await call.message.answer(f"💸 Nhập số tiền muốn TRỪ cho user {user_id}:")
    await state.set_state(MoneyState.waiting_for_amount)

# Sửa lại hàm process_money để hỗ trợ user_id từ state
@dp.message(MoneyState.waiting_for_amount)
async def process_money(msg: Message, state: FSMContext):
    if msg.from_user.id not in ADMIN_IDS:
        return
    if msg.text == "/cancel":
        await state.clear()
        await msg.answer("❌ Đã hủy!")
        return
    try:
        amount = int(msg.text.strip())
        data = await state.get_data()
        user_id = data.get('user_id')
        action = data.get('action', 'add')
        
        # Nếu không có user_id trong state, hỏi lại
        if not user_id:
            parts = msg.text.split()
            if len(parts) >= 2:
                user_id = int(parts[0])
                amount = int(parts[1])
            else:
                await msg.answer("❌ Sai format!\nDùng: <code>user_id số_tiền</code>\nVí dụ: <code>5180190297 50000</code>")
                return
        
        if action == "sub":
            amount = -amount
        
        user = get_user(user_id)
        if not user:
            await msg.answer(f"❌ Không tìm thấy user ID: {user_id}")
            return
        
        old_balance = user[3] if user and isinstance(user[3], int) else 0
        update_balance(user_id, amount, f"Admin {'cộng' if amount > 0 else 'trừ'} {abs(amount)}đ")
        add_admin_log(msg.from_user.id, f"{'add' if amount > 0 else 'sub'}_money", user_id, f"{abs(amount)}đ")
        new_user = get_user(user_id)
        new_balance = new_user[3] if new_user and isinstance(new_user[3], int) else 0
        
        await msg.answer(
            f"✅ Đã {'cộng' if amount > 0 else 'trừ'} {abs(amount):,}đ cho user {user_id}\n"
            f"💰 Số dư cũ: {old_balance:,}đ → Số dư mới: {new_balance:,}đ"
        )
        
        # Thông báo cho user
        if amount > 0:
            await notify_user(user_id, "NẠP TIỀN THÀNH CÔNG", f"💵 Số tiền: {amount:,}đ\n💰 Số dư mới: {new_balance:,}đ")
        else:
            await notify_user(user_id, "TRỪ TIỀN TÀI KHOẢN", f"💸 Số tiền: {abs(amount):,}đ\n💰 Số dư mới: {new_balance:,}đ")
        
        await state.clear()
        await msg.answer("👑 ADMIN PANEL", reply_markup=admin_menu())
        
    except Exception as e:
        await msg.answer(f"❌ Lỗi: {str(e)}\nDùng: <code>user_id số_tiền</code>")
# ==================== CHẠY WEBHOOK ====================
def run_webhook():
    uvicorn.run(sepay_app, host="0.0.0.0", port=8000)

# Sửa lại hàm main
async def main():
    fix_ref_code()
    migrate_db()
    init_db()
    logger.info("🚀 Bot đang chạy...")
    
    # Chạy webhook trong thread riêng
    webhook_thread = threading.Thread(target=run_webhook, daemon=True)
    webhook_thread.start()
    logger.info("✅ Webhook server started on port 8000")
    
    logger.info("✅ Bot sẵn sàng!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
