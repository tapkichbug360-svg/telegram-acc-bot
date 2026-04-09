import json
import sqlite3
import os
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException

app = FastAPI()

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "bot.db")

def update_balance(telegram_id: int, amount: int, trans_id: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Kiểm tra trùng lặp
    c.execute("SELECT id FROM recharge_history WHERE trans_id = ?", (trans_id,))
    if c.fetchone():
        conn.close()
        return False
    
    # Cộng tiền
    c.execute("UPDATE users SET balance = balance + ? WHERE telegram_id = ?", (amount, telegram_id))
    c.execute("UPDATE users SET total_recharge = total_recharge + ? WHERE telegram_id = ?", (amount, telegram_id))
    c.execute("INSERT INTO recharge_history (user_id, amount, trans_id, created_at) VALUES (?, ?, ?, ?)",
              (telegram_id, amount, trans_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return True

@app.post("/webhook/sepay")
async def sepay_webhook(request: Request):
    try:
        data = await request.json()
        amount = data.get("amount", 0)
        content = data.get("content", "")
        trans_id = data.get("transaction_id", "")
        
        # Parse nội dung: "NAP 5180190297"
        parts = content.split()
        if len(parts) >= 2 and parts[0].upper() == "NAP":
            telegram_id = int(parts[1])
            
            if update_balance(telegram_id, amount, trans_id):
                return {"status": "success", "message": f"Added {amount} to user {telegram_id}"}
            else:
                return {"status": "duplicate", "message": "Transaction already processed"}
        
        return {"status": "ignored", "message": "Invalid content format"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def root():
    return {"status": "Bot is running", "webhook": "/webhook/sepay"}