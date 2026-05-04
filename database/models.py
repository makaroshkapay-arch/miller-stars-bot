from datetime import datetime
from sqlalchemy import Column, Integer, BigInteger, String, Float, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import DeclarativeBase, relationship

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"

    user_id = Column(BigInteger, primary_key=True)
    username = Column(String, nullable=True)
    deals_count = Column(Integer, default=0)
    referral_balance = Column(Float, default=0.0)  # Баланс в звездах
    referrer_id = Column(BigInteger, nullable=True)  # ID пригласившего
    referral_code = Column(String, unique=True, nullable=True)  # Уникальный реферальный код
    referrals_count = Column(Integer, default=0)  # Количество приглашенных
    created_at = Column(DateTime, default=datetime.utcnow)

    crypto_orders = relationship("CryptoOrder", back_populates="user")
    nft_listings = relationship("NFTListing", back_populates="seller")
    gift_purchases = relationship("GiftPurchase", back_populates="user")

class CryptoOrder(Base):
    __tablename__ = "crypto_orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"))
    type = Column(String)  # buy_stars, sell_stars, buy_nft, buy_gift
    amount_stars = Column(Integer)
    crypto_amount = Column(Float)
    wallet_address = Column(String, nullable=True)
    crypto_invoice_id = Column(String, nullable=True)
    telegram_payment_charge_id = Column(String, nullable=True)
    recipient_username = Column(String, nullable=True)  # Получатель звезд
    status = Column(String, default="pending")  # pending, paid, cancelled, completed
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="crypto_orders")

class NFTListing(Base):
    __tablename__ = "nft_listings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    seller_id = Column(BigInteger, ForeignKey("users.user_id"))
    nft_link = Column(Text, nullable=True)
    gift_id = Column(Integer, nullable=True)
    nft_name = Column(String, nullable=True)
    price_stars = Column(Integer, nullable=True)
    price_crypto = Column(Float, nullable=True)
    is_verified = Column(Boolean, default=False)
    status = Column(String, default="active")  # active, sold, cancelled
    created_at = Column(DateTime, default=datetime.utcnow)

    seller = relationship("User", back_populates="nft_listings")

class GiftListing(Base):
    """Каталог доступных подарков"""
    __tablename__ = "gift_listings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    gift_id = Column(Integer, unique=True, nullable=False)
    gift_name = Column(String, nullable=False)
    price_stars = Column(Integer, nullable=True)
    price_crypto = Column(Float, nullable=True)
    image_url = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    available = Column(Boolean, default=True)
    total_sold = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    purchases = relationship("GiftPurchase", back_populates="gift")

class GiftPurchase(Base):
    """История покупок подарков"""
    __tablename__ = "gift_purchases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"))
    gift_id = Column(Integer, ForeignKey("gift_listings.id"))
    payment_type = Column(String)
    amount_stars = Column(Integer, nullable=True)
    amount_crypto = Column(Float, nullable=True)
    status = Column(String, default="pending")
    telegram_invoice_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="gift_purchases")
    gift = relationship("GiftListing", back_populates="purchases")