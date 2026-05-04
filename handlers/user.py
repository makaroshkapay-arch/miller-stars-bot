from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, PreCheckoutQuery, ContentType, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select
from config import ADMIN_ID, ADMIN_IDS, CRYPTO_BOT_TOKEN, BOT_TOKEN
from keyboards.inline import main_menu_keyboard, buy_stars_packs_keyboard, payment_keyboard, referral_keyboard
from payments.crypto_bot import CryptoBotAPI
from payments.stars import StarsPayment
from database.models import User, CryptoOrder
from aiogram.exceptions import TelegramBadRequest
from database.core import get_db
from utils.referral import ReferralSystem
import logging

logger = logging.getLogger(__name__)


router = Router()
crypto_bot = CryptoBotAPI(CRYPTO_BOT_TOKEN)

# ID канала для проверки подписки
CHANNEL_ID = "@miller_news"
CHANNEL_URL = "https://t.me/miller_news"

# Фото для главного меню
MAIN_MENU_PHOTO = "AgACAgIAAxkBAAIDJGn3sl4hz9OO_jl39JP3BWUKKDkNAAJtFWsbuDPBS8tUjEzNfwAB1wEAAwIAA3kAAzsE"

class BuyStarsStates(StatesGroup):
    waiting_recipient = State()
    waiting_custom_amount = State()

class SellStarsStates(StatesGroup):
    waiting_amount = State()
    waiting_wallet = State()

class WithdrawReferralStates(StatesGroup):
    waiting_amount = State()


def get_referral_link(bot_username: str, referral_code: str) -> str:
    """Создает реферальную ссылку"""
    return f"https://t.me/{bot_username}?start={referral_code}"


async def check_subscription(bot: Bot, user_id: int) -> bool:
    """Проверяет подписку пользователя на канал"""
    try:
        chat_member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return chat_member.status in ["member", "administrator", "creator"]
    except TelegramBadRequest:
        return False
    except Exception as e:
        logger.error(f"Error checking subscription: {e}")
        return False


async def send_message_safe(callback: CallbackQuery, text: str, keyboard=None, parse_mode="HTML"):
    """Безопасная отправка сообщения с удалением фото"""
    try:
        await callback.message.delete()
    except:
        pass
    return await callback.message.answer(text, reply_markup=keyboard, parse_mode=parse_mode)


@router.callback_query(F.data == "check_sub")
async def check_sub_handler(callback: CallbackQuery):
    """Обработчик кнопки проверки подписки"""
    if await check_subscription(callback.bot, callback.from_user.id):
        await callback.answer("✅ Подписка подтверждена! Добро пожаловать!", show_alert=True)
        
        await callback.message.answer_photo(
            photo=MAIN_MENU_PHOTO,
            caption="🌟 <b>Miller Stars - Маркетплейс Telegram Stars и NFT!</b>\n\nВыберите действие:",
            reply_markup=main_menu_keyboard(),
            parse_mode="HTML"
        )
    else:
        await callback.answer("❌ Вы еще не подписались на канал!", show_alert=True)


