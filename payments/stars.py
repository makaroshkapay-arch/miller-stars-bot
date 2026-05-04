from aiogram.types import LabeledPrice, PreCheckoutQuery
from aiogram import Bot

class StarsPayment:
    @staticmethod
    async def create_stars_invoice(
        bot: Bot,
        chat_id: int,
        amount: int,
        description: str,
        payload: str
    ) -> bool:
        """Создает инвойс в звездах Telegram"""
        try:
            price = LabeledPrice(label=description, amount=amount)
            await bot.send_invoice(
                chat_id=chat_id,
                title="Оплата звездами",
                description=description,
                payload=payload,
                provider_token="",  # Пустой для нативных звезд
                currency="XTR",
                prices=[price]
            )
            return True
        except Exception as e:
            print(f"Error creating stars invoice: {e}")
            return False

    @staticmethod
    async def accept_pre_checkout(pre_checkout_query: PreCheckoutQuery):
        """Подтверждение pre-checkout запроса"""
        await pre_checkout_query.answer(ok=True)