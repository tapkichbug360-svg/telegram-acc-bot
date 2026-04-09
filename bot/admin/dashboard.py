from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from bot.config import settings
from bot.database.repositories import (
    get_total_revenue, get_total_users, get_total_sales, 
    get_available_accounts_count, get_sales_by_site
)

router = Router()

async def get_admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📈 Doanh thu theo site", callback_data="stats_revenue_by_site")],
        [InlineKeyboardButton(text="📊 Thống kê tổng quan", callback_data="stats_overview")],
        [InlineKeyboardButton(text="➕ Thêm account mới", callback_data="add_account_menu")],
        [InlineKeyboardButton(text="📋 Báo cáo doanh thu", callback_data="export_report")]
    ])

@router.message(Command("admin"))
async def admin_panel(message: Message, db: AsyncSession):
    if message.from_user.id not in settings.ADMIN_IDS:
        await message.answer("⛔ Bạn không có quyền truy cập!")
        return
    
    total_revenue = await get_total_revenue(db)
    total_users = await get_total_users(db)
    total_sales = await get_total_sales(db)
    available_accs = await get_available_accounts_count(db)
    
    dashboard_text = f"""
📊 **DASHBOARD QUẢN LÝ BÁN ACC**

💰 **DOANH THU:**
• Tổng doanh thu: {total_revenue:,.0f} VND
• Số giao dịch: {total_sales}

👥 **NGƯỜI DÙNG:**
• Tổng số users: {total_users}

🎮 **KHO ACC:**
• Còn trống: {available_accs}
• Giá mỗi acc: 20,000 VND
"""
    
    await message.answer(dashboard_text, reply_markup=await get_admin_keyboard())

@router.callback_query(F.data == "stats_revenue_by_site")
async def show_revenue_by_site(callback: CallbackQuery, db: AsyncSession):
    sales_data = await get_sales_by_site(db)
    
    text = "📊 **DOANH THU THEO SITE:**\n\n"
    sites = ["SC88", "C168", "CM88", "FLY88", "F168"]
    
    for site in sites:
        count = sales_data.get(site, 0)
        revenue = count * 20000
        text += f"🎮 **{site}:**\n   💰 {revenue:,.0f} VND | 📦 {count} acc\n\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Quay lại", callback_data="back_to_admin")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)

@router.callback_query(F.data == "stats_overview")
async def show_overview(callback: CallbackQuery, db: AsyncSession):
    total_revenue = await get_total_revenue(db)
    total_users = await get_total_users(db)
    total_sales = await get_total_sales(db)
    available_accs = await get_available_accounts_count(db)
    
    text = f"""
📈 **THỐNG KÊ TỔNG QUAN**

💰 Doanh thu: {total_revenue:,.0f} VND
📦 Giao dịch: {total_sales}
👥 Users: {total_users}
🎮 Acc còn: {available_accs}

📅 Cập nhật: vừa xong
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Quay lại", callback_data="back_to_admin")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)

@router.callback_query(F.data == "back_to_admin")
async def back_to_admin(callback: CallbackQuery, db: AsyncSession):
    await admin_panel(callback.message, db)