@router.message(Command("start"))
async def cmd_start(message: Message, command: CommandObject):
    db = get_db()
    async with db.get_session() as session:
        result = await session.execute(
            select(User).where(User.user_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            referral_code = ReferralSystem.generate_referral_code(message.from_user.id)
            user = User(
                user_id=message.from_user.id,
                username=message.from_user.username,
                deals_count=0,
                referral_balance=0.0,
                referral_code=referral_code,
                referrals_count=0
            )
            session.add(user)
            await session.commit()
            
            if command.args:
                referrer_code = command.args.strip()
                await ReferralSystem.process_referral(user, referrer_code)
                
                try:
                    referrer = await ReferralSystem.get_user_by_code(referrer_code)
                    if referrer:
                        await message.bot.send_message(
                            referrer.user_id,
                            f"🎉 По вашей реферальной ссылке зарегистрировался новый пользователь!\n"
                            f"Вы получили +{ReferralSystem.REFERRAL_REWARD} звезд на баланс."
                        )
                except Exception:
                    pass
        
        bot_info = await message.bot.get_me()
        ref_link = get_referral_link(bot_info.username, user.referral_code)
        
        welcome_text = (
            "🌟 <b>Miller Stars - Маркетплейс Telegram Stars и NFT!</b>\n\n"
            "Здесь вы можете купить, продать звезды и обмениваться коллекционными подарками.\n\n"
            f"🔗 Ваша реферальная ссылка:\n<code>{ref_link}</code>\n\n"
            f"Приглашайте друзей и получайте +{ReferralSystem.REFERRAL_REWARD} звезд за каждого!\n\n"
            "Выберите действие:"
        )
        
        await message.answer_photo(
            photo=MAIN_MENU_PHOTO,
            caption=welcome_text,
            reply_markup=main_menu_keyboard(),
            parse_mode="HTML"
        )


@router.callback_query(F.data == "main_menu")
async def back_to_main_menu(callback: CallbackQuery):
    """Возврат в главное меню"""
    await send_message_safe(
        callback,
        "🌟 <b>Miller Stars - Маркетплейс Telegram Stars и NFT!</b>\n\nВыберите действие:",
        main_menu_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "sell_stars_menu")
async def sell_stars_menu(callback: CallbackQuery, state: FSMContext):
    """Меню продажи звезд"""
    if not await check_subscription(callback.bot, callback.from_user.id):
        await send_message_safe(
            callback,
            "🔒 <b>Требуется подписка</b>\n\nПодпишитесь на канал @miller_news",
            InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📢 Подписаться", url=CHANNEL_URL)],
                [InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub")]
            ])
        )
        return
    
    await send_message_safe(
        callback,
        "⭐ <b>Продажа Telegram Stars</b>\n\n"
        "📝 <b>Инструкция:</b>\n"
        "1. Отправьте количество звезд\n"
        "2. Укажите адрес кошелька USDT (TON)\n"
        "3. Получите USDT на ваш кошелек\n\n"
        "💰 <b>Курс:</b> 1 звезда = 0.012 USDT\n"
        "📊 <b>Минимальная сумма:</b> 50 звезд\n\n"
        "Введите количество звезд для продажи:",
        InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")]
        ])
    )
    await state.set_state(SellStarsStates.waiting_amount)
    await callback.answer()


@router.message(SellStarsStates.waiting_amount)
async def process_sell_amount(message: Message, state: FSMContext):
    """Обработка количества звезд для продажи"""
    if not await check_subscription(message.bot, message.from_user.id):
        await message.answer(
            f"🔒 Для использования бота подпишитесь на канал {CHANNEL_ID}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📢 Подписаться", url=CHANNEL_URL)]
            ])
        )
        await state.clear()
        return
    
    try:
        amount = int(message.text)
        if amount < 50:
            await message.answer("❌ Минимальное количество: 50 звезд")
            return
        
        usdt_amount = round(amount * 0.012, 2)
        await state.update_data(sell_amount=amount, usdt_amount=usdt_amount)
        
        await message.answer(
            f"📊 <b>Продажа {amount} звезд</b>\n\n"
            f"💰 Вы получите: <b>{usdt_amount} USDT</b>\n"
            f"📋 Курс: 1 ⭐ = 0.012 USDT\n\n"
            f"📝 <b>Введите адрес вашего кошелька USDT (TON):</b>\n\n"
            f"<i>Пример: UQC... или EQ...</i>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Отмена", callback_data="main_menu")]
            ]),
            parse_mode="HTML"
        )
        await state.set_state(SellStarsStates.waiting_wallet)
    except ValueError:
        await message.answer("❌ Введите целое число звезд")


