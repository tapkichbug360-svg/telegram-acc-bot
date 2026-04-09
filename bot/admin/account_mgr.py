from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from bot.database.repositories import add_new_account

router = Router()

class AddAccountState(StatesGroup):
    waiting_for_site = State()
    waiting_for_account = State()

@router.callback_query(F.data == "add_account_menu")
async def show_add_account_menu(callback: CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 SC88", callback_data="add_site_SC88")],
        [InlineKeyboardButton(text="🎮 C168", callback_data="add_site_C168")],
        [InlineKeyboardButton(text="🎮 CM88", callback_data="add_site_CM88")],
        [InlineKeyboardButton(text="🎮 FLY88", callback_data="add_site_FLY88")],
        [InlineKeyboardButton(text="🎮 F168", callback_data="add_site_F168")],
        [InlineKeyboardButton(text="◀️ Hủy", callback_data="back_to_admin")]
    ])
    
    await callback.message.edit_text(
        "➕ **THÊM ACCOUNT MỚI**\n\n"
        "💰 Giá mặc định: 20,000 VND/acc\n"
        "📝 Format: username | password\n\n"
        "**Chọn site:**",
        reply_markup=keyboard
    )
    await state.set_state(AddAccountState.waiting_for_site)

@router.callback_query(AddAccountState.waiting_for_site, F.data.startswith("add_site_"))
async def get_site(callback: CallbackQuery, state: FSMContext):
    site = callback.data.split("_")[2]
    await state.update_data(site=site)
    
    await callback.message.edit_text(
        f"📝 **Nhập thông tin account cho {site}**\n\n"
        f"Format: username | password\n"
        f"Ví dụ: ipuser123 | abcxyz123\n\n"
        f"Gửi /cancel để hủy"
    )
    await state.set_state(AddAccountState.waiting_for_account)

@router.message(AddAccountState.waiting_for_account)
async def save_account(message: Message, state: FSMContext, db: AsyncSession):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Đã hủy thêm account!")
        return
    
    data = await state.get_data()
    site = data.get("site")
    
    try:
        if "|" not in message.text:
            raise ValueError("Thiếu dấu |")
        
        username, password = message.text.split("|")
        username = username.strip()
        password = password.strip()
        
        if not username or not password:
            raise ValueError("Username hoặc password trống")
        
        await add_new_account(db, site, username, password)
        
        await message.answer(
            f"✅ **Đã thêm account {site} thành công!**\n\n"
            f"👤 Username: {username}\n"
            f"🔑 Password: {password}\n"
            f"💰 Giá: 20,000 VND"
        )
        await state.clear()
        
    except Exception as e:
        await message.answer(
            f"❌ **Lỗi!**\n{str(e)}\n\n"
            f"Format đúng: username | password\n"
            f"Gửi /cancel để hủy"
        )

@router.message(Command("cancel"))
async def cancel_add(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Đã hủy thao tác!")
