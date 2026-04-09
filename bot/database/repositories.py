from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from bot.database.models import User, Account, Purchase
from datetime import datetime

async def register_user(db: AsyncSession, telegram_id: int, username: str, first_name: str):
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        user = User(telegram_id=telegram_id, username=username, first_name=first_name)
        db.add(user)
        await db.commit()
    return user

async def get_available_account(db: AsyncSession, site: str):
    result = await db.execute(
        select(Account).where(
            Account.site == site,
            Account.is_sold == False
        ).limit(1)
    )
    return result.scalar_one_or_none()

async def mark_account_sold(db: AsyncSession, account_id: int, user_id: int):
    await db.execute(
        update(Account)
        .where(Account.id == account_id)
        .values(is_sold=True, sold_at=datetime.now(), sold_to_user_id=user_id)
    )
    await db.commit()

async def create_purchase(db: AsyncSession, user_id: int, account_id: int, site: str, amount: float):
    purchase = Purchase(user_id=user_id, account_id=account_id, site=site, amount=amount)
    db.add(purchase)
    await db.commit()
    return purchase

async def get_total_revenue(db: AsyncSession):
    result = await db.execute(select(func.sum(Purchase.amount)))
    return result.scalar() or 0

async def get_total_users(db: AsyncSession):
    result = await db.execute(select(func.count(User.id)))
    return result.scalar() or 0

async def get_total_sales(db: AsyncSession):
    result = await db.execute(select(func.count(Purchase.id)))
    return result.scalar() or 0

async def get_available_accounts_count(db: AsyncSession):
    result = await db.execute(select(func.count(Account.id)).where(Account.is_sold == False))
    return result.scalar() or 0

async def get_sales_by_site(db: AsyncSession):
    result = await db.execute(
        select(Account.site, func.count(Account.id))
        .where(Account.is_sold == True)
        .group_by(Account.site)
    )
    return {row[0]: row[1] for row in result}

async def add_new_account(db: AsyncSession, site: str, username: str, password: str, price: float = 20000):
    account = Account(site=site, username=username, password=password, price=price)
    db.add(account)
    await db.commit()
    return account

async def get_user_purchases(db: AsyncSession, user_id: int, limit: int = 10):
    result = await db.execute(
        select(Purchase)
        .where(Purchase.user_id == user_id)
        .order_by(Purchase.purchased_at.desc())
        .limit(limit)
    )
    purchases = result.scalars().all()
    
    purchase_list = []
    for p in purchases:
        acc_result = await db.execute(select(Account).where(Account.id == p.account_id))
        acc = acc_result.scalar_one_or_none()
        purchase_list.append({
            'site': p.site,
            'username': acc.username if acc else 'N/A',
            'password': acc.password if acc else 'N/A',
            'amount': p.amount,
            'date': p.purchased_at
        })
    return purchase_list

async def get_user_total_spent(db: AsyncSession, user_id: int):
    result = await db.execute(
        select(func.sum(Purchase.amount)).where(Purchase.user_id == user_id)
    )
    return result.scalar() or 0
