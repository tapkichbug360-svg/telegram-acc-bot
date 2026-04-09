from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession
from bot.database.repositories import get_user_total_spent, get_user_purchases

router = Router()

@router.callback_query(F.data == "my_profile")
async def show_profile(callback: CallbackQuery, db: AsyncSession):
    total_spent = await get_user_total_spent(db, callback.from_user.id)
    purchases_count = len(await get_user_purchases(db, callback.from_user.id, 100))
    
    text = f"""
👤 **HỒ SƠ CỦA TÔI**

🆔 **ID:** {callback.from_user.id}
📝 **Tên:** {callback.from_user.first_name}
👤 **Username:** @{callback.from_user.username or 'chưa có'}

📊 **THỐNG KÊ:**
• 💰 Đã chi: {total_spent:,.0f} VND
• 📦 Đã mua: {purchases_count} account
• 🎮 Site: SC88, C168, CM88, FLY88, F168

📅 Tham gia: {callback.from_user.id}
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Mua thêm", callback_data="buy_account")],
        [InlineKeyboardButton(text="📜 Lịch sử", callback_data="purchase_history")],
        [InlineKeyboardButton(text="🔙 Quay lại", callback_data="back_to_menu")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)
