import os
from dotenv import load_dotenv

import os
from dotenv import load_dotenv

load_dotenv()

# Токены
BOT_TOKEN = os.getenv("BOT_TOKEN")
CRYPTO_BOT_TOKEN = os.getenv("CRYPTO_BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
ADMIN_IDS = [
    int(id.strip()) 
    for id in os.getenv("ADMIN_IDS", "").split(",") 
    if id.strip()
]

# База данных
DB_URL = os.getenv("DB_URL")
if not DB_URL:
    raise ValueError("DB_URL не задан в .env файле")

# Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Реферальная система
REFERRAL_REWARD = 2  # Звезд за приглашение
REFERRAL_FIRST_PURCHASE_REWARD = 5  # Дополнительно за первую покупку приглашенного

# Дополнительные проверки
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан в .env файле")
if not CRYPTO_BOT_TOKEN:
    raise ValueError("CRYPTO_BOT_TOKEN не задан в .env файле")