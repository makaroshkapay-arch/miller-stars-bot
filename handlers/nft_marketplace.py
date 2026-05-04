"""
Модуль NFT Маркетплейса и Обменника
Комиссия системы: 3% от суммы сделки
"""
from aiogram import Router, F, Bot
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, 
    InlineKeyboardButton, LabeledPrice, PreCheckoutQuery,
    ContentType, SuccessfulPayment
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select, and_, or_
from datetime import datetime
from typing import Optional
import logging

from config import ADMIN_IDS, CRYPTO_BOT_TOKEN
from database.models import User, CryptoOrder, NFTListing
from database.core import get_db
from payments.crypto_bot import CryptoBotAPI
from payments.stars import StarsPayment

logger = logging.getLogger(__name__)

router = Router()
crypto_bot = CryptoBotAPI(CRYPTO_BOT_TOKEN)

# Комиссия системы
COMMISSION_RATE = 0.03  # 3%

# ==================== FSM СОСТОЯНИЯ ====================

class SellNFTCreation(StatesGroup):
    """Состояния для создания листинга NFT"""
    waiting_username = State()
    waiting_nft_link = State()
    waiting_price_stars = State()
    waiting_price_crypto = State()

class ExchangeStates(StatesGroup):
    """Состояния для обменника"""
    waiting_asset_info = State()
    waiting_agreement = State()
    waiting_transfer = State()

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def calculate_commission(price: float) -> dict:
    """Расчет цены с комиссией"""
    price_with_commission = price * (1 + COMMISSION_RATE)
    commission_amount = price * COMMISSION_RATE
    return {
        "original_price": price,
        "price_with_commission": round(price_with_commission, 2),
        "commission": round(commission_amount, 2)
    }

