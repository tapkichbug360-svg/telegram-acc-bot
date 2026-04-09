import asyncio
import os
import psycopg2
import logging
import threading
import uvicorn
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

# ==================== CẤU HÌNH ====================
BOT_TOKEN = "8670258284:AAEE74b5XcUnDJUG6DpH8QJkixL8WWj8NCw"
ADMIN_IDS = [5180190297, 6448523574]
ADMIN_USERNAMES = ["minhthune2003", "makkllai"]  # Thêm dòng này

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
    
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        telegram_id BIGINT PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        balance BIGINT DEFAULT 0,
        total_recharge BIGINT DEFAULT 0,
        total_spent BIGINT DEFAULT 0,
        created_at TEXT)''')
    
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

def get_user(telegram_id: int):  # Giữ nguyên, chỉ đổi trong database
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE telegram_id = %s", (telegram_id,))
    user = c.fetchone()
    if not user:
        c.execute("INSERT INTO users (telegram_id, created_at) VALUES (%s, %s)", 
                  (telegram_id, datetime.now().isoformat()))
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
    else:
        c.execute("UPDATE users SET total_spent = total_spent + %s WHERE telegram_id = %s", (-amount, telegram_id))
    c.execute("INSERT INTO recharge_history (user_id, amount, note, created_at) VALUES (%s, %s, %s, %s)",
              (telegram_id, amount, note, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def add_admin_log(admin_id: int, action: str, target_id: int = None, details: str = ""):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT INTO admin_logs (admin_id, action, target_id, details, created_at) VALUES (%s, %s, %s, %s, %s)",
              (admin_id, action, target_id, details, datetime.now().isoformat()))
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
              (user_id, datetime.now().isoformat(), account_id))
    conn.commit()
    conn.close()

def save_purchase(user_id: int, account_id: int, site: str, amount: int):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT INTO purchases (user_id, account_id, site, amount, purchased_at) VALUES (%s, %s, %s, %s, %s)",
              (user_id, account_id, site, amount, datetime.now().isoformat()))
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
              (site, username, password, withdraw_password, real_name, bank_number, phone, datetime.now().isoformat(), note))
    conn.commit()
    conn.close()

def bulk_add_accounts(site: str, accounts: List[Tuple[str, str]]):
    conn = get_db_connection()
    c = conn.cursor()
    for username, password in accounts:
        c.execute("INSERT INTO accounts (site, username, password, created_at) VALUES (%s, %s, %s, %s)",
                  (site, username, password, datetime.now().isoformat()))
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
            history.append({
                'site': p[3],
                'username': acc[0],
                'password': acc[1],
                'withdraw_password': acc[2] or "Chưa có",
                'real_name': acc[3] or "Chưa có",
                'bank_number': acc[4] or "Chưa có",
                'phone': acc[5] or "Chưa có",
                'amount': p[4],
                'date': p[5][:19]
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
    today = datetime.now().date().isoformat()
    c.execute("SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM purchases WHERE DATE(purchased_at) = %s", (today,))
    sales_count, revenue = c.fetchone()
    c.execute("SELECT COUNT(*) FROM users WHERE DATE(created_at) = %s", (today,))
    new_users = c.fetchone()[0]
    conn.close()
    return {'sales': sales_count or 0, 'revenue': revenue or 0, 'new_users': new_users}
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

def main_menu(user_balance: int = 0):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 MUA ACC", callback_data="buy")],
        [InlineKeyboardButton(text="💰 SỐ DƯ", callback_data="balance")],
        [InlineKeyboardButton(text="📜 LỊCH SỬ", callback_data="history")],
        [InlineKeyboardButton(text="💳 NẠP TIỀN", callback_data="recharge")],
        [InlineKeyboardButton(text="🆘 HỖ TRỢ", callback_data="support")]
    ])

def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 DASHBOARD", callback_data="admin_dashboard")],
        [InlineKeyboardButton(text="➕ THÊM ACC", callback_data="admin_add")],
        [InlineKeyboardButton(text="📦 NHẬP NHIỀU", callback_data="admin_bulk_add")],
        [InlineKeyboardButton(text="💰 CỘNG TIỀN", callback_data="admin_add_money")],
        [InlineKeyboardButton(text="💸 TRỪ TIỀN", callback_data="admin_sub_money")],
        [InlineKeyboardButton(text="👥 DANH SÁCH USER", callback_data="admin_users")],
        [InlineKeyboardButton(text="📦 KHO ACC", callback_data="admin_inventory")],
        [InlineKeyboardButton(text="💰 DOANH THU", callback_data="admin_revenue")],
        [InlineKeyboardButton(text="⚙️ CÀI GIÁ", callback_data="admin_price")]
    ])

# ==================== USER ====================
@dp.message(Command("start"))
async def start(msg: Message):
    user = get_user(msg.from_user.id)
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
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Quay lại", callback_data="menu")]
    ]))

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
    
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

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
    history = get_user_history(call.from_user.id)
    if not history:
        await call.message.edit_text("📭 Bạn chưa mua acc nào!", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛒 Mua ngay", callback_data="buy")],
            [InlineKeyboardButton(text="🔙 Quay lại", callback_data="menu")]
        ]))
        return
    text = "📜 <b>LỊCH SỬ MUA HÀNG</b>\n\n"
    for i, h in enumerate(history, 1):
        text += f"""🔹 <b>#{i}</b>
🎮 Site: {SITE_EMOJI[h['site']]} {h['site']}
👤 Username: <code>{h['username']}</code>
🔑 Password: <code>{h['password']}</code>
🔐 MK Rút: <code>{h.get('withdraw_password', 'Chưa có')}</code>
📝 Tên thật: {h.get('real_name', 'Chưa có')}
🏦 STK: {h.get('bank_number', 'Chưa có')}
📱 SĐT: {h.get('phone', 'Chưa có')}
💰 Giá: {h['amount']:,}đ
📅 Ngày mua: {h['date']}

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
📅 <b>Thời gian:</b> {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}

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
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Mua ngay", callback_data="buy")],
        [InlineKeyboardButton(text="🔙 Quay lại", callback_data="menu")]
    ]))

@dp.callback_query(F.data == "menu")
async def back_menu(call: CallbackQuery):
    user = get_user(call.from_user.id)
    balance = user[3] if user and isinstance(user[3], int) else 0
    await call.message.edit_text(
        f"🎉 <b>MENU CHÍNH</b>\n\n💰 Số dư: {balance:,}đ\n\n👇 Chọn chức năng:",
        reply_markup=main_menu(balance)
    )

# ==================== ADMIN ====================
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
    
    text = f"""
📊 <b>DASHBOARD TỔNG QUAN</b>

👥 <b>Thống kê user:</b>
• Tổng users: {user_count}
• Users mới hôm nay: {daily['new_users']}

💰 <b>Thống kê doanh thu:</b>
• Hôm nay: {daily['revenue']:,}đ ({daily['sales']} giao dịch)
• Tổng doanh thu: {total_revenue:,}đ
• Tổng acc đã bán: {total_sold}

📦 <b>Tồn kho:</b>
• Tổng acc còn: {total_inv}

📋 <b>Chi tiết theo site:</b>
"""
    for site in SITES:
        text += f"\n{SITE_EMOJI[site]} {site}: 📦{sold.get(site,0)} bán | ✅{inv.get(site,0)} còn | 💰{revenue.get(site,0):,}đ"
    
    await call.message.edit_text(text, reply_markup=admin_menu())

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
    
    await call.message.edit_text(text, reply_markup=admin_menu())

@dp.callback_query(F.data == "admin_add")
async def admin_add_menu(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Không có quyền!")
        return
    buttons = [[InlineKeyboardButton(text=f"{SITE_EMOJI[s]} {s}", callback_data=f"addsite_{s}")] for s in SITES]
    buttons.append([InlineKeyboardButton(text="🔙 Quay lại", callback_data="admin_dashboard")])
    await call.message.edit_text("➕ <b>THÊM ACCOUNT</b>\n\nChọn site:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(AddAccountState.waiting_for_site)

@dp.callback_query(F.data == "admin_bulk_add")
async def admin_bulk_add(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Không có quyền!")
        return
    buttons = [[InlineKeyboardButton(text=f"{SITE_EMOJI[s]} {s}", callback_data=f"bulk_{s}")] for s in SITES]
    buttons.append([InlineKeyboardButton(text="🔙 Quay lại", callback_data="admin_dashboard")])
    await call.message.edit_text("📦 <b>NHẬP NHIỀU ACCOUNT</b>\n\nChọn site:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
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
    await call.message.edit_text("💰 <b>CỘNG TIỀN CHO USER</b>\n\nFormat: <code>user_id số_tiền</code>\nVí dụ: <code>5180190297 50000</code>\n\nGửi /cancel để hủy")
    await state.set_state(MoneyState.waiting_for_user)

@dp.callback_query(F.data == "admin_sub_money")
async def admin_sub_money(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Không có quyền!")
        return
    await state.update_data(action="sub")
    await call.message.edit_text("💸 <b>TRỪ TIỀN CỦA USER</b>\n\nFormat: <code>user_id số_tiền</code>\nVí dụ: <code>5180190297 20000</code>\n\nGửi /cancel để hủy")
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

@dp.callback_query(F.data == "admin_users")
async def admin_users(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Không có quyền!")
        return
    users = get_all_users(30)
    text = "👥 <b>DANH SÁCH USER (Top 30 theo số dư)</b>\n\n"
    for i, u in enumerate(users, 1):
        balance = u[3] if isinstance(u[3], int) else 0
        total_recharge = u[4] if isinstance(u[4], int) else 0
        text += f"{i}. 🆔 <code>{u[0]}</code>\n"
        text += f"   👤 {u[2] or u[1] or 'No name'}\n"
        text += f"   💰 {balance:,}đ | 📥 {total_recharge:,}đ\n\n"
    await call.message.edit_text(text, reply_markup=admin_menu())

@dp.callback_query(F.data == "admin_inventory")
async def admin_inventory(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Không có quyền!")
        return
    inv = get_inventory()
    text = "📦 <b>KHO ACCOUNT (ADMIN)</b>\n\n"
    for site in SITES:
        text += f"{SITE_EMOJI[site]} {site}: {inv.get(site, 0)} acc\n"
    await call.message.edit_text(text, reply_markup=admin_menu())

@dp.callback_query(F.data == "admin_price")
async def admin_price_menu(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Không có quyền!")
        return
    buttons = [[InlineKeyboardButton(text=f"{SITE_EMOJI[s]} {s}", callback_data=f"price_{s}")] for s in SITES]
    buttons.append([InlineKeyboardButton(text="🔙 Quay lại", callback_data="admin_dashboard")])
    await call.message.edit_text("⚙️ <b>CÀI ĐẶT GIÁ THEO SITE</b>\n\nChọn site:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await state.set_state(PriceState.waiting_for_site)

@dp.callback_query(PriceState.waiting_for_site, F.data.startswith("price_"))
async def admin_set_price(call: CallbackQuery, state: FSMContext):
    site = call.data.split("_")[1]
    await state.update_data(site=site)
    current_price = SITE_PRICE.get(site, 20000)
    await call.message.edit_text(f"💰 Nhập giá mới cho {SITE_EMOJI[site]} {site}:\n\nGiá hiện tại: {current_price:,}đ\n\nGửi /cancel để hủy")
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

# ==================== CHẠY WEBHOOK ====================
def run_webhook():
    uvicorn.run(sepay_app, host="0.0.0.0", port=8000)

# Sửa lại hàm main
async def main():
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
