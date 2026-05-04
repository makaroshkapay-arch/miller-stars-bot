"""
Скрипт миграции базы данных для добавления новых полей
"""
import asyncio
import logging
from sqlalchemy import text
from database.core import get_db, init_db
from config import DB_URL

logger = logging.getLogger(__name__)

async def migrate_database():
    """Добавляет новые колонки в существующую базу данных"""
    
    # Инициализируем подключение к БД
    db = await init_db(DB_URL)
    
    async with db.get_session() as session:
        try:
            # Проверяем существование колонок перед добавлением
            migrations = [
                # Добавляем колонку referrer_id
                """
                ALTER TABLE users ADD COLUMN referrer_id BIGINT
                """,
                # Добавляем колонку referral_code
                """
                ALTER TABLE users ADD COLUMN referral_code VARCHAR
                """,
                # Добавляем колонку referrals_count
                """
                ALTER TABLE users ADD COLUMN referrals_count INTEGER DEFAULT 0
                """,
                # Добавляем колонку recipient_username в crypto_orders
                """
                ALTER TABLE crypto_orders ADD COLUMN recipient_username VARCHAR
                """,
                # Создаем уникальный индекс для referral_code
                """
                CREATE UNIQUE INDEX IF NOT EXISTS ix_users_referral_code ON users (referral_code)
                """
            ]
            
            for migration in migrations:
                try:
                    await session.execute(text(migration))
                    logger.info(f"Выполнена миграция: {migration[:50]}...")
                except Exception as e:
                    if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                        logger.info(f"Колонка уже существует, пропускаем: {migration[:50]}...")
                    else:
                        logger.warning(f"Ошибка миграции: {e}")
                        # Продолжаем выполнение других миграций
            
            await session.commit()
            logger.info("Миграция базы данных успешно завершена")
            
        except Exception as e:
            logger.error(f"Ошибка при миграции: {e}")
            await session.rollback()
            raise

async def generate_referral_codes():
    """Генерирует реферальные коды для существующих пользователей, у которых их нет"""
    from database.models import User
    from sqlalchemy import select, update
    from utils.referral import ReferralSystem
    
    db = get_db()
    async with db.get_session() as session:
        # Находим пользователей без реферального кода
        result = await session.execute(
            select(User).where(User.referral_code == None)
        )
        users_without_code = result.scalars().all()
        
        for user in users_without_code:
            user.referral_code = ReferralSystem.generate_referral_code(user.user_id)
            logger.info(f"Сгенерирован код для пользователя {user.user_id}: {user.referral_code}")
        
        await session.commit()
        logger.info(f"Сгенерированы реферальные коды для {len(users_without_code)} пользователей")

async def main():
    """Основная функция миграции"""
    logger.info("Начинаем миграцию базы данных...")
    
    try:
        # Выполняем миграцию схемы
        await migrate_database()
        
        # Генерируем реферальные коды для существующих пользователей
        await generate_referral_codes()
        
        logger.info("Все миграции успешно выполнены!")
        
    except Exception as e:
        logger.error(f"Критическая ошибка при миграции: {e}")
    finally:
        from database.core import close_db
        await close_db()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())