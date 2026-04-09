from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession
from bot.database.repositories import get_user_purchases

router = Router()

@router.callback_query(F.data == "purchase_history")
async def show_history(callback: CallbackQuery, db: AsyncSession):
    purchases = await get_user_purchases(db, callback.from_user.id, 10)
    
    if not purchases:
        await callback.message.edit_text(
            "📭 **Bạn chưa mua account nào!**\n\nHãy bấm nút MUA để bắt đầu.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎮 Mua ngay", callback_data="buy_account")]
            ])
        )
        return
    
    text = "📜 **LỊCH SỬ MUA HÀNG**\n\n"
    for i, p in enumerate(purchases, 1):
        text += f"{i}. 🎮 {p['site']}\n"
        text += f"   👤 {p['username']}:{p['password']}\n"
        text += f"   💰 {p['amount']:,.0f} VND\n"
        text += f"   📅 {p['date'].strftime('%d/%m/%Y %H:%M')}\n\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Quay lại", callback_data="back_to_menu")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard)