def get_nft_sell_menu_keyboard():
    """Клавиатура меню продажи NFT"""
    buttons = [
        [InlineKeyboardButton(text="📦 Мои NFT (выставленные)", callback_data="my_nft_listings")],
        [InlineKeyboardButton(text="📤 Выставить на продажу", callback_data="create_nft_listing")],
        [InlineKeyboardButton(text="🔙 Назад в главное меню", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_marketplace_keyboard():
    """Клавиатура маркета"""
    buttons = [
        [InlineKeyboardButton(text="🛍 Купить за Stars", callback_data="buy_nft_stars")],
        [InlineKeyboardButton(text="💎 Купить за Crypto", callback_data="buy_nft_crypto")],
        [InlineKeyboardButton(text="🔙 Назад в главное меню", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_exchange_keyboard():
    """Клавиатура обменника"""
    buttons = [
        [InlineKeyboardButton(text="💰 Продать актив боту", callback_data="start_exchange")],
        [InlineKeyboardButton(text="📋 Мои заявки на обмен", callback_data="my_exchange_requests")],
        [InlineKeyboardButton(text="🔙 Назад в главное меню", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

async def send_nft_to_user(bot: Bot, chat_id: int, nft_link: str, listing_id: int):
    """Отправка NFT пользователю после покупки"""
    try:
        await bot.send_message(
            chat_id,
            f"🎁 <b>Поздравляем с покупкой!</b>\n\n"
            f"🔹 NFT лот #{listing_id}\n"
            f"🔗 Ссылка на подарок: {nft_link}\n\n"
            f"<i>Нажмите на ссылку, чтобы получить ваш NFT-подарок</i>",
            parse_mode="HTML",
            disable_web_page_preview=False
        )
    except Exception as e:
        logger.error(f"Error sending NFT to user: {e}")

async def notify_admins(bot: Bot, text: str, keyboard=None):
    """Уведомление всех администраторов"""
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id}: {e}")

# ==================== ОСНОВНЫЕ МЕНЮ ====================

@router.callback_query(F.data == "nft_market")
async def show_marketplace_menu(callback: CallbackQuery):
    """Показать меню маркета NFT"""
    try:
        await callback.message.edit_text(
            "🛒 <b>Маркет NFT-подарков</b>\n\n"
            "Здесь вы можете купить коллекционные подарки Telegram.\n"
            "Выберите способ оплаты:",
            reply_markup=get_marketplace_keyboard(),
            parse_mode="HTML"
        )
    except TelegramBadRequest:
        pass
    await callback.answer()

@router.callback_query(F.data == "sell_nft_menu")
async def show_sell_nft_menu(callback: CallbackQuery):
    """Показать меню продажи NFT"""
    try:
        await callback.message.edit_text(
            "💎 <b>Продажа NFT-подарков</b>\n\n"
            "• Просмотрите ваши выставленные лоты\n"
            "• Выставите новый подарок на продажу\n"
            "• Удалите ненужные лоты\n\n"
            f"<i>Комиссия системы: {COMMISSION_RATE*100}% от цены покупателя</i>",
            reply_markup=get_nft_sell_menu_keyboard(),
            parse_mode="HTML"
        )
    except TelegramBadRequest:
        pass
    await callback.answer()

# ==================== ПОКУПКА NFT (МАРКЕТ) ====================

@router.callback_query(F.data.in_(["buy_nft_stars", "buy_nft_crypto"]))
async def show_available_listings(callback: CallbackQuery):
    """Показать доступные NFT для покупки"""
    payment_type = "stars" if callback.data == "buy_nft_stars" else "crypto"
    
    db = get_db()
    async with db.get_session() as session:
        result = await session.execute(
            select(NFTListing).where(
                and_(
                    NFTListing.status == "active",
                    NFTListing.is_verified == True
                )
            )
        )
        listings = result.scalars().all()
        
        if not listings:
            try:
                await callback.message.edit_text(
                    "📭 <b>Нет доступных лотов</b>\n\n"
                    "На данный момент нет верифицированных NFT для продажи.\n"
                    "Попробуйте позже или станьте первым продавцом!",
                    reply_markup=get_marketplace_keyboard(),
                    parse_mode="HTML"
                )
            except TelegramBadRequest:
                pass
            await callback.answer()
            return
        
        # Показываем первые 5 лотов
        for listing in listings[:10]:
            stars_calc = calculate_commission(listing.price_stars) if listing.price_stars else None
            crypto_calc = calculate_commission(listing.price_crypto) if listing.price_crypto else None
            
            text = (
                f"🎁 <b>NFT Лот #{listing.id}</b>\n\n"
                f"📛 Название: {listing.nft_name or 'Не указано'}\n"
            )
            
            if listing.price_stars and stars_calc:
                text += (
                    f"⭐ Цена Stars: {stars_calc['price_with_commission']} (включая комиссию 3%)\n"
                )
            if listing.price_crypto and crypto_calc:
                text += (
                    f"💎 Цена USDT: ${crypto_calc['price_with_commission']} (включая комиссию 3%)\n"
                )
            
            text += (
                f"📅 Создан: {listing.created_at.strftime('%d.%m.%Y')}\n"
                f"🔗 Ссылка: {listing.nft_link[:50]}..."
            )
            
            # Кнопки покупки
            buttons = []
            if payment_type == "stars" and listing.price_stars:
                buttons.append([
                    InlineKeyboardButton(
                        text=f"⭐ Купить за {stars_calc['price_with_commission']} Stars",
                        callback_data=f"purchase_nft_{listing.id}_stars"
                    )
                ])
            elif payment_type == "crypto" and listing.price_crypto:
                buttons.append([
                    InlineKeyboardButton(
                        text=f"💎 Купить за ${crypto_calc['price_with_commission']} USDT",
                        callback_data=f"purchase_nft_{listing.id}_crypto"
                    )
                ])
            
            buttons.append([
                InlineKeyboardButton(text="🔙 К выбору оплаты", callback_data="nft_market")
            ])
            
            try:
                await callback.message.answer(
                    text,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
            except TelegramBadRequest:
                pass
        
        await callback.answer()

@router.callback_query(F.data.startswith("purchase_nft_"))
async def process_nft_purchase(callback: CallbackQuery):
    """Обработка покупки NFT"""
    parts = callback.data.split("_")
    listing_id = int(parts[2])
    payment_type = parts[3]  # stars или crypto
    
    db = get_db()
    async with db.get_session() as session:
        listing = await session.get(NFTListing, listing_id)
        
        if not listing or listing.status != "active":
            await callback.answer("❌ Этот лот уже продан или снят с продажи", show_alert=True)
            return
        
        if payment_type == "stars":
            # Покупка за Stars
            stars_calc = calculate_commission(listing.price_stars)
            
            await callback.message.answer(
                f"🛍 <b>Покупка NFT за Stars</b>\n\n"
                f"Лот #{listing.id}\n"
                f"Цена: {stars_calc['price_with_commission']} Stars\n"
                f"Включая комиссию: {stars_calc['commission']} Stars\n\n"
                f"Создаю счет для оплаты...",
                parse_mode="HTML"
            )
            
            # Создаем инвойс в звездах
            payload = f"nft_purchase_{callback.from_user.id}_{listing_id}"
            await StarsPayment.create_stars_invoice(
                callback.bot,
                callback.message.chat.id,
                int(stars_calc['price_with_commission']),
                f"Покупка NFT лота #{listing_id}",
                payload
            )
            
        elif payment_type == "crypto":
            # Покупка за Crypto
            crypto_calc = calculate_commission(listing.price_crypto)
            
            invoice = await crypto_bot.create_invoice(
                asset="USDT",
                amount=crypto_calc['price_with_commission'],
                description=f"Покупка NFT лота #{listing_id}",
                payload=f"nft_{listing_id}_{callback.from_user.id}",
                paid_btn_name="openBot",
                paid_btn_url="https://t.me/miller_starsbot"
            )
            
            if invoice:
                await callback.message.answer(
                    f"💎 <b>Счет на оплату NFT создан</b>\n\n"
                    f"Лот #{listing_id}\n"
                    f"Сумма: ${crypto_calc['price_with_commission']} USDT\n"
                    f"Комиссия: ${crypto_calc['commission']} USDT\n\n"
                    f"Для оплаты нажмите кнопку ниже:",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="💳 Оплатить", url=invoice["pay_url"])],
                        [InlineKeyboardButton(
                            text="✅ Я оплатил", 
                            callback_data=f"check_nft_payment_{invoice['invoice_id']}_{listing_id}"
                        )]
                    ]),
                    parse_mode="HTML"
                )
                
                # Сохраняем заказ
                order = CryptoOrder(
                    user_id=callback.from_user.id,
                    type="buy_nft",
                    amount_stars=listing.price_stars or 0,
                    crypto_amount=crypto_calc['price_with_commission'],
                    crypto_invoice_id=str(invoice["invoice_id"]),
                    status="pending"
                )
                session.add(order)
                await session.commit()
            else:
                await callback.message.answer("❌ Ошибка при создании счета")
    
    await callback.answer()

@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    """Обработка pre-checkout для NFT"""
    await StarsPayment.accept_pre_checkout(pre_checkout_query)

@router.message(F.content_type == ContentType.SUCCESSFUL_PAYMENT)
async def process_nft_stars_payment(message: Message):
    """Обработка успешной оплаты NFT через Stars"""
    if not message.successful_payment:
        return
    
    payload = message.successful_payment.invoice_payload
    
    if payload.startswith("nft_purchase_"):
        parts = payload.split("_")
        buyer_id = int(parts[2])
        listing_id = int(parts[3])
        
        db = get_db()
        async with db.get_session() as session:
            listing = await session.get(NFTListing, listing_id)
            
            if listing and listing.status == "active":
                # Отмечаем как проданное
                listing.status = "sold"
                listing.buyer_id = buyer_id
                
                # Обновляем счетчик сделок продавца
                seller = await session.get(User, listing.seller_id)
                if seller:
                    seller.deals_count += 1
                
                await session.commit()
                
                # Отправляем NFT покупателю
                await send_nft_to_user(message.bot, buyer_id, listing.nft_link, listing_id)
                
                # Уведомляем продавца
                try:
                    await message.bot.send_message(
                        listing.seller_id,
                        f"🎉 <b>Ваш NFT продан!</b>\n\n"
                        f"Лот #{listing.id}\n"
                        f"Покупатель: {buyer_id}\n"
                        f"Сумма: {listing.price_stars} Stars\n"
                        f"Комиссия системы: {calculate_commission(listing.price_stars)['commission']} Stars\n"
                        f"Вы получите: {listing.price_stars} Stars",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Failed to notify seller {listing.seller_id}: {e}")
                
                # Уведомляем админов
                await notify_admins(
                    message.bot,
                    f"✅ NFT #{listing_id} продан через Stars\n"
                    f"Продавец: {listing.seller_id}\n"
                    f"Покупатель: {buyer_id}\n"
                    f"Сумма: {listing.price_stars} Stars"
                )
            else:
                await message.answer("❌ Ошибка: лот уже неактивен")

@router.callback_query(F.data.startswith("check_nft_payment_"))
async def check_nft_crypto_payment(callback: CallbackQuery):
    """Проверка оплаты NFT через Crypto"""
    parts = callback.data.split("_")
    invoice_id = int(parts[3])
    listing_id = int(parts[4])
    
    invoice_status = await crypto_bot.get_invoice(invoice_id)
    
    if invoice_status and invoice_status.get("status") == "paid":
        db = get_db()
        async with db.get_session() as session:
            listing = await session.get(NFTListing, listing_id)
            
            if listing and listing.status == "active":
                listing.status = "sold"
                listing.buyer_id = callback.from_user.id
                
                seller = await session.get(User, listing.seller_id)
                if seller:
                    seller.deals_count += 1
                
                # Обновляем статус заказа
                result = await session.execute(
                    select(CryptoOrder).where(
                        CryptoOrder.crypto_invoice_id == str(invoice_id)
                    )
                )
                order = result.scalar_one_or_none()
                if order:
                    order.status = "paid"
                
                await session.commit()
                
                # Отправляем NFT
                await send_nft_to_user(
                    callback.bot, 
                    callback.from_user.id, 
                    listing.nft_link, 
                    listing_id
                )
                
                # Уведомляем продавца
                try:
                    await callback.bot.send_message(
                        listing.seller_id,
                        f"🎉 <b>Ваш NFT продан за Crypto!</b>\n\n"
                        f"Лот #{listing.id}\n"
                        f"Сумма: ${listing.price_crypto} USDT\n"
                        f"Ожидайте перевода от администратора",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass
                
                # Уведомляем админов о необходимости перевода средств
                await notify_admins(
                    callback.bot,
                    f"🔔 <b>NFT #{listing_id} продан за Crypto!</b>\n\n"
                    f"Продавец: {listing.seller_id}\n"
                    f"Покупатель: {callback.from_user.id}\n"
                    f"Сумма к переводу продавцу: ${listing.price_crypto} USDT\n"
                    f"Комиссия системы: ${calculate_commission(listing.price_crypto)['commission']} USDT\n\n"
                    f"⚠️ Необходимо перевести средства продавцу вручную!",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(
                            text=f"✅ Перевел продавцу #{listing.seller_id}",
                            callback_data=f"admin_transferred_{listing_id}_{listing.seller_id}"
                        )]
                    ])
                )
                
                try:
                    await callback.message.edit_text(
                        "✅ <b>Оплата подтверждена!</b>\n\n"
                        "NFT отправлен вам в чат.\n"
                        "Проверьте сообщение выше 👆",
                        parse_mode="HTML"
                    )
                except TelegramBadRequest:
                    pass
            else:
                await callback.answer("❌ Лот уже неактивен", show_alert=True)
    else:
        await callback.answer("❌ Оплата еще не получена. Попробуйте позже", show_alert=True)
    
    await callback.answer()

@router.callback_query(F.data.startswith("admin_transferred_"))
async def admin_confirm_transfer(callback: CallbackQuery):
    """Подтверждение перевода средств продавцу админом"""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    parts = callback.data.split("_")
    listing_id = int(parts[2])
    seller_id = int(parts[3])
    
    try:
        await callback.bot.send_message(
            seller_id,
            f"💰 <b>Средства переведены!</b>\n\n"
            f"Перевод за NFT лот #{listing_id} выполнен.\n"
            f"Проверьте ваш кошелек.",
            parse_mode="HTML"
        )
        await callback.message.edit_text(
            f"✅ Перевод продавцу #{seller_id} подтвержден и отправлен",
            reply_markup=None
        )
    except Exception as e:
        await callback.answer(f"Ошибка: {e}", show_alert=True)
    
    await callback.answer()

# ==================== ПРОДАЖА NFT ====================

@router.callback_query(F.data == "create_nft_listing")
async def start_nft_creation(callback: CallbackQuery, state: FSMContext):
    """Начало создания листинга NFT"""
    await callback.message.answer(
        "📝 <b>Создание листинга NFT</b>\n\n"
        "Шаг 1/4: Введите ваш username (без @):",
        parse_mode="HTML"
    )
    await state.set_state(SellNFTCreation.waiting_username)
    await callback.answer()

@router.message(SellNFTCreation.waiting_username)
async def process_nft_username(message: Message, state: FSMContext):
    """Обработка username"""
    username = message.text.strip().replace('@', '')
    await state.update_data(username=username)
    
    await message.answer(
        "Шаг 2/4: Отправьте ссылку на NFT подарок или ID подарка:"
    )
    await state.set_state(SellNFTCreation.waiting_nft_link)

@router.message(SellNFTCreation.waiting_nft_link)
async def process_nft_link(message: Message, state: FSMContext):
    """Обработка ссылки на NFT"""
    nft_input = message.text.strip()
    await state.update_data(nft_link=nft_input)
    
    await message.answer(
        "Шаг 3/4: Введите цену в Telegram Stars (целое число):\n"
        f"<i>Комиссия {COMMISSION_RATE*100}% будет добавлена к цене для покупателя</i>",
        parse_mode="HTML"
    )
    await state.set_state(SellNFTCreation.waiting_price_stars)

@router.message(SellNFTCreation.waiting_price_stars)
async def process_nft_stars_price(message: Message, state: FSMContext):
    """Обработка цены в звездах"""
    try:
        price_stars = int(message.text)
        if price_stars <= 0:
            raise ValueError
        
        await state.update_data(price_stars=price_stars)
        
        await message.answer(
            "Шаг 4/4: Введите эквивалент в USD (например: 5.99):\n"
            f"<i>Комиссия {COMMISSION_RATE*100}% будет добавлена к цене для покупателя</i>",
            parse_mode="HTML"
        )
        await state.set_state(SellNFTCreation.waiting_price_crypto)
    except ValueError:
        await message.answer("❌ Введите целое положительное число звезд")

@router.message(SellNFTCreation.waiting_price_crypto)
async def finalize_nft_creation(message: Message, state: FSMContext):
    """Завершение создания NFT листинга"""
    try:
        if message.text and message.text.startswith('/'):
            await state.clear()
            return
        
        price_crypto = float(message.text.replace(',', '.'))
        if price_crypto <= 0:
            raise ValueError
        
        data = await state.get_data()

        if not all(key in data for key in ['username', 'nft_link', 'price_stars']):
            await message.answer("❌ Ошибка данных. Начните заново с /start")
            await state.clear()
            return
        
        stars_calc = calculate_commission(data['price_stars'])
        crypto_calc = calculate_commission(price_crypto)
        
        db = get_db()
        async with db.get_session() as session:
            # Создаем листинг
            listing = NFTListing(
                seller_id=message.from_user.id,
                nft_link=data['nft_link'],
                price_stars=data['price_stars'],
                price_crypto=price_crypto,
                status="active",
                is_verified=False  # Требует верификации админом
            )
            session.add(listing)
            await session.commit()
            await session.refresh(listing)

            await state.clear()
            
            await message.answer(
                f"✅ <b>Листинг создан!</b>\n\n"
                f"🔹 Лот #{listing.id}\n"
                f"🔗 NFT: {data['nft_link'][:50]}...\n\n"
                f"<b>Ваша выручка:</b>\n"
                f"⭐ {data['price_stars']} Stars\n"
                f"💎 ${price_crypto} USDT\n\n"
                f"<b>Цена для покупателя (с комиссией {COMMISSION_RATE*100}%):</b>\n"
                f"⭐ {stars_calc['price_with_commission']} Stars\n"
                f"💎 ${crypto_calc['price_with_commission']} USDT\n\n"
                f"<i>Лот отправлен на верификацию администратору</i>",
                parse_mode="HTML",
                disable_web_page_preview=True
            )
            
            # Уведомляем админов о новом листинге
            await notify_admins(
                message.bot,
                f"📢 <b>Новый NFT листинг на верификацию</b>\n\n"
                f"ID: {listing.id}\n"
                f"Продавец: @{data['username']} (ID: {message.from_user.id})\n"
                f"Ссылка: {data['nft_link']}\n"
                f"Цена Stars: {data['price_stars']}\n"
                f"Цена USDT: ${price_crypto}\n"
                f"Комиссия: {stars_calc['commission']} Stars / ${crypto_calc['commission']} USDT",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="✅ Верифицировать",
                            callback_data=f"verify_nft_{listing.id}"
                        ),
                        InlineKeyboardButton(
                            text="❌ Отклонить",
                            callback_data=f"reject_nft_{listing.id}"
                        )
                    ]
                ])
            )
            # Отправляем главное меню
            from keyboards.inline import main_menu_keyboard
            await message.answer(
                "Что делаем дальше?",
                reply_markup=main_menu_keyboard()
            )
    
    except (ValueError, TypeError):
        await message.answer(
            "❌ Введите корректную цену в USD (например: 5.99)\n"
            "Или отправьте /start для выхода"
        )
        # Не очищаем состояние, чтобы пользователь мог повторить ввод
        return
    except Exception as e:
        logger.error(f"Error creating NFT listing: {e}")
        await message.answer(
            "❌ Произошла ошибка при создании листинга. Попробуйте позже."
        )
        await state.clear()
        
