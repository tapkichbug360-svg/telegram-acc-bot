# database.py
import psycopg2
import os
from urllib.parse import urlparse

# Lấy connection string từ biến môi trường
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:Manh123@103.152.164.136:5432/telegram_bot")

def get_db_connection():
    """Kết nối đến PostgreSQL trên VPS"""
    return psycopg2.connect(DATABASE_URL)

def init_db():
    """Tạo bảng nếu chưa tồn tại"""
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        telegram_id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        balance INTEGER DEFAULT 0,
        total_recharge INTEGER DEFAULT 0,
        total_spent INTEGER DEFAULT 0,
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
        user_id INTEGER, account_id INTEGER, site TEXT, amount INTEGER, 
        purchased_at TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS recharge_history (
        id SERIAL PRIMARY KEY,
        user_id INTEGER, amount INTEGER, trans_id TEXT, created_at TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS admin_logs (
        id SERIAL PRIMARY KEY,
        admin_id INTEGER, action TEXT, target_id INTEGER, details TEXT, created_at TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS site_settings (
        site TEXT PRIMARY KEY, price INTEGER, is_active INTEGER DEFAULT 1)''')
    
    conn.commit()
    conn.close()
    print("✅ Database on VPS initialized")