from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from config import DB_URL

Base = declarative_base()

class Database:
    def __init__(self, db_url: str):
        self.engine = create_async_engine(db_url, echo=True)
        self.session_factory = async_sessionmaker(
            self.engine, 
            class_=AsyncSession, 
            expire_on_commit=False
        )
    
    async def get_session(self):
        async with self.session_factory() as session:
            yield session
    
    async def create_tables(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

# ВАЖНО: создаем экземпляр здесь
db = Database(DB_URL)