@router.message(SellStarsStates.waiting_wallet)
async def process_sell_wallet(message: Message, state: FSMContext):
    """Обработка адреса кошелька"""
    if not await check_subscription(message.bot, message.from_user.id):
        await message.answer(
            f"🔒 Для использования бота подпишитесь на канал {CHANNEL_ID}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📢 Подписаться", url=CHANNEL_URL)]
            ])
        )
        await state.clear()
        return
    
    wallet = message.text.strip()
    
    if not wallet or len(wallet) < 10:
        await message.answer("❌ Введите корректный адрес кошелька TON\nПример: UQC... или EQ...")
        return
    
    data = await state.get_data()
    amount = data.get('sell_amount')
    usdt_amount = data.get('usdt_amount')
    
    if not amount or not usdt_amount:
        await message.answer("❌ Ошибка данных. Начните заново: /start")
        await state.clear()
        return
    
    db = get_db()
    async with db.get_session() as session:
        order = CryptoOrder(
            user_id=message.from_user.id,
            type="sell_stars",
            amount_stars=amount,
            crypto_amount=usdt_amount,
            wallet_address=wallet,
            status="pending"
        )
        session.add(order)
        await session.commit()
        
        for admin_id in ADMIN_IDS if isinstance(ADMIN_IDS, list) else [ADMIN_IDS]:
            try:
                admin_text = (
                    f"📢 <b>Новая заявка на продажу звезд!</b>\n\n"
                    f"👤 Продавец: @{message.from_user.username} (ID: {message.from_user.id})\n"
                    f"⭐ Количество: {amount} звезд\n"
                    f"💰 Сумма к выплате: {usdt_amount} USDT\n"
                    f"🏦 Кошелек: <code>{wallet}</code>"
                )
                await message.bot.send_message(admin_id, admin_text, parse_mode="HTML")
            except Exception as e:
                logger.error(f"Failed to notify admin: {e}")
    
    await message.answer(
        f"✅ <b>Заявка на продажу создана!</b>\n\n"
        f"⭐ Звезды: {amount}\n"
        f"💰 Сумма к выплате: {usdt_amount} USDT\n"
        f"🏦 Кошелек: <code>{wallet}</code>\n\n"
        f"<b>Далее:</b>\n"
        f"1. Отправьте {amount} звезд боту @miller_starsbot\n"
        f"2. Администратор проверит поступление\n"
        f"3. Средства будут отправлены на ваш кошелек\n\n"
        f"<i>Обычно обработка занимает до 30 минут</i>",
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML"
    )
    await state.clear()


@router.callback_query(F.data == "buy_stars_menu")
async def buy_stars_menu(callback: CallbackQuery, state: FSMContext):
    """Меню покупки звезд"""
    if not await check_subscription(callback.bot, callback.from_user.id):
        await send_message_safe(
            callback,
            "🔒 <b>Требуется подписка</b>\n\nПодпишитесь на канал @miller_news",
            InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📢 Подписаться", url=CHANNEL_URL)],
                [InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub")]
            ])
        )
        return
    
    await send_message_safe(
        callback,
        "💎 <b>Покупка Telegram Stars</b>\n\n"
        "📝 Сначала укажите, кому отправить звезды:\n\n"
        "<b>Выберите получателя:</b>",
        InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Отправить себе", callback_data="recipient_me_stars")],
            [InlineKeyboardButton(text="👤 Отправить другу", callback_data="recipient_other_stars")],
            [InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")]
        ])
    )
    await callback.answer()


@router.callback_query(F.data == "recipient_me_stars")
async def recipient_me_stars(callback: CallbackQuery, state: FSMContext):
    """Получатель - я сам"""
    await state.update_data(
        recipient_username=callback.from_user.username or f"user_{callback.from_user.id}",
        recipient_id=callback.from_user.id
    )
    
    await send_message_safe(
        callback,
        "💎 <b>Покупка Telegram Stars</b>\n\n"
        f"Получатель: <b>Вы (@{callback.from_user.username or 'нет username'})</b>\n\n"
        "Теперь выберите пакет звезд или введите свою сумму:\n\n"
        "💰 Курс: 1 звезда = 0.018 USDT",
        buy_stars_packs_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "recipient_other_stars")
async def recipient_other_stars(callback: CallbackQuery, state: FSMContext):
    """Запрос username получателя"""
    await send_message_safe(
        callback,
        "📝 <b>Введите username получателя звезд:</b>\n\n"
        "Например: @username\n\n"
        "<i>⚠️ Убедитесь, что получатель зарегистрирован в Telegram и в нашем боте</i>",
        InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="buy_stars_menu")]
        ])
    )
    await state.set_state(BuyStarsStates.waiting_recipient)
    await callback.answer()


