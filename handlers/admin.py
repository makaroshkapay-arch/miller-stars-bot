from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from sqlalchemy import select, func
from config import ADMIN_ID
from database.models import CryptoOrder, NFTListing, User
from database.core import get_db

router = Router()

ADMIN_IDS = ADMIN_ID if isinstance(ADMIN_ID, list) else [ADMIN_ID]

def admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="📦 Заказы", callback_data="admin_orders")],
        [InlineKeyboardButton(text="💎 Вывод рефералов", callback_data="admin_ref_withdrawals")],
        [InlineKeyboardButton(text="🎁 Верификация NFT", callback_data="admin_verify_nft")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")]
    ])

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

@router.message(Command("admin"))
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещен")
        return
    
    await message.answer(
        "🔐 Админ-панель Miller Stars",
        reply_markup=admin_keyboard()
    )

@router.callback_query(F.data == "admin_orders")
async def show_orders(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    db = get_db()
    async with db.get_session() as session:
        result = await session.execute(
            select(CryptoOrder).where(CryptoOrder.status == "pending")
        )
        orders = result.scalars().all()
        
        if not orders:
            await callback.message.edit_text("Нет активных заказов на выплату")
            await callback.answer()
            return
        
        for order in orders:
            text = (
                f"📦 Заказ #{order.id}\n"
                f"Тип: {order.type}\n"
                f"User ID: {order.user_id}\n"
                f"Stars: {order.amount_stars}\n"
                f"USDT: {order.crypto_amount}\n"
                f"Wallet: {order.wallet_address or 'Не указан'}"
            )
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Выплатил",
                        callback_data=f"admin_complete_{order.id}"
                    ),
                    InlineKeyboardButton(
                        text="❌ Отклонить",
                        callback_data=f"admin_cancel_{order.id}"
                    )
                ]
            ])
            
            await callback.message.answer(text, reply_markup=keyboard)
    
    await callback.answer()

@router.callback_query(F.data.startswith("admin_complete_"))
async def complete_order(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    order_id = int(callback.data.split("_")[-1])
    
    db = get_db()
    async with db.get_session() as session:
        order = await session.get(CryptoOrder, order_id)
        if order:
            order.status = "completed"
            
            try:
                await callback.bot.send_message(
                    order.user_id,
                    f"✅ Заказ #{order.id} выполнен!\n\n"
                    f"Средства в размере {order.crypto_amount} USDT отправлены на ваш кошелек."
                )
            except Exception:
                pass
            
            await callback.message.edit_text(
                f"✅ Заказ #{order.id} отмечен как выполненный"
            )
        else:
            await callback.answer("❌ Заказ не найден", show_alert=True)
    
    await callback.answer()

@router.callback_query(F.data.startswith("admin_cancel_"))
async def cancel_order(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    order_id = int(callback.data.split("_")[-1])
    
    db = get_db()
    async with db.get_session() as session:
        order = await session.get(CryptoOrder, order_id)
        if order:
            order.status = "cancelled"
            
            try:
                await callback.bot.send_message(
                    order.user_id,
                    f"❌ Заказ #{order.id} отклонен.\n"
                    f"Свяжитесь с поддержкой для выяснения причин."
                )
            except Exception:
                pass
            
            await callback.message.edit_text(
                f"❌ Заказ #{order.id} отклонен"
            )
        else:
            await callback.answer("❌ Заказ не найден", show_alert=True)
    
    await callback.answer()

@router.message(Command("broadcast"))
async def broadcast(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещен")
        return
    
    if not message.reply_to_message and len(message.text.split()) < 2:
        await message.answer("Использование: /broadcast текст_сообщения\nИли ответьте на сообщение командой /broadcast")
        return
    
    if message.reply_to_message:
        broadcast_text = message.reply_to_message.text or message.reply_to_message.caption
        if not broadcast_text:
            await message.answer("Нет текста в пересылаемом сообщении")
            return
    else:
        broadcast_text = message.text.split(maxsplit=1)[1]
    
    db = get_db()
    async with db.get_session() as session:
        result = await session.execute(select(User))
        users = result.scalars().all()
        
        success_count = 0
        for user in users:
            try:
                await message.bot.send_message(user.user_id, broadcast_text)
                success_count += 1
            except Exception:
                continue
        
        await message.answer(f"✅ Рассылка отправлена {success_count} пользователям")

@router.callback_query(F.data == "admin_verify_nft")
async def verify_nft_start(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    db = get_db()
    async with db.get_session() as session:
        result = await session.execute(
            select(NFTListing).where(
                NFTListing.is_verified == False,
                NFTListing.status == "active"
            )
        )
        listings = result.scalars().all()
        
        if not listings:
            await callback.message.edit_text("Нет NFT для верификации")
            await callback.answer()
            return
        
        for listing in listings:
            text = (
                f"🎁 NFT #{listing.id}\n"
                f"Продавец: {listing.seller_id}\n"
                f"Название: {listing.nft_name}\n"
                f"Ссылка: {listing.nft_link}\n"
                f"Цена Stars: {listing.price_stars}\n"
                f"Цена USDT: {listing.price_crypto}"
            )
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Подтвердить",
                        callback_data=f"verify_nft_{listing.id}"
                    ),
                    InlineKeyboardButton(
                        text="❌ Отклонить",
                        callback_data=f"reject_nft_{listing.id}"
                    )
                ]
            ])
            
            await callback.message.answer(text, reply_markup=keyboard)
    
    await callback.answer()

