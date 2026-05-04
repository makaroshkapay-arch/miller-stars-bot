"""
Модуль покупки старых подарков Telegram
Сначала выбор получателя, потом выбор подарка
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
from sqlalchemy import select, and_
from datetime import datetime
from typing import Optional, List
import logging

from config import ADMIN_IDS, CRYPTO_BOT_TOKEN
from database.models import User, GiftPurchase
from database.core import get_db
from payments.crypto_bot import CryptoBotAPI

logger = logging.getLogger(__name__)

router = Router()
crypto_bot = CryptoBotAPI(CRYPTO_BOT_TOKEN)

AVAILABLE_GIFTS = [
    {
        "gift_id": 5956217000635139069,
        "name": "🎅 Новогодний Мишка",
        "stars_price": 65,
        "crypto_price": 1.2,
        "description": "Коллекционный новогодний мишка из ограниченной серии"
    },
    {
        "gift_id": 5922558454332916696,
        "name": "🎄 Новогодняя Елка",
        "stars_price": 65,
        "crypto_price": 1.2,
        "description": "Праздничная ёлка из новогодней коллекции Telegram"
    },
    {
        "gift_id": 5800655655995968830,
        "name": "💘 Мишка Валентин",
        "stars_price": 65,
        "crypto_price": 1.2,
        "description": "Романтичный мишка ко Дню Святого Валентина"
    },
    {
        "gift_id": 5801108895304779062,
        "name": "💗 Сердечко 8 марта",
        "stars_price": 65,
        "crypto_price": 1.2,
        "description": "Праздничное сердечко к Международному женскому дню"
    },
    {
        "gift_id": 5866352046986232958,
        "name": "🌷 Мишка 8 марта",
        "stars_price": 65,
        "crypto_price": 1.2,
        "description": "Весенний мишка в подарок на 8 марта"
    },
    {
        "gift_id": 5893356958802511476,
        "name": "🍀 Мишка Денежный",
        "stars_price": 65,
        "crypto_price": 1.2,
        "description": "Удачливый мишка-лепрекон с золотом"
    },
    {
        "gift_id": 5935895822435615975,
        "name": "🎭 Мишка 1 апреля",
        "stars_price": 65,
        "crypto_price": 1.2,
        "description": "Весёлый мишка на День смеха"
    },
    {
        "gift_id": 5969796561943660080,
        "name": "🐰 Пасхальный мишка",
        "stars_price": 65,
        "crypto_price": 1.2,
        "description": "Милый пасхальный мишка с яйцами"
    }
]


class GiftPurchaseStates(StatesGroup):
    """Состояния для покупки подарка"""
    waiting_recipient_username = State()

def get_animated_emoji(emoji_id: str, fallback: str) -> str:
    """Создает HTML-тег для анимированного эмодзи"""
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'


def get_gifts_keyboard():
    """Клавиатура с доступными подарками"""
    keyboard = []
    
    for gift in AVAILABLE_GIFTS:

        keyboard.append([
            InlineKeyboardButton(
                text=f"{gift['name']} - ⭐{gift['stars_price']} / ${gift['crypto_price']}",
                callback_data=f"select_gift_{gift['gift_id']}"
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_payment_method_keyboard(gift_id: int):
    """Клавиатура выбора способа оплаты"""
    keyboard = [
        [
            InlineKeyboardButton(
                text="⭐ Оплатить Stars",
                callback_data=f"pay_gift_{gift_id}_stars"
            )
        ],
        [
            InlineKeyboardButton(
                text="💎 Оплатить Crypto (USDT)",
                callback_data=f"pay_gift_{gift_id}_crypto"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔙 К выбору подарка",
                callback_data="show_gifts_menu"
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


async def send_gift_to_user(bot: Bot, user_id: int, gift_id: int) -> bool:
    """Отправка подарка пользователю методом sendGift"""
    try:
        logger.info(f"🚀 Отправка подарка {gift_id} пользователю {user_id}")
        result = await bot.send_gift(
            user_id=user_id,
            gift_id=str(gift_id),
            pay_for_upgrade=False,
            text=f"🎁 Ваш подарок"
        )
        logger.info(f"✅ Gift {gift_id} отправлен пользователю {user_id}")
        return True
    except TelegramBadRequest as e:
        error_msg = str(e)
        logger.error(f"❌ Ошибка Telegram: {error_msg}")
        with open("gift_errors.log", "a", encoding="utf-8") as f:
            f.write(f"{datetime.now()}: Gift {gift_id} to {user_id} - {error_msg}\n")
        return False
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка: {e}")
        return False


async def notify_admin_gift_purchase(bot: Bot, purchase_info: dict):
    """Уведомление администраторов о покупке подарка"""
    for admin_id in ADMIN_IDS:
        try:
            text = (
                f"🎁 <b>Куплен подарок!</b>\n\n"
                f"Покупатель: {purchase_info.get('buyer_id')}\n"
                f"Получатель: @{purchase_info.get('recipient_username')}\n"
                f"Подарок: {purchase_info['gift_name']}\n"
                f"Gift ID: {purchase_info['gift_id']}\n"
                f"Способ оплаты: {purchase_info['payment_type']}\n"
                f"Сумма: {purchase_info['amount']}\n"
                f"Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
            )
            await bot.send_message(admin_id, text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Не удалось уведомить админа {admin_id}: {e}")


# ==================== НОВАЯ ЛОГИКА: СНАЧАЛА ВЫБОР ПОЛУЧАТЕЛЯ ====================

@router.callback_query(F.data == "buy_gifts_menu")
async def buy_gifts_start(callback: CallbackQuery):
    """Начало покупки подарка - выбор получателя"""
    try:
        await callback.message.edit_text(
            "🎁 <b>Покупка коллекционных подарков Telegram</b>\n\n"
            "📝 <b>Сначала выберите, кому отправить подарок:</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📤 Отправить себе", callback_data="gift_recipient_me")],
                [InlineKeyboardButton(text="👤 Отправить другу", callback_data="gift_recipient_other")],
                [InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")]
            ]),
            parse_mode="HTML"
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(F.data == "gift_recipient_me")
async def gift_recipient_me(callback: CallbackQuery, state: FSMContext):
    """Получатель подарка - я сам"""
    await state.update_data(
        gift_recipient_username=callback.from_user.username or f"user_{callback.from_user.id}",
        gift_recipient_id=callback.from_user.id
    )
    
    # Показываем выбор подарка
    await callback.message.edit_text(
        f"🎁 <b>Покупка коллекционных подарков Telegram</b>\n\n"
        f"Получатель: <b>Вы (@{callback.from_user.username or 'нет username'})</b>\n\n"
        "Теперь выберите подарок из списка:\n"
        "<i>Бот купит подарок и отправит его вам</i>\n\n"
        "💰 <b>Доступные подарки:</b>",
        reply_markup=get_gifts_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "gift_recipient_other")
async def gift_recipient_other(callback: CallbackQuery, state: FSMContext):
    """Запрос username получателя подарка"""
    await callback.message.edit_text(
        "📝 <b>Введите username получателя подарка:</b>\n\n"
        "Например: @username\n\n"
        "<i>⚠️ Убедитесь, что получатель зарегистрирован в Telegram и в нашем боте</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="buy_gifts_menu")]
        ])
    )
    await state.set_state(GiftPurchaseStates.waiting_recipient_username)
    await callback.answer()


@router.message(GiftPurchaseStates.waiting_recipient_username)
async def process_gift_recipient_username(message: Message, state: FSMContext):
    """Обработка username получателя подарка"""
    username = message.text.strip().replace('@', '')
    
    if not username:
        await message.answer(
            "❌ Введите корректный username\n"
            "Например: @username\n\n"
            "Или нажмите /cancel для отмены"
        )
        return
    
    # Сохраняем получателя
    await state.update_data(gift_recipient_username=username)
    
    # Показываем выбор подарка
    await message.answer(
        f"🎁 <b>Покупка коллекционных подарков Telegram</b>\n\n"
        f"Получатель: <b>@{username}</b>\n\n"
        "Теперь выберите подарок из списка:\n"
        "<i>Бот купит подарок и отправит его получателю</i>\n\n"
        "💰 <b>Доступные подарки:</b>",
        reply_markup=get_gifts_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(None)  # Сбрасываем состояние


# ==================== ВЫБОР ПОДАРКА И ОПЛАТА ====================

@router.callback_query(F.data == "show_gifts_menu")
async def back_to_gifts_menu(callback: CallbackQuery, state: FSMContext):
    """Возврат к списку подарков"""
    data = await state.get_data()
    recipient = data.get('gift_recipient_username', 'не выбран')
    
    try:
        await callback.message.edit_text(
            f"🎁 <b>Покупка коллекционных подарков Telegram</b>\n\n"
            f"Получатель: <b>@{recipient}</b>\n\n"
            "Выберите подарок из списка:\n"
            "<i>Бот купит подарок и отправит его получателю</i>\n\n"
            "💰 <b>Доступные подарки:</b>",
            reply_markup=get_gifts_keyboard(),
            parse_mode="HTML"
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("select_gift_"))
async def select_gift_for_purchase(callback: CallbackQuery, state: FSMContext):
    """Выбор конкретного подарка"""
    gift_id_str = callback.data.replace("select_gift_", "")
    
    try:
        gift_id = int(gift_id_str)
    except ValueError:
        await callback.answer("❌ Ошибка данных", show_alert=True)
        return
    
    gift = next((g for g in AVAILABLE_GIFTS if g['gift_id'] == gift_id), None)
    
    if not gift:
        await callback.answer("❌ Подарок не найден", show_alert=True)
        return
    
    # Проверяем, выбран ли получатель
    data = await state.get_data()
    recipient = data.get('gift_recipient_username')
    
    if not recipient:
        await callback.answer("❌ Сначала выберите получателя!", show_alert=True)
        await buy_gifts_start(callback)
        return
    
    try:
        await callback.message.edit_text(
            f"🎁 <b>{gift['name']}</b>\n\n"
            f"📤 Получатель: @{recipient}\n"
            f"📝 {gift['description']}\n\n"
            f"<b>Стоимость:</b>\n"
            f"• ⭐ {gift['stars_price']} Stars\n"
            f"• 💎 ${gift['crypto_price']} USDT\n\n"
            f"Выберите способ оплаты:",
            reply_markup=get_payment_method_keyboard(gift_id),
            parse_mode="HTML"
        )
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("pay_gift_"))
async def process_gift_payment(callback: CallbackQuery, state: FSMContext):
    """Обработка оплаты подарка"""
    data = callback.data.replace("pay_gift_", "")
    
    if "_stars" in data:
        gift_id_str = data.replace("_stars", "")
        payment_type = "stars"
    elif "_crypto" in data:
        gift_id_str = data.replace("_crypto", "")
        payment_type = "crypto"
    else:
        await callback.answer("❌ Ошибка данных", show_alert=True)
        return
    
    try:
        gift_id = int(gift_id_str)
    except ValueError:
        await callback.answer("❌ Ошибка данных", show_alert=True)
        return
    
    gift = next((g for g in AVAILABLE_GIFTS if g['gift_id'] == gift_id), None)
    if not gift:
        await callback.answer("❌ Подарок не найден", show_alert=True)
        return
    
    # Получаем данные получателя
    state_data = await state.get_data()
    recipient = state_data.get('gift_recipient_username')
    
    if not recipient:
        await callback.answer("❌ Получатель не выбран!", show_alert=True)
        await buy_gifts_start(callback)
        return
    
    # Сохраняем данные
    await state.update_data(
        gift_id=gift_id,
        payment_type=payment_type,
        gift_name=gift['name'],
        stars_price=gift['stars_price'],
        crypto_price=gift['crypto_price']
    )
    
    # ========== ОПЛАТА STARS ==========
    if payment_type == "stars":
        logger.info(f"💳 Создание счёта Stars: {gift['name']} - {gift['stars_price']} Stars для @{recipient}")
        
        await callback.message.answer_invoice(
            title=f"Подарок: {gift['name']}",
            description=f"Покупка подарка для @{recipient}\n{gift['description']}",
            payload=f"gift_{callback.from_user.id}_{gift_id}_{recipient}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label=gift['name'], amount=gift['stars_price'])],
            start_parameter="gift_purchase",
            need_name=False,
            need_phone_number=False,
            need_email=False,
            need_shipping_address=False,
            is_flexible=False
        )
        
        try:
            await callback.message.delete()
        except:
            pass
        
        await callback.answer()
    
    # ========== ОПЛАТА CRYPTO ==========
    elif payment_type == "crypto":
        logger.info(f"💎 Создание счёта Crypto: {gift['name']} - ${gift['crypto_price']} для @{recipient}")
        
        invoice = await crypto_bot.create_invoice(
            asset="USDT",
            amount=gift['crypto_price'],
            description=f"Покупка подарка: {gift['name']} для @{recipient}",
            payload=f"gift_{gift_id}_{callback.from_user.id}_{recipient}",
            paid_btn_name="openBot",
            paid_btn_url="https://t.me/miller_starsbot"
        )
        
        if invoice:
            # Сохраняем заказ в БД
            db = get_db()
            async with db.get_session() as session:
                purchase = GiftPurchase(
                    user_id=callback.from_user.id,
                    gift_id=gift_id,
                    payment_type="crypto",
                    amount_crypto=gift['crypto_price'],
                    status="pending",
                    telegram_invoice_id=str(invoice["invoice_id"])
                )
                session.add(purchase)
                await session.commit()
            
            await callback.message.edit_text(
                f"💎 <b>Счёт на оплату создан</b>\n\n"
                f"Подарок: {gift['name']}\n"
                f"Получатель: @{recipient}\n"
                f"Сумма: ${gift['crypto_price']} USDT\n\n"
                f"Для оплаты нажмите кнопку ниже:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="💳 Оплатить", url=invoice["pay_url"])],
                    [InlineKeyboardButton(
                        text="✅ Я оплатил", 
                        callback_data=f"check_gift_payment_{invoice['invoice_id']}_{gift_id}"
                    )],
                    [InlineKeyboardButton(text="🔙 К выбору подарка", callback_data="show_gifts_menu")]
                ]),
                parse_mode="HTML"
            )
        else:
            await callback.answer("❌ Ошибка создания счёта", show_alert=True)
        
        await callback.answer()


# ========== ОБРАБОТКА PRE-CHECKOUT (STARS) ==========
@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery, state: FSMContext, bot: Bot):
    """Обработка pre-checkout для Stars"""
    payload = pre_checkout_query.invoice_payload
    
    logger.info(f"🔍 Pre-checkout: {payload}")
    
    if payload.startswith("gift_"):
        parts = payload.split("_")
        
        if len(parts) < 4:
            await pre_checkout_query.answer(ok=False, error_message="Ошибка данных")
            return
        
        buyer_id = int(parts[1])
        gift_id = int(parts[2])
        recipient = parts[3]
        
        gift = next((g for g in AVAILABLE_GIFTS if g['gift_id'] == gift_id), None)
        
        if gift:
            # Подтверждаем платёж
            await pre_checkout_query.answer(ok=True)
            
            logger.info(f"✅ Pre-checkout OK: {gift['name']} от {buyer_id} для @{recipient}")
            
            # Сохраняем данные
            await state.update_data(
                gift_id=gift_id,
                gift_name=gift['name'],
                buyer_id=buyer_id,
                gift_recipient_username=recipient,
                payment_type="stars",
                amount=f"{gift['stars_price']} Stars"
            )
            
            # Сразу обрабатываем отправку
            await handle_gift_delivery(bot, buyer_id, recipient, gift, "stars", f"{gift['stars_price']} Stars")
        else:
            logger.error(f"❌ Подарок {gift_id} не найден")
            await pre_checkout_query.answer(ok=False, error_message="Подарок не найден")
    else:
        await pre_checkout_query.answer(ok=False, error_message="Неверный запрос")


# ========== УСПЕШНАЯ ОПЛАТА STARS ==========
@router.message(F.content_type == ContentType.SUCCESSFUL_PAYMENT)
async def process_successful_stars_payment(message: Message, state: FSMContext, bot: Bot):
    """Обработка успешной оплаты Stars"""
    if not message.successful_payment:
        return
    
    payload = message.successful_payment.invoice_payload
    
    if payload.startswith("gift_"):
        # Уже обработано в pre_checkout, ничего не делаем
        pass


async def handle_gift_delivery(bot: Bot, buyer_id: int, recipient_username: str, gift: dict, payment_type: str, amount: str):
    """Обработка доставки подарка"""
    logger.info(f"👤 Поиск получателя @{recipient_username} для подарка {gift['name']}")
    
    recipient_id = None
    
    # Способ 1: get_chat
    try:
        user_info = await bot.get_chat(f"@{recipient_username}")
        recipient_id = user_info.id
        logger.info(f"✅ Найден через get_chat: @{recipient_username} = {recipient_id}")
    except Exception as e:
        logger.warning(f"❌ get_chat: {e}")
    
    # Способ 2: через БД
    if not recipient_id:
        try:
            db = get_db()
            async with db.get_session() as session:
                result = await session.execute(
                    select(User).where(User.username == recipient_username)
                )
                user = result.scalar_one_or_none()
                if user:
                    recipient_id = user.user_id
                    logger.info(f"✅ Найден в БД: @{recipient_username} = {recipient_id}")
        except Exception as e:
            logger.warning(f"❌ Поиск в БД: {e}")
    
    if recipient_id:
        # Отправляем подарок
        success = await send_gift_to_user(bot, recipient_id, gift['gift_id'])
        
        if success:
            # Сохраняем в БД
            db = get_db()
            async with db.get_session() as session:
                purchase = GiftPurchase(
                    user_id=buyer_id,
                    gift_id=gift['gift_id'],
                    payment_type=payment_type,
                    status="completed"
                )
                session.add(purchase)
                await session.commit()
            
            # Уведомляем покупателя
            try:
                await bot.send_message(
                    buyer_id,
                    f"✅ <b>Подарок успешно отправлен!</b>\n\n"
                    f"🎁 {gift['name']}\n"
                    f"👤 Получатель: @{recipient_username}\n"
                    f"📦 Подарок уже в профиле получателя!\n\n"
                    f"Спасибо за покупку! ❤️",
                    parse_mode="HTML"
                )
            except:
                pass
            
            # Уведомляем получателя
            try:
                await bot.send_message(
                    recipient_id,
                    f"🎁 <b>Вам подарок!</b>\n\n"
                    f"Пользователь ID:{buyer_id} отправил вам коллекционный подарок: <b>{gift['name']}</b>\n\n"
                    f"Проверьте раздел «Подарки» в Telegram.",
                    parse_mode="HTML"
                )
            except:
                pass
            
            # Уведомляем админов
            await notify_admin_gift_purchase(bot, {
                "buyer_id": buyer_id,
                "gift_name": gift['name'],
                "gift_id": gift['gift_id'],
                "payment_type": payment_type,
                "amount": amount,
                "recipient_username": recipient_username
            })
        else:
            try:
                await bot.send_message(
                    buyer_id,
                    "❌ <b>Ошибка отправки подарка</b>\n\n"
                    "Свяжитесь с поддержкой.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="📞 Поддержка", callback_data="support")]
                    ])
                )
            except:
                pass
    else:
        # Получатель не найден
        try:
            bot_info = await bot.get_me()
            bot_username = bot_info.username
            
            db = get_db()
            async with db.get_session() as session:
                purchase = GiftPurchase(
                    user_id=buyer_id,
                    gift_id=gift['gift_id'],
                    payment_type=payment_type,
                    status="pending",
                    telegram_invoice_id=f"pending_{recipient_username}"
                )
                session.add(purchase)
                await session.commit()
                purchase_id = purchase.id
            
            deep_link = f"https://t.me/{bot_username}?start=gift_{purchase_id}"
            
            await bot.send_message(
                buyer_id,
                f"❌ <b>Не удалось найти @{recipient_username}</b>\n\n"
                f"📌 Отправьте получателю эту ссылку:\n\n"
                f"🔗 <code>{deep_link}</code>\n\n"
                f"После перехода подарок отправится автоматически.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📤 Поделиться ссылкой", 
                        url=f"https://t.me/share/url?url={deep_link}&text=Прими%20подарок!")],
                    [InlineKeyboardButton(text="🔙 В меню", callback_data="main_menu")]
                ])
            )
        except Exception as e:
            logger.error(f"Ошибка создания deep link: {e}")


# ========== ПРОВЕРКА ОПЛАТЫ CRYPTO ==========
@router.callback_query(F.data.startswith("check_gift_payment_"))
async def check_gift_crypto_payment(callback: CallbackQuery, state: FSMContext):
    """Проверка оплаты через CryptoBot"""
    data = callback.data.replace("check_gift_payment_", "")
    parts = data.rsplit("_", 1)
    
    if len(parts) != 2:
        await callback.answer("❌ Ошибка данных", show_alert=True)
        return
    
    try:
        invoice_id = int(parts[0])
        gift_id = int(parts[1])
    except ValueError:
        await callback.answer("❌ Ошибка данных", show_alert=True)
        return
    
    gift = next((g for g in AVAILABLE_GIFTS if g['gift_id'] == gift_id), None)
    if not gift:
        await callback.answer("❌ Подарок не найден", show_alert=True)
        return
    
    state_data = await state.get_data()
    recipient = state_data.get('gift_recipient_username')
    
    if not recipient:
        await callback.answer("❌ Получатель не найден", show_alert=True)
        return
    
    logger.info(f"🔍 Проверка оплаты Crypto: invoice={invoice_id}")
    
    invoice_status = await crypto_bot.get_invoice(invoice_id)
    
    if invoice_status and invoice_status.get("status") == "paid":
        await callback.answer("✅ Оплата подтверждена!")
        
        # Обновляем статус в БД
        db = get_db()
        async with db.get_session() as session:
            result = await session.execute(
                select(GiftPurchase).where(
                    GiftPurchase.telegram_invoice_id == str(invoice_id)
                )
            )
            purchase = result.scalar_one_or_none()
            if purchase:
                purchase.status = "paid"
                await session.commit()
        
        # Отправляем подарок
        await handle_gift_delivery(
            callback.bot,
            callback.from_user.id,
            recipient,
            gift,
            "crypto",
            f"${gift['crypto_price']} USDT"
        )
        
        try:
            await callback.message.edit_text(
                f"✅ <b>Подарок отправлен!</b>\n\n"
                f"🎁 {gift['name']}\n"
                f"👤 Получатель: @{recipient}",
                parse_mode="HTML"
            )
        except TelegramBadRequest:
            pass
    else:
        await callback.answer("❌ Оплата ещё не получена. Попробуйте позже", show_alert=True)
    
    await callback.answer()


@router.message(Command("test_gift"))
async def test_gift_send(message: Message):
    """Тестовая отправка подарка"""
    if message.from_user.id not in ADMIN_IDS:
        return
    
    await message.answer("🎁 Тестирую отправку...")
    
    success = await send_gift_to_user(
        message.bot,
        message.from_user.id,
        5956217000635139069
    )
    
    if success:
        await message.answer("✅ Подарок отправлен!")
    else:
        await message.answer("❌ Ошибка!")


@router.message(Command("cancel"))
async def cancel_gift_sending(message: Message, state: FSMContext):
    """Отмена отправки подарка"""
    await state.clear()
    await message.answer("❌ Отправка отменена.")