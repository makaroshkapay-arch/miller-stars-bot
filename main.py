import asyncio
import logging
import sys
from pathlib import Path

# Добавляем корневую папку в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent))

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import BOT_TOKEN, DB_URL
from handlers.admin import router as admin_router
from handlers.nft_marketplace import router as nft_router
from handlers.gift_purchases import router as gift_router

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    # Инициализация БД
    logger.info("Initializing database...")
    
    # Импортируем функции для работы с БД
    from database.core import init_db, get_db, close_db
    
    try:
        await init_db(DB_URL)
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        return
    
    # Проверяем инициализацию через get_db()
    db = get_db()
    logger.info(f"Database object: {db}")
    
    # Создание бота и диспетчера
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    
    # Подключение роутеров (ВАЖЕН ПОРЯДОК!)
    from handlers.user import router as user_router
    
    # 1. Админ-роутер (высший приоритет)
    dp.include_router(admin_router)
    
    # 2. NFT-роутер
    dp.include_router(nft_router)
    
    # 3. Роутер подарков (ДОЛЖЕН БЫТЬ ПЕРЕД user_router!)
    dp.include_router(gift_router)
    
    # 4. Пользовательский роутер (самый низкий приоритет)
    dp.include_router(user_router)
    
    # Проверка подключенных роутеров
    logger.info(f"Connected routers: {len(dp.sub_routers)}")
    
    # Запуск бота
    logger.info("Starting bot polling...")
    try:
        await dp.start_polling(bot, skip_updates=True)  # skip_updates=True важно!
    except Exception as e:
        logger.error(f"Bot error: {e}")
    finally:
        await close_db()
        logger.info("Bot stopped")

if __name__ == "__main__":
    # ❗ Только ОДИН вызов!
    asyncio.run(main())