@router.message(BuyStarsStates.waiting_recipient)
async def process_recipient_stars(message: Message, state: FSMContext):
    """Обработка username получателя для звезд"""
    if not await check_subscription(message.bot, message.from_user.id):
        await message.answer(
            f"🔒 Для использования бота подпишитесь на канал {CHANNEL_ID}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📢 Подписаться", url=CHANNEL_URL)]
            ])
        )
        await state.clear()
        return
    
    username = message.text.strip().replace('@', '')
    
    if not username:
        await message.answer("❌ Введите корректный username\nНапример: @username")
        return
    
    await state.update_data(recipient_username=username)
    
    await message.answer(
        f"💎 <b>Покупка Telegram Stars</b>\n\n"
        f"Получатель: <b>@{username}</b>\n\n"
        "Теперь выберите пакет звезд или введите свою сумму:\n\n"
        "💰 Курс: 1 звезда = 0.018 USDT",
        reply_markup=buy_stars_packs_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(None)


@router.callback_query(F.data.startswith("buy_pack_"))
async def buy_stars_pack(callback: CallbackQuery, state: FSMContext):
    """Покупка пакета звезд"""
    if not await check_subscription(callback.bot, callback.from_user.id):
        await send_message_safe(
            callback,
            "🔒 <b>Требуется подписка</b>\n\nПодпишитесь на канал @miller_news",
            InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📢 Подписаться", url=CHANNEL_URL)],
                [InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub")]
            ])
        )
        return
    
    amount = int(callback.data.split("_")[-1])
    
    data = await state.get_data()
    recipient = data.get('recipient_username')
    
    if not recipient:
        await callback.answer("❌ Сначала выберите получателя!", show_alert=True)
        await buy_stars_menu(callback, state)
        return
    
    if amount == 1050:
        calculated_amount = 19.0
        actual_stars = 1050
    else:
        calculated_amount = round(amount * 0.018, 2)
        actual_stars = amount
    
    invoice = await crypto_bot.create_invoice(
        asset="USDT",
        amount=calculated_amount,
        description=f"Покупка {actual_stars} Telegram Stars для @{recipient}",
        paid_btn_name="openBot",
        paid_btn_url="https://t.me/miller_starsbot",
        payload=f"stars_{callback.from_user.id}_{actual_stars}_{recipient}"
    )
    
    if invoice:
        db = get_db()
        async with db.get_session() as session:
            order = CryptoOrder(
                user_id=callback.from_user.id,
                type="buy_stars",
                amount_stars=actual_stars,
                crypto_amount=calculated_amount,
                crypto_invoice_id=str(invoice["invoice_id"]),
                recipient_username=recipient,
                status="pending"
            )
            session.add(order)
            await session.commit()
        
        pay_url = invoice["pay_url"]
        text = (
            f"💎 <b>Заказ на {actual_stars} звезд</b>\n\n"
            f"📤 Получатель: @{recipient}\n"
            f"📊 Сумма к оплате: {calculated_amount} USDT\n"
            f"🌐 Сеть: TON\n\n"
            f"⚠️ Оплачивайте строго одну транзакцию!\n\n"
            f"Для оплаты нажмите кнопку ниже:"
        )
        
        await send_message_safe(callback, text, payment_keyboard(pay_url, str(invoice["invoice_id"])))
    else:
        await send_message_safe(callback, "❌ Ошибка при создании счета. Попробуйте позже.")
    
    await callback.answer()


