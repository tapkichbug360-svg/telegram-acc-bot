from aiogram import Router, F
from aiogram.types import CallbackQuery, FSInputFile
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
import pandas as pd
import os
from bot.database.models import Purchase, User

router = Router()

@router.callback_query(F.data == "export_report")
async def export_full_report(callback: CallbackQuery, db: AsyncSession):
    await callback.message.edit_text("📊 Đang tạo báo cáo...")
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    # Lấy dữ liệu 30 ngày
    result = await db.execute(
        select(Purchase).where(
            Purchase.purchased_at >= start_date,
            Purchase.purchased_at <= end_date
        ).order_by(Purchase.purchased_at)
    )
    purchases = result.scalars().all()
    
    # Tạo DataFrame
    data = []
    for p in purchases:
        data.append({
            'Ngày': p.purchased_at.strftime('%d/%m/%Y'),
            'Site': p.site,
            'User ID': p.user_id,
            'Số tiền': p.amount,
            'Thời gian': p.purchased_at.strftime('%H:%M:%S')
        })
    
    df = pd.DataFrame(data)
    
    if df.empty:
        await callback.message.edit_text("📭 Chưa có dữ liệu giao dịch nào!")
        return
    
    # Thống kê theo ngày
    daily_stats = df.groupby('Ngày').agg({
        'Số tiền': 'sum',
        'User ID': 'count'
    }).rename(columns={'Số tiền': 'Doanh thu', 'User ID': 'Số giao dịch'})
    
    # Thống kê theo site
    site_stats = df.groupby('Site').agg({
        'Số tiền': 'sum',
        'User ID': 'count'
    }).rename(columns={'Số tiền': 'Doanh thu', 'User ID': 'Số lượng'})
    
    # Xuất Excel
    filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    with pd.ExcelWriter(filename) as writer:
        df.to_excel(writer, sheet_name='Chi tiết giao dịch', index=False)
        daily_stats.to_excel(writer, sheet_name='Doanh thu theo ngày')
        site_stats.to_excel(writer, sheet_name='Doanh thu theo site')
    
    await callback.message.answer_document(
        FSInputFile(filename),
        caption=f"📊 **Báo cáo doanh thu**\n{start_date.strftime('%d/%m/%Y')} - {end_date.strftime('%d/%m/%Y')}"
    )
    
    os.remove(filename)
    
    from bot.admin.dashboard import back_to_admin
    await back_to_admin(callback, db)
