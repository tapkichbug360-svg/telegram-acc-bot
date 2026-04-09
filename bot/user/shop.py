from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from bot.database.repositories import (
    get_available_account, mark_account_sold, 
    create_purchase, get_available_accounts_count
)

router = Router()

class BuyState(StatesGroup):
    selecting_site = State()

@router.callback_query(F.data == "buy_account")
async def select_site(callback: CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 SC88", callback_data="site_SC88")],
        [InlineKeyboardButton(text="🎮 C168", callback_data="site_C168")],
        [InlineKeyboardButton(text="🎮 CM88", callback_data="site_CM88")],
        [InlineKeyboardButton(text="🎮 FLY88", callback_data="site_FLY88")],
        [InlineKeyboardButton(text="🎮 F168", callback_data="site_F168")],
        [InlineKeyboardButton(text="◀️ Quay lại", callback_data="back_to_menu")]
    ])
    
    await callback.message.edit_text(
        "🎮 **CHỌN SITE ĐỂ MUA ACCOUNT**\n\n"
        "💰 Giá: 20,000 VND / acc",
        reply_markup=keyboard
    )
    await state.set_state(BuyState.selecting_site)

@router.callback_query(BuyState.selecting_site, F.data.startswith("site_"))
async def process_buy(callback: CallbackQuery, state: FSMContext, db: AsyncSession):
    site = callback.data.split("_")[1]
    
    account = await get_available_account(db, site)
    
    if not account:
        await callback.message.edit_text(
            f"❌ **Site {site} đã hết hàng!**\n\nVui lòng quay lại sau.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Thử lại", callback_data="buy_account")]
            ])
        )
        return
    
    await create_purchase(db, callback.from_user.id, account.id, site, 20000)
    await mark_account_sold(db, account.id, callback.from_user.id)
    
    await callback.message.edit_text(
        f"✅ **MUA THÀNH CÔNG!**\n\n"
        f"🎮 **Site:** {site}\n"
        f"👤 **Username:** {account.username}\n"
        f"🔑 **Password:** {account.password}\n\n"
        f"💰 **Giá:** 20,000 VND\n"
        f"📅 **Thời gian:** {account.sold_at.strftime('%H:%M:%S %d/%m/%Y') if account.sold_at else 'vừa xong'}\n\n"
        f"⚠️ Vui lòng đăng nhập ngay để kiểm tra!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛒 Mua tiếp", callback_data="buy_account")],
            [InlineKeyboardButton(text="🏠 Menu chính", callback_data="back_to_menu")]
        ])
    )
    await state.clear()