@router.callback_query(F.data == "custom_stars")
async def custom_stars_amount(callback: CallbackQuery, state: FSMContext):
    """Ввод своей суммы звезд"""
    if not await check_subscription(callback.bot, callback.from_user.id):
        await send_message_safe(
            callback,
            "🔒 <b>Требуется подписка</b>\n\nПодпишитесь на канал @miller_news",
            InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📢 Подписаться", url=CHANNEL_URL)],
                [InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub")]
            ])
        )
        return
    
    data = await state.get_data()
    recipient = data.get('recipient_username')
    
    if not recipient:
        await callback.answer("❌ Сначала выберите получателя!", show_alert=True)
        await buy_stars_menu(callback, state)
        return
    
    await send_message_safe(
        callback,
        "📝 <b>Введите желаемое количество звезд:</b>\n\n"
        f"Получатель: @{recipient}\n"
        "Минимум: 50 звезд\n"
        "💰 Курс: 1 звезда = 0.018 USDT\n\n"
        "<i>Отправьте число, например: 250</i>",
        InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="buy_stars_menu")]
        ])
    )
    await state.set_state(BuyStarsStates.waiting_custom_amount)
    await callback.answer()


@router.message(BuyStarsStates.waiting_custom_amount)
async def process_custom_stars(message: Message, state: FSMContext):
    """Обработка своей суммы звезд"""
    if not await check_subscription(message.bot, message.from_user.id):
        await message.answer(
            f"🔒 Подпишитесь на канал {CHANNEL_ID}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📢 Подписаться", url=CHANNEL_URL)]
            ])
        )
        await state.clear()
        return
    
    try:
        amount = int(message.text)
        if amount < 50:
            await message.answer("❌ Минимальное количество: 50 звезд")
            return
        
        data = await state.get_data()
        recipient = data.get('recipient_username')
        
        if not recipient:
            await message.answer("❌ Ошибка: получатель не выбран")
            await state.clear()
            return
        
        calculated_amount = round(amount * 0.018, 2)
        
        invoice = await crypto_bot.create_invoice(
            asset="USDT",
            amount=calculated_amount,
            description=f"Покупка {amount} Telegram Stars для @{recipient}",
            paid_btn_name="openBot",
            paid_btn_url="https://t.me/miller_starsbot",
            payload=f"stars_{message.from_user.id}_{amount}_{recipient}"
        )
        
        if invoice:
            db = get_db()
            async with db.get_session() as session:
                order = CryptoOrder(
                    user_id=message.from_user.id,
                    type="buy_stars",
                    amount_stars=amount,
                    crypto_amount=calculated_amount,
                    crypto_invoice_id=str(invoice["invoice_id"]),
                    recipient_username=recipient,
                    status="pending"
                )
                session.add(order)
                await session.commit()
            
            pay_url = invoice["pay_url"]
            text = (
                f"💎 <b>Заказ на {amount} звезд</b>\n\n"
                f"📤 Получатель: @{recipient}\n"
                f"📊 Сумма к оплате: {calculated_amount} USDT\n"
                f"🌐 Сеть: TON\n\n"
                f"⚠️ Оплачивайте строго одну транзакцию!\n\n"
                f"Для оплаты нажмите кнопку ниже:"
            )
            
            await message.answer(text, reply_markup=payment_keyboard(pay_url, str(invoice["invoice_id"])), parse_mode="HTML")
        else:
            await message.answer("❌ Ошибка при создании счета. Попробуйте позже.")
        
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите целое число звезд (минимум 50)")


@router.callback_query(F.data.startswith("check_payment_"))
async def check_crypto_payment(callback: CallbackQuery, state: FSMContext):
    await callback.answer("⏳ Проверяю платеж...")
    
    invoice_id = int(callback.data.split("_")[-1])
    invoice_status = await crypto_bot.get_invoice(invoice_id)
    
    if invoice_status and invoice_status["status"] == "paid":
        db = get_db()
        async with db.get_session() as session:
            result = await session.execute(
                select(CryptoOrder).where(CryptoOrder.crypto_invoice_id == str(invoice_id))
            )
            order = result.scalar_one_or_none()
            if order and order.status == "pending":
                order.status = "paid"
                
                user_orders_result = await session.execute(
                    select(CryptoOrder).where(
                        CryptoOrder.user_id == callback.from_user.id,
                        CryptoOrder.type == "buy_stars",
                        CryptoOrder.status == "paid"
                    )
                )
                is_first_purchase = len(user_orders_result.scalars().all()) == 0
                
                if is_first_purchase:
                    await ReferralSystem.reward_referrer_first_purchase(callback.from_user.id)
                
                await session.commit()
                
                await callback.bot.send_message(
                    ADMIN_ID if isinstance(ADMIN_ID, int) else ADMIN_ID[0],
                    f"🔔 <b>Оплаченный заказ!</b>\n\n"
                    f"Покупатель: @{callback.from_user.username} (ID: {callback.from_user.id})\n"
                    f"Stars: {order.amount_stars}\n"
                    f"Получатель: @{order.recipient_username}\n"
                    f"Сумма: {order.crypto_amount} USDT\n\n"
                    f"⚠️ Отправьте @{order.recipient_username} {order.amount_stars} звезд",
                    parse_mode="HTML"
                )
                
                await send_message_safe(
                    callback,
                    f"✅ <b>Оплата подтверждена!</b>\n\n"
                    f"Вы приобрели {order.amount_stars} звезд.\n"
                    f"Получатель: @{order.recipient_username}\n\n"
                    f"Звезды будут отправлены в ближайшее время.",
                    main_menu_keyboard()
                )
    else:
        await callback.answer("❌ Платеж еще не получен. Попробуйте позже.", show_alert=True)


