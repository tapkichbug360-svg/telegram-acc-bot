from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import enum

Base = declarative_base()

class SiteName(enum.Enum):
    SC88 = "SC88"
    C168 = "C168"
    CM88 = "CM88"
    FLY88 = "FLY88"
    F168 = "F168"

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    username = Column(String, nullable=True)
    first_name = Column(String)
    total_spent = Column(Float, default=0)
    registered_at = Column(DateTime, default=datetime.now)

class Account(Base):
    __tablename__ = 'accounts'
    
    id = Column(Integer, primary_key=True)
    site = Column(String, nullable=False)
    username = Column(String, nullable=False)
    password = Column(String, nullable=False)
    price = Column(Float, default=20000)
    is_sold = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)
    sold_at = Column(DateTime, nullable=True)
    sold_to_user_id = Column(Integer, nullable=True)

class Purchase(Base):
    __tablename__ = 'purchases'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    account_id = Column(Integer, nullable=False)
    site = Column(String)
    amount = Column(Float)
    purchased_at = Column(DateTime, default=datetime.now)
