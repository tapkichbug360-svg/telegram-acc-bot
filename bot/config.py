import os
from typing import List
from dotenv import load_dotenv

load_dotenv()

class Settings:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN")
    ADMIN_IDS: List[int] = eval(os.getenv("ADMIN_IDS", "[5180190297]"))
    DB_URL: str = os.getenv("DB_URL", "sqlite+aiosqlite:///data/bot.db")

settings = Settings()