@router.callback_query(F.data == "profile")
async def show_profile(callback: CallbackQuery):
    if not await check_subscription(callback.bot, callback.from_user.id):
        await send_message_safe(
            callback,
            "🔒 <b>Требуется подписка</b>\n\nПодпишитесь на канал @miller_news",
            InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📢 Подписаться", url=CHANNEL_URL)],
                [InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub")]
            ])
        )
        return
    
    db = get_db()
    async with db.get_session() as session:
        user = await session.get(User, callback.from_user.id)
        
        if user:
            bot_info = await callback.bot.get_me()
            ref_link = get_referral_link(bot_info.username, user.referral_code)
            
            text = (
                f"👤 <b>Ваш профиль</b>\n\n"
                f"🆔 ID: {user.user_id}\n"
                f"📛 Username: @{user.username or 'Нет'}\n"
                f"🤝 Сделок: {user.deals_count}\n"
                f"💎 Баланс звезд: {user.referral_balance}\n"
                f"👥 Приглашено друзей: {user.referrals_count}\n\n"
                f"🔗 <b>Реферальная ссылка:</b>\n<code>{ref_link}</code>\n\n"
                f"📅 С нами с: {user.created_at.strftime('%d.%m.%Y')}"
            )
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📋 Список приглашенных", callback_data="referrals_list")],
                [InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")]
            ])
        else:
            text = "Профиль не найден"
            keyboard = main_menu_keyboard()
    
    await send_message_safe(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data == "referrals_list")
async def show_referrals_list(callback: CallbackQuery):
    """Список приглашенных"""
    if not await check_subscription(callback.bot, callback.from_user.id):
        await send_message_safe(
            callback,
            "🔒 <b>Требуется подписка</b>\n\nПодпишитесь на канал @miller_news",
            InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📢 Подписаться", url=CHANNEL_URL)],
                [InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub")]
            ])
        )
        return
    
    db = get_db()
    async with db.get_session() as session:
        result = await session.execute(
            select(User).where(User.referrer_id == callback.from_user.id)
        )
        referrals = result.scalars().all()
        
        if not referrals:
            text = "👥 У вас пока нет приглашенных пользователей."
        else:
            text = f"👥 <b>Приглашенные пользователи ({len(referrals)}):</b>\n\n"
            for i, ref in enumerate(referrals[:20], 1):
                text += f"{i}. @{ref.username or 'Без username'} (ID: {ref.user_id})\n"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 К профилю", callback_data="profile")]
        ])
    
    await send_message_safe(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data == "support")
async def support_handler(callback: CallbackQuery):
    """Поддержка"""
    await send_message_safe(
        callback,
        "📞 <b>Поддержка Miller Stars</b>\n\n"
        "По всем вопросам обращайтесь:\n"
        "@miller_support\n\n"
        "Или напишите менеджеру @refMarvinn.",
        InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")]
        ])
    )
    await callback.answer()


