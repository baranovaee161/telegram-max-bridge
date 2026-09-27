import asyncio
import logging
from datetime import datetime
import os
from asyncpg import create_pool, Pool
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv('DATABASE_URL')

# Глобальный пул подключений
db_pool: Pool = None

async def init_db():
    """Инициализируем подключение к БД и создаём таблицы"""
    global db_pool
    
    try:
        db_pool = await create_pool(
            DATABASE_URL,
            min_size=1,
            max_size=10,
            command_timeout=60
        )
        
        async with db_pool.acquire() as conn:
            # Таблица пользователей
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id BIGSERIAL PRIMARY KEY,
                    telegram_id BIGINT UNIQUE NOT NULL,
                    username TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_banned BOOLEAN DEFAULT FALSE
                )
            ''')
            
            # Таблица объявлений
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS ads (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL REFERENCES users(telegram_id),
                    username TEXT NOT NULL,
                    category TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    price TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE
                )
            ''')
            
            # Таблица админов
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS admins (
                    id BIGSERIAL PRIMARY KEY,
                    telegram_id BIGINT UNIQUE NOT NULL,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица жалоб
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS reports (
                    id BIGSERIAL PRIMARY KEY,
                    ad_id BIGINT NOT NULL REFERENCES ads(id) ON DELETE CASCADE,
                    reporter_id BIGINT NOT NULL,
                    reason TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
        
        logger.info("Database initialized successfully")
    
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

async def close_db():
    """Закрываем подключение к БД"""
    global db_pool
    if db_pool:
        await db_pool.close()
        logger.info("Database connection closed")

# ============= ПОЛЬЗОВАТЕЛИ =============

async def add_user(telegram_id: int, username: str = None):
    """Добавляем пользователя в БД"""
    async with db_pool.acquire() as conn:
        try:
            await conn.execute('''
                INSERT INTO users (telegram_id, username)
                VALUES ($1, $2)
                ON CONFLICT (telegram_id) DO UPDATE
                SET username = $2
            ''', telegram_id, username)
        except Exception as e:
            logger.error(f"Error adding user: {e}")

async def is_user_banned(telegram_id: int) -> bool:
    """Проверяем, забанен ли пользователь"""
    async with db_pool.acquire() as conn:
        result = await conn.fetchval('''
            SELECT is_banned FROM users WHERE telegram_id = $1
        ''', telegram_id)
        return result or False

async def ban_user(telegram_id: int):
    """Блокируем пользователя"""
    async with db_pool.acquire() as conn:
        try:
            await conn.execute('''
                UPDATE users SET is_banned = TRUE WHERE telegram_id = $1
            ''', telegram_id)
            logger.info(f"User {telegram_id} banned")
        except Exception as e:
            logger.error(f"Error banning user: {e}")

# ============= ОБЪЯВЛЕНИЯ =============

async def add_ad(user_id: int, username: str, category: str, title: str, 
                 description: str, price: str) -> int:
    """Добавляем объявление в БД"""
    # Сначала добавляем пользователя (если его еще нет)
    await add_user(user_id, username)
    
    async with db_pool.acquire() as conn:
        try:
            ad_id = await conn.fetchval('''
                INSERT INTO ads (user_id, username, category, title, description, price)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
            ''', user_id, username, category, title, description, price)
            
            logger.info(f"Ad {ad_id} created by user {user_id}")
            return ad_id
        except Exception as e:
            logger.error(f"Error adding ad: {e}")
            raise

async def get_ads_by_category(category: str) -> list:
    """Получаем объявления по категории"""
    async with db_pool.acquire() as conn:
        try:
            rows = await conn.fetch('''
                SELECT id, user_id, username, category, title, description, price, created_at
                FROM ads
                WHERE category = $1 AND is_active = TRUE
                ORDER BY created_at DESC
            ''', category)
            
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error fetching ads by category: {e}")
            return []

async def get_all_ads() -> list:
    """Получаем все активные объявления"""
    async with db_pool.acquire() as conn:
        try:
            rows = await conn.fetch('''
                SELECT id, user_id, username, category, title, description, price, created_at
                FROM ads
                WHERE is_active = TRUE
                ORDER BY created_at DESC
            ''')
            
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error fetching all ads: {e}")
            return []

async def get_user_ads(user_id: int) -> list:
    """Получаем объявления пользователя"""
    async with db_pool.acquire() as conn:
        try:
            rows = await conn.fetch('''
                SELECT id, user_id, username, category, title, description, price, created_at
                FROM ads
                WHERE user_id = $1 AND is_active = TRUE
                ORDER BY created_at DESC
            ''', user_id)
            
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error fetching user ads: {e}")
            return []

async def delete_ad(ad_id: int, user_id: int = None) -> bool:
    """Удаляем объявление (пользователь или админ)"""
    async with db_pool.acquire() as conn:
        try:
            if user_id:
                # Проверяем, что объявление принадлежит пользователю
                owner = await conn.fetchval('''
                    SELECT user_id FROM ads WHERE id = $1
                ''', ad_id)
                
                if owner != user_id:
                    logger.warning(f"User {user_id} tried to delete ad {ad_id} they don't own")
                    return False
            
            await conn.execute('''
                UPDATE ads SET is_active = FALSE WHERE id = $1
            ''', ad_id)
            
            logger.info(f"Ad {ad_id} deleted")
            return True
        except Exception as e:
            logger.error(f"Error deleting ad: {e}")
            return False

async def get_ad_by_id(ad_id: int) -> dict:
    """Получаем объявление по ID"""
    async with db_pool.acquire() as conn:
        try:
            row = await conn.fetchrow('''
                SELECT id, user_id, username, category, title, description, price, created_at
                FROM ads
                WHERE id = $1 AND is_active = TRUE
            ''', ad_id)
            
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error fetching ad: {e}")
            return None

# ============= АДМИНЫ =============

async def is_admin(telegram_id: int) -> bool:
    """Проверяем, является ли пользователь админом"""
    async with db_pool.acquire() as conn:
        result = await conn.fetchval('''
            SELECT TRUE FROM admins WHERE telegram_id = $1
        ''', telegram_id)
        return bool(result)

async def add_admin(telegram_id: int):
    """Добавляем админа"""
    async with db_pool.acquire() as conn:
        try:
            await conn.execute('''
                INSERT INTO admins (telegram_id)
                VALUES ($1)
                ON CONFLICT (telegram_id) DO NOTHING
            ''', telegram_id)
            logger.info(f"User {telegram_id} added as admin")
        except Exception as e:
            logger.error(f"Error adding admin: {e}")

async def remove_admin(telegram_id: int):
    """Удаляем админа"""
    async with db_pool.acquire() as conn:
        try:
            await conn.execute('''
                DELETE FROM admins WHERE telegram_id = $1
            ''', telegram_id)
            logger.info(f"User {telegram_id} removed from admins")
        except Exception as e:
            logger.error(f"Error removing admin: {e}")

# ============= ЖАЛОБЫ =============

async def add_report(ad_id: int, reporter_id: int, reason: str = None):
    """Добавляем жалобу на объявление"""
    async with db_pool.acquire() as conn:
        try:
            report_id = await conn.fetchval('''
                INSERT INTO reports (ad_id, reporter_id, reason)
                VALUES ($1, $2, $3)
                RETURNING id
            ''', ad_id, reporter_id, reason)
            
            logger.info(f"Report {report_id} created for ad {ad_id}")
            return report_id
        except Exception as e:
            logger.error(f"Error adding report: {e}")
            return None

async def get_reports() -> list:
    """Получаем все жалобы"""
    async with db_pool.acquire() as conn:
        try:
            rows = await conn.fetch('''
                SELECT id, ad_id, reporter_id, reason, created_at
                FROM reports
                ORDER BY created_at DESC
            ''')
            
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error fetching reports: {e}")
            return []

async def delete_report(report_id: int):
    """Удаляем жалобу"""
    async with db_pool.acquire() as conn:
        try:
            await conn.execute('''
                DELETE FROM reports WHERE id = $1
            ''', report_id)
            logger.info(f"Report {report_id} deleted")
        except Exception as e:
            logger.error(f"Error deleting report: {e}")
