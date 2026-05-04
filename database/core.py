from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from contextlib import asynccontextmanager
from .models import Base
import logging

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, url: str):
        self.engine = create_async_engine(url, echo=False)
        self.session_factory = async_sessionmaker(
            self.engine, 
            class_=AsyncSession, 
            expire_on_commit=False
        )

    async def create_tables(self):
        """Создание всех таблиц"""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Все таблицы созданы/проверены")

    @asynccontextmanager
    async def get_session(self):
        """Получение сессии с автоматическим коммитом/откатом"""
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def close(self):
        """Закрытие соединения с БД"""
        await self.engine.dispose()

# Глобальная переменная
db_instance = None

def get_db():
    """Получить экземпляр базы данных"""
    global db_instance
    if db_instance is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return db_instance

async def init_db(url: str):
    """Инициализация базы данных"""
    global db_instance
    db_instance = Database(url)
    
    # Создаем таблицы для новых моделей
    await db_instance.create_tables()
    
    # Выполняем миграции для существующих таблиц
    await run_migrations(db_instance)
    
    logger.info("Database initialized successfully")
    return db_instance

async def run_migrations(db: Database):
    """Выполняет миграции базы данных"""
    from sqlalchemy import text
    
    async with db.get_session() as session:
        # Список миграций
        migrations = [
            # Проверяем и добавляем новые колонки в users
            "ALTER TABLE users ADD COLUMN referrer_id BIGINT REFERENCES users(user_id)",
            "ALTER TABLE users ADD COLUMN referral_code VARCHAR",
            "ALTER TABLE users ADD COLUMN referrals_count INTEGER DEFAULT 0",
            
            # Добавляем колонку в crypto_orders
            "ALTER TABLE crypto_orders ADD COLUMN recipient_username VARCHAR",
            
            # Создаем индексы
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_referral_code ON users (referral_code)",
            "CREATE INDEX IF NOT EXISTS ix_users_referrer_id ON users (referrer_id)"
        ]
        
        for migration in migrations:
            try:
                await session.execute(text(migration))
                logger.info(f"Миграция выполнена: {migration[:60]}...")
            except Exception as e:
                # Игнорируем ошибки о существующих колонках
                if "already exists" not in str(e).lower() and "duplicate" not in str(e).lower():
                    logger.debug(f"Миграция пропущена (возможно уже выполнена): {e}")
        
        # Генерируем реферальные коды для пользователей без них
        try:
            result = await session.execute(
                text("SELECT user_id FROM users WHERE referral_code IS NULL")
            )
            users_without_code = result.fetchall()
            
            if users_without_code:
                from utils.referral import ReferralSystem
                for (user_id,) in users_without_code:
                    referral_code = ReferralSystem.generate_referral_code(user_id)
                    await session.execute(
                        text("UPDATE users SET referral_code = :code WHERE user_id = :uid"),
                        {"code": referral_code, "uid": user_id}
                    )
                logger.info(f"Сгенерированы реферальные коды для {len(users_without_code)} пользователей")
        except Exception as e:
            logger.debug(f"Генерация кодов пропущена: {e}")

async def close_db():
    """Закрытие соединения с БД"""
    global db_instance
    if db_instance is not None:
        await db_instance.close()
        db_instance = None
        logger.info("Database connection closed")