@router.callback_query(F.data == "referral_menu")
async def referral_menu_handler(callback: CallbackQuery):
    """Реферальное меню"""
    if not await check_subscription(callback.bot, callback.from_user.id):
        await send_message_safe(
            callback,
            "🔒 <b>Требуется подписка</b>\n\nПодпишитесь на канал @miller_news",
            InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📢 Подписаться", url=CHANNEL_URL)],
                [InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub")]
            ])
        )
        return
    
    await send_message_safe(
        callback,
        "🔗 <b>Реферальная программа</b>\n\n"
        f"Приглашайте друзей и получайте бонусы!\n"
        f"• +{ReferralSystem.REFERRAL_REWARD} звезд за каждого приглашенного\n"
        f"• +{ReferralSystem.FIRST_PURCHASE_REWARD} звезд за первую покупку друга\n\n"
        "Выберите действие:",
        referral_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "get_referral_link")
async def show_referral_link(callback: CallbackQuery):
    """Показать реферальную ссылку"""
    if not await check_subscription(callback.bot, callback.from_user.id):
        await send_message_safe(
            callback,
            "🔒 <b>Требуется подписка</b>\n\nПодпишитесь на канал @miller_news",
            InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📢 Подписаться", url=CHANNEL_URL)],
                [InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub")]
            ])
        )
        return
    
    db = get_db()
    async with db.get_session() as session:
        user = await session.get(User, callback.from_user.id)
        
        if not user:
            await callback.answer("❌ Пользователь не найден", show_alert=True)
            return
        
        bot_info = await callback.bot.get_me()
        ref_link = get_referral_link(bot_info.username, user.referral_code)
        
        text = (
            f"🔗 <b>Ваша реферальная ссылка:</b>\n\n<code>{ref_link}</code>\n\n"
            f"📊 <b>Статистика:</b>\n"
            f"👥 Приглашено: {user.referrals_count}\n"
            f"💰 Баланс: {user.referral_balance} звезд"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Поделиться", url=f"https://t.me/share/url?url={ref_link}")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="referral_menu")]
        ])
    
    await send_message_safe(callback, text, keyboard)
    await callback.answer()


@router.callback_query(F.data == "withdraw_referral")
async def withdraw_referral_start(callback: CallbackQuery, state: FSMContext):
    """Вывод реферальных звезд"""
    if not await check_subscription(callback.bot, callback.from_user.id):
        await send_message_safe(
            callback,
            "🔒 <b>Требуется подписка</b>\n\nПодпишитесь на канал @miller_news",
            InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📢 Подписаться", url=CHANNEL_URL)],
                [InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub")]
            ])
        )
        return
    
    db = get_db()
    async with db.get_session() as session:
        user = await session.get(User, callback.from_user.id)
        
        if not user or user.referral_balance < 15:
            await callback.answer(
                f"❌ Минимальная сумма: 15 звезд\nВаш баланс: {user.referral_balance if user else 0} звезд", 
                show_alert=True
            )
            return
        
        await send_message_safe(
            callback,
            f"💎 <b>Вывод реферальных звезд</b>\n\n"
            f"💰 Ваш баланс: <b>{user.referral_balance} звезд</b>\n"
            f"⚠️ Минимальная сумма: <b>15 звезд</b>\n\n"
            f"📝 Введите количество звезд для вывода:",
            InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="referral_menu")]
            ])
        )
        await state.set_state(WithdrawReferralStates.waiting_amount)
    await callback.answer()