@router.callback_query(F.data == "my_nft_listings")
async def show_my_listings(callback: CallbackQuery):
    """Показать мои NFT листинги"""
    db = get_db()
    async with db.get_session() as session:
        result = await session.execute(
            select(NFTListing).where(
                and_(
                    NFTListing.seller_id == callback.from_user.id,
                    NFTListing.status == "active"
                )
            )
        )
        listings = result.scalars().all()
        
        if not listings:
            try:
                await callback.message.edit_text(
                    "📦 <b>Ваши NFT листинги</b>\n\n"
                    "У вас нет активных листингов.\n"
                    "Создайте новый, нажав «Выставить на продажу»",
                    reply_markup=get_nft_sell_menu_keyboard(),
                    parse_mode="HTML"
                )
            except TelegramBadRequest:
                pass
            await callback.answer()
            return
        
        for listing in listings[:5]:
            stars_calc = calculate_commission(listing.price_stars) if listing.price_stars else None
            crypto_calc = calculate_commission(listing.price_crypto) if listing.price_crypto else None
            
            text = (
                f"📦 <b>Лот #{listing.id}</b>\n\n"
                f"Статус: {'✅ Верифицирован' if listing.is_verified else '⏳ На проверке'}\n"
                f"Ваша цена: {listing.price_stars} Stars / ${listing.price_crypto} USDT\n"
            )
            
            if stars_calc and crypto_calc:
                text += (
                    f"Цена для покупателя: {stars_calc['price_with_commission']} Stars "
                    f"/ ${crypto_calc['price_with_commission']} USDT\n"
                )
            
            buttons = [[
                InlineKeyboardButton(
                    text="🗑 Удалить листинг",
                    callback_data=f"delete_listing_{listing.id}"
                )
            ]]
            
            await callback.message.answer(
                text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
                parse_mode="HTML"
            )
        
        await callback.answer()

