import json
import sqlite3
import os
import traceback
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

app = FastAPI()

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "bot.db")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8670258284:AAEE74b5XcUnDJUG6DpH8QJkixL8WWj8NCw")
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

async def send_notification(telegram_id: int, amount: int, new_balance: int):
    try:
        text = f"""✅ <b>NẠP TIỀN THÀNH CÔNG!</b>

💵 <b>Số tiền:</b> {amount:,}đ
💰 <b>Số dư hiện tại:</b> {new_balance:,}đ

Cảm ơn bạn đã nạp tiền! 🎉"""
        await bot.send_message(telegram_id, text)
        print(f"✅ Đã gửi thông báo cho user {telegram_id}")
    except Exception as e:
        print(f"❌ Lỗi gửi thông báo: {e}")

def update_balance(telegram_id: int, amount: int, trans_id: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Kiểm tra trùng lặp
    c.execute("SELECT id FROM recharge_history WHERE trans_id = ?", (trans_id,))
    if c.fetchone():
        conn.close()
        return False, 0
    
    # Lấy số dư cũ
    c.execute("SELECT balance FROM users WHERE telegram_id = ?", (telegram_id,))
    old_balance_row = c.fetchone()
    old_balance = old_balance_row[0] if old_balance_row else 0
    
    # Cộng tiền
    c.execute("UPDATE users SET balance = balance + ? WHERE telegram_id = ?", (amount, telegram_id))
    c.execute("UPDATE users SET total_recharge = total_recharge + ? WHERE telegram_id = ?", (amount, telegram_id))
    c.execute("INSERT INTO recharge_history (user_id, amount, trans_id, created_at) VALUES (?, ?, ?, ?)",
              (telegram_id, amount, trans_id, datetime.now().isoformat()))
    
    # Lấy số dư mới
    c.execute("SELECT balance FROM users WHERE telegram_id = ?", (telegram_id,))
    new_balance_row = c.fetchone()
    new_balance = new_balance_row[0] if new_balance_row else old_balance + amount
    
    conn.commit()
    conn.close()
    return True, new_balance

@app.post("/webhook/sepay")
async def sepay_webhook(request: Request):
    try:
        print("📥 Nhận được webhook từ SePay")
        data = await request.json()
        print(f"📦 Data: {data}")
        
        amount = data.get("amount", 0)
        content = data.get("content", "")
        trans_id = data.get("transaction_id", "")
        
        print(f"💰 Amount: {amount}, Content: {content}, TransID: {trans_id}")
        
        # Parse nội dung: "NAP 5180190297"
        parts = content.split()
        if len(parts) >= 2 and parts[0].upper() == "NAP":
            telegram_id = int(parts[1])
            print(f"👤 User ID: {telegram_id}")
            
            success, new_balance = update_balance(telegram_id, amount, trans_id)
            
            if success:
                print(f"✅ Cộng tiền thành công! Số dư mới: {new_balance}")
                await send_notification(telegram_id, amount, new_balance)
                return {"status": "success", "message": f"Added {amount} to user {telegram_id}"}
            else:
                print("⚠️ Giao dịch đã được xử lý trước đó")
                return {"status": "duplicate", "message": "Transaction already processed"}
        
        print("⚠️ Nội dung không đúng format")
        return {"status": "ignored", "message": "Invalid content format"}
        
    except Exception as e:
        print(f"❌ LỖI: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def root():
    return {"status": "Bot is running", "webhook": "/webhook/sepay"}

@app.on_event("shutdown")
async def shutdown():
    await bot.session.close()