@router.message(WithdrawReferralStates.waiting_amount)
async def process_withdraw_amount(message: Message, state: FSMContext):
    """Обработка суммы вывода"""
    if not await check_subscription(message.bot, message.from_user.id):
        await message.answer(
            f"🔒 Подпишитесь на канал {CHANNEL_ID}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📢 Подписаться", url=CHANNEL_URL)]
            ])
        )
        await state.clear()
        return
    
    try:
        amount = int(message.text)
        
        if amount < 15:
            await message.answer("❌ Минимальная сумма вывода: 15 звезд")
            return
        
        db = get_db()
        async with db.get_session() as session:
            user = await session.get(User, message.from_user.id)
            
            if not user:
                await message.answer("❌ Пользователь не найден")
                await state.clear()
                return
            
            if amount > user.referral_balance:
                await message.answer(f"❌ Недостаточно звезд! У вас: {user.referral_balance}")
                return
            
            user.referral_balance -= amount
            
            order = CryptoOrder(
                user_id=message.from_user.id,
                type="withdraw_referral",
                amount_stars=amount,
                status="pending",
                recipient_username=message.from_user.username or f"user_{message.from_user.id}"
            )
            session.add(order)
            await session.commit()
            
            for admin_id in ADMIN_IDS:
                try:
                    admin_text = (
                        f"📢 <b>Заявка на вывод реферальных звезд!</b>\n\n"
                        f"Заказ: #{order.id}\n"
                        f"От: @{message.from_user.username}\n"
                        f"Сумма: {amount} звезд"
                    )
                    await message.bot.send_message(admin_id, admin_text, parse_mode="HTML")
                except Exception as e:
                    logger.error(f"Failed to notify admin: {e}")
        
        await message.answer(
            f"✅ <b>Заявка на вывод создана!</b>\n\n"
            f"⭐ Сумма: {amount} звезд\n"
            f"💰 Остаток: {user.referral_balance} звезд\n\n"
            f"Администратор отправит вам звезды в ближайшее время.",
            reply_markup=main_menu_keyboard(),
            parse_mode="HTML"
        )
        await state.clear()
        
    except ValueError:
        await message.answer("❌ Введите целое число звезд (минимум 15)")


@router.callback_query(F.data.startswith("admin_sent_ref_"))
async def admin_confirm_referral_sent(callback: CallbackQuery):
    """Админ подтверждает отправку звезд"""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    parts = callback.data.replace("admin_sent_ref_", "").split("_")
    order_id = int(parts[0])
    user_id = int(parts[1])
    amount = int(parts[2])
    
    db = get_db()
    async with db.get_session() as session:
        order = await session.get(CryptoOrder, order_id)
        if order:
            order.status = "completed"
            await session.commit()
            
            try:
                await callback.bot.send_message(
                    user_id,
                    f"✅ <b>Звезды отправлены!</b>\n\n"
                    f"⭐ Количество: {amount} звезд\n"
                    f"📦 Заказ: #{order_id}\n\n"
                    f"Спасибо за участие в реферальной программе! 🎉",
                    parse_mode="HTML"
                )
            except Exception:
                pass
            
            await callback.message.edit_text(
                f"✅ Отправка подтверждена!\nЗаказ #{order_id}: {amount} звезд",
                reply_markup=None
            )
            await callback.answer("✅ Подтверждено!", show_alert=True)
        else:
            await callback.answer("❌ Заказ не найден", show_alert=True)


@router.callback_query(F.data.startswith("admin_reject_ref_"))
async def admin_reject_referral_withdraw(callback: CallbackQuery):
    """Админ отклоняет заявку на вывод"""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещен", show_alert=True)
        return
    
    parts = callback.data.replace("admin_reject_ref_", "").split("_")
    order_id = int(parts[0])
    user_id = int(parts[1])
    amount = int(parts[2])
    
    db = get_db()
    async with db.get_session() as session:
        order = await session.get(CryptoOrder, order_id)
        user = await session.get(User, user_id)
        
        if order and user:
            order.status = "cancelled"
            user.referral_balance += amount
            await session.commit()
            
            try:
                await callback.bot.send_message(
                    user_id,
                    f"❌ <b>Заявка на вывод отклонена</b>\n\n"
                    f"⭐ {amount} звезд возвращены на ваш баланс.",
                    parse_mode="HTML"
                )
            except Exception:
                pass
            
            await callback.message.edit_text(
                f"❌ Заявка #{order_id} отклонена.\n{amount} звезд возвращены",
                reply_markup=None
            )
            await callback.answer("✅ Отклонено", show_alert=True)
        else:
            await callback.answer("❌ Ошибка данных", show_alert=True)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    """Отмена текущего действия"""
    await state.clear()
    await message.answer(
        "❌ Действие отменено.",
        reply_markup=main_menu_keyboard()
    )