@router.callback_query(F.data.startswith("delete_listing_"))
async def delete_nft_listing(callback: CallbackQuery):
    """Удаление NFT листинга"""
    listing_id = int(callback.data.split("_")[-1])
    
    db = get_db()
    async with db.get_session() as session:
        listing = await session.get(NFTListing, listing_id)
        
        if listing and listing.seller_id == callback.from_user.id:
            listing.status = "cancelled"
            await session.commit()
            await callback.answer("✅ Листинг удален", show_alert=True)
            await show_my_listings(callback)
        else:
            await callback.answer("❌ Ошибка доступа", show_alert=True)

# ==================== ОБМЕННИК ====================

@router.callback_query(F.data == "exchange_menu")
async def exchange_menu(callback: CallbackQuery):
    """Меню обменника"""
    # Добавьте эту кнопку в главное меню в inline.py
    try:
        await callback.message.edit_text(
            "💰 <b>Обменник активов</b>\n\n"
            "Здесь вы можете продать боту:\n"
            "• Анонимные NFT-подарки\n"
            "• Редкие подарки\n"
            "• Telegram Stars\n\n"
            "<i>Администратор оценит ваш актив и предложит цену</i>",
            reply_markup=get_exchange_keyboard(),
            parse_mode="HTML"
        )
    except TelegramBadRequest:
        pass
    await callback.answer()

