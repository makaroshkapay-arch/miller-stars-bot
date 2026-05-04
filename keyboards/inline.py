from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def main_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="💎 Купить Звезды", callback_data="buy_stars_menu"),
        InlineKeyboardButton(text="⭐ Продать Звезды", callback_data="sell_stars_menu")
    )
    builder.row(
        InlineKeyboardButton(text="🎁 Маркет (Купить NFT)", callback_data="nft_market"),
        InlineKeyboardButton(text="💰 Продать NFT", callback_data="sell_nft_menu")
    )
    builder.row(
        InlineKeyboardButton(text="🎀 Купить подарки (Gifts)", callback_data="buy_gifts_menu")
    )
    builder.row(
        InlineKeyboardButton(text="👤 Профиль / Кошелек", callback_data="profile"),
        InlineKeyboardButton(text="📞 Поддержка", callback_data="support")
    )
    builder.row(
        InlineKeyboardButton(text="🔗 Реферальная программа", callback_data="referral_menu")
    )
    return builder.as_markup()

def buy_stars_packs_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="100 Звезд — 1.8 USDT", callback_data="buy_pack_100"))
    builder.row(InlineKeyboardButton(text="500 Звезд — 9 USDT", callback_data="buy_pack_500"))
    builder.row(InlineKeyboardButton(text="1000 Звезд + Бонус 50 — 19 USDT", callback_data="buy_pack_1050"))
    builder.row(InlineKeyboardButton(text="📝 Другая сумма", callback_data="custom_stars"))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu"))
    return builder.as_markup()

def payment_keyboard(pay_url: str, invoice_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💳 Оплатить", url=pay_url))
    builder.row(
        InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"check_payment_{invoice_id}"),
        InlineKeyboardButton(text="🔄 Проверить", callback_data=f"check_payment_{invoice_id}")
    )
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="buy_stars_menu"))
    return builder.as_markup()

def referral_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📋 Мои рефералы", callback_data="referrals_list"))
    builder.row(InlineKeyboardButton(text="💎 Вывести звезды", callback_data="withdraw_referral"))
    builder.row(InlineKeyboardButton(text="🔗 Получить ссылку", callback_data="get_referral_link"))
    builder.row(InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu"))
    return builder.as_markup()