@router.callback_query(F.data.startswith("verify_nft_"))
async def approve_nft(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    nft_id = int(callback.data.split("_")[-1])
    
    db = get_db()
    async with db.get_session() as session:
        listing = await session.get(NFTListing, nft_id)
        if listing:
            listing.is_verified = True
            
            try:
                await callback.bot.send_message(
                    listing.seller_id,
                    f"✅ Ваш NFT \"{listing.nft_name}\" прошел верификацию и добавлен в маркет!"
                )
            except Exception:
                pass
            
            await callback.message.edit_text(
                f"✅ NFT #{nft_id} верифицирован"
            )
        else:
            await callback.answer("❌ NFT не найден", show_alert=True)
    
    await callback.answer()

@router.callback_query(F.data.startswith("reject_nft_"))
async def reject_nft(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    nft_id = int(callback.data.split("_")[-1])
    
    db = get_db()
    async with db.get_session() as session:
        listing = await session.get(NFTListing, nft_id)
        if listing:
            listing.status = "cancelled"
            
            try:
                await callback.bot.send_message(
                    listing.seller_id,
                    f"❌ Ваш NFT \"{listing.nft_name}\" отклонен."
                )
            except Exception:
                pass
            
            await callback.message.edit_text(
                f"❌ NFT #{nft_id} отклонен"
            )
        else:
            await callback.answer("❌ NFT не найден", show_alert=True)
    
    await callback.answer()

@router.callback_query(F.data == "admin_stats")
async def stats(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    db = get_db()
    async with db.get_session() as session:
        # ИСПРАВЛЕНО: User.id → User.user_id
        result = await session.execute(select(func.count(User.user_id)))
        total_users = result.scalar()
        
        result = await session.execute(select(func.count(CryptoOrder.id)))
        total_orders = result.scalar()
        
        result = await session.execute(
            select(func.count(NFTListing.id)).where(NFTListing.status == "active")
        )
        active_listings = result.scalar()
        
        stats_text = (
            f"📊 Статистика бота:\n\n"
            f"👥 Всего пользователей: {total_users}\n"
            f"📦 Всего заказов: {total_orders}\n"
            f"🎁 Активных лотов NFT: {active_listings}"
        )
        
        await callback.message.edit_text(stats_text)
    
    await callback.answer()

@router.callback_query(F.data == "admin_broadcast")
async def broadcast_start(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    await callback.message.edit_text(
        "📢 Отправьте сообщение для рассылки\n"
        "Или используйте команду /broadcast текст_сообщения"
    )
    await callback.answer()

@router.callback_query(F.data == "admin_ref_withdrawals")
async def show_ref_withdrawals(callback: CallbackQuery):
    """Показать заявки на вывод реферальных звезд"""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    db = get_db()
    async with db.get_session() as session:
        result = await session.execute(
            select(CryptoOrder).where(
                CryptoOrder.type == "withdraw_referral",
                CryptoOrder.status == "pending"
            )
        )
        orders = result.scalars().all()
        
        if not orders:
            await callback.message.edit_text(
                "📭 Нет активных заявок на вывод реферальных звезд",
                reply_markup=admin_keyboard()
            )
            await callback.answer()
            return
        
        for order in orders:
            text = (
                f"💎 <b>Заявка на вывод #{order.id}</b>\n\n"
                f"👤 User ID: {order.user_id}\n"
                f"📛 Username: @{order.recipient_username or 'Не указан'}\n"
                f"⭐ Сумма: {order.amount_stars} звезд\n"
                f"📅 Создана: {order.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
                f"<b>Отправьте пользователю {order.amount_stars} звезд</b>"
            )
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text=f"✅ Отправил {order.amount_stars} зв.",
                    callback_data=f"admin_sent_ref_{order.id}_{order.user_id}_{order.amount_stars}"
                )
            ], [
                InlineKeyboardButton(
                    text="❌ Отклонить",
                    callback_data=f"admin_reject_ref_{order.id}_{order.user_id}_{order.amount_stars}"
                )
            ]])
            
            await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    
    await callback.answer()