@router.callback_query(F.data == "start_exchange")
async def start_exchange_process(callback: CallbackQuery, state: FSMContext):
    """Начало процесса обмена"""
    await callback.message.answer(
        "📤 <b>Продажа актива боту</b>\n\n"
        "Отправьте мне подарок (Gift) или скриншот того, что хотите продать.\n"
        "Также опишите актив в сообщении.",
        parse_mode="HTML"
    )
    await state.set_state(ExchangeStates.waiting_asset_info)
    await callback.answer()

@router.message(ExchangeStates.waiting_asset_info)
async def process_asset_info(message: Message, state: FSMContext):
    """Обработка информации об активе"""
    asset_info = {
        "user_id": message.from_user.id,
        "username": message.from_user.username,
        "text": message.text or message.caption or "",
        "has_photo": bool(message.photo),
        "has_document": bool(message.document),
        "message_id": message.message_id
    }
    
    await state.update_data(asset_info=asset_info)
    
    # Пересылаем админам
    await notify_admins(
        message.bot,
        f"📢 <b>Новая заявка на обмен!</b>\n\n"
        f"От: @{message.from_user.username} (ID: {message.from_user.id})\n"
        f"Описание: {asset_info['text']}\n\n"
        f"<i>Оцените актив и предложите цену</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💰 Предложить цену",
                    callback_data=f"offer_price_{message.from_user.id}"
                )
            ]
        ])
    )
    
    await message.answer(
        "✅ <b>Заявка отправлена!</b>\n\n"
        "Администратор рассмотрит ваш актив и предложит цену.\n"
        "Ожидайте уведомления.",
        parse_mode="HTML"
    )
    await state.clear()

