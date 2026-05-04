import hashlib
import secrets
from typing import Optional
from sqlalchemy import select
from database.models import User
from database.core import get_db

class ReferralSystem:
    REFERRAL_REWARD = 2  # Звезд за приглашенного
    FIRST_PURCHASE_REWARD = 5  # Дополнительно за первую покупку приглашенного
    
    @staticmethod
    def generate_referral_code(user_id: int) -> str:
        """Генерирует уникальный реферальный код"""
        random_part = secrets.token_hex(4)
        code = f"REF{user_id}{random_part}"[:12]
        return code.upper()
    
    @staticmethod
    async def get_user_by_code(referral_code: str) -> Optional[User]:
        """Находит пользователя по реферальному коду"""
        db = get_db()
        async with db.get_session() as session:
            result = await session.execute(
                select(User).where(User.referral_code == referral_code)
            )
            return result.scalar_one_or_none()
    
    @staticmethod
    async def process_referral(new_user: User, referrer_code: str) -> bool:
        """Обрабатывает реферальное приглашение"""
        db = get_db()
        async with db.get_session() as session:
            # Находим пригласившего
            result = await session.execute(
                select(User).where(User.referral_code == referrer_code)
            )
            referrer = result.scalar_one_or_none()
            
            if referrer and referrer.user_id != new_user.user_id:
                # Устанавливаем связь
                new_user.referrer_id = referrer.user_id
                
                # Начисляем бонус пригласившему
                referrer.referral_balance += ReferralSystem.REFERRAL_REWARD
                referrer.referrals_count += 1
                
                await session.commit()
                return True
        return False
    
    @staticmethod
    async def reward_referrer_first_purchase(user_id: int):
        """Начисляет бонус рефереру за первую покупку приглашенного"""
        db = get_db()
        async with db.get_session() as session:
            result = await session.execute(
                select(User).where(User.user_id == user_id)
            )
            user = result.scalar_one_or_none()
            
            if user and user.referrer_id:
                result = await session.execute(
                    select(User).where(User.user_id == user.referrer_id)
                )
                referrer = result.scalar_one_or_none()
                
                if referrer:
                    referrer.referral_balance += ReferralSystem.FIRST_PURCHASE_REWARD
                    await session.commit()