@router.callback_query(F.data.startswith("offer_price_"))
async def admin_offer_price(callback: CallbackQuery, state: FSMContext):
    """Админ предлагает цену (заглушка - админ должен ответить вручную)"""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    user_id = int(callback.data.split("_")[-1])
    
    await callback.message.answer(
        f"Для предложения цены пользователю {user_id}, отправьте сообщение в формате:\n"
        f"<code>/offer {user_id} сумма_USDT способ_оплаты</code>\n\n"
        f"Пример: /offer {user_id} 10.5 USDT",
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(Command("offer"))
async def process_admin_offer(message: Message):
    """Обработка предложения цены админом"""
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Доступ запрещен")
        return
    
    try:
        parts = message.text.split()
        user_id = int(parts[1])
        amount = float(parts[2])
        currency = parts[3] if len(parts) > 3 else "USDT"
        
        # Отправляем предложение пользователю
        await message.bot.send_message(
            user_id,
            f"💰 <b>Предложение от администратора</b>\n\n"
            f"За ваш актив предлагаем: <b>{amount} {currency}</b>\n\n"
            f"Если согласны, нажмите кнопку ниже:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="✅ Согласен, отправить боту",
                    callback_data=f"agree_exchange_{amount}_{currency}"
                )],
                [InlineKeyboardButton(
                    text="❌ Отказаться",
                    callback_data="decline_exchange"
                )]
            ]),
            parse_mode="HTML"
        )
        
        await message.answer(f"✅ Предложение отправлено пользователю {user_id}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}\nИспользуйте формат: /offer user_id сумма валюта")

@router.callback_query(F.data.startswith("agree_exchange_"))
async def user_agree_exchange(callback: CallbackQuery, state: FSMContext):
    """Пользователь согласен на обмен"""
    parts = callback.data.split("_")
    amount = float(parts[2])
    currency = parts[3]
    
    await state.update_data(exchange_amount=amount, exchange_currency=currency)
    
    await callback.message.answer(
        "📤 <b>Отправьте подарок боту</b>\n\n"
        "Перешлите сообщение с подарком (Gift) в этот чат.\n"
        "После получения администратор переведет вам средства.",
        parse_mode="HTML"
    )
    await state.set_state(ExchangeStates.waiting_transfer)
    await callback.answer()

@router.message(ExchangeStates.waiting_transfer)
async def process_gift_transfer(message: Message, state: FSMContext):
    """Обработка получения подарка"""
    data = await state.get_data()
    
    # Пересылаем подарок админам
    await notify_admins(
        message.bot,
        f"🎁 <b>Пользователь отправил подарок!</b>\n\n"
        f"От: @{message.from_user.username} (ID: {message.from_user.id})\n"
        f"Сумма к выплате: {data['exchange_amount']} {data['exchange_currency']}\n\n"
        f"Подарок переслан ниже. Подтвердите получение и выполните перевод:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=f"💰 Выплатить {data['exchange_amount']} {data['exchange_currency']}",
                callback_data=f"pay_exchange_{message.from_user.id}_{data['exchange_amount']}_{data['exchange_currency']}"
            )]
        ])
    )
    
    # Пересылаем сообщение с подарком админам
    for admin_id in ADMIN_IDS:
        try:
            await message.forward(admin_id)
        except Exception:
            pass
    
    await message.answer(
        "✅ <b>Подарок отправлен!</b>\n\n"
        "Администратор проверит получение и переведет вам средства.",
        parse_mode="HTML"
    )
    await state.clear()

@router.callback_query(F.data.startswith("pay_exchange_"))
async def admin_pay_exchange(callback: CallbackQuery):
    """Админ подтверждает выплату"""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    parts = callback.data.split("_")
    user_id = int(parts[2])
    amount = float(parts[3])
    currency = parts[4]
    
    # Уведомляем пользователя о выплате
    try:
        await callback.bot.send_message(
            user_id,
            f"💰 <b>Средства переведены!</b>\n\n"
            f"Сумма: {amount} {currency}\n"
            f"Проверьте ваш кошелек или баланс.",
            parse_mode="HTML"
        )
    except Exception:
        pass
    
    await callback.message.edit_text(
        f"✅ Выплата пользователю {user_id} подтверждена:\n"
        f"{amount} {currency}",
        reply_markup=None
    )
    await callback.answer("✅ Выплата подтверждена", show_alert=True)

@router.callback_query(F.data == "decline_exchange")
async def decline_exchange(callback: CallbackQuery):
    """Отказ от обмена"""
    await callback.message.edit_text(
        "❌ Вы отказались от предложения.",
        reply_markup=None
    )
    await callback.answer()

# ==================== ДОПОЛНИТЕЛЬНО: ОТОБРАЖЕНИЕ ЗАЯВОК ====================

@router.callback_query(F.data == "my_exchange_requests")
async def show_my_exchange_requests(callback: CallbackQuery):
    """Показать мои заявки на обмен"""
    await callback.message.edit_text(
        "📋 <b>Ваши заявки на обмен</b>\n\n"
        "Здесь будут отображаться ваши активные заявки.\n"
        "Функция в разработке.",
        reply_markup=get_exchange_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()
    