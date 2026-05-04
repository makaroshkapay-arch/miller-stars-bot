import aiohttp
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class CryptoBotAPI:
    def __init__(self, token: str, timeout: int = 30):
        self.token = token
        self.base_url = "https://pay.crypt.bot"
        self.headers = {"Crypto-Pay-API-Token": token}
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _request(self, method: str, endpoint: str, **kwargs) -> Optional[dict]:
        session = await self._get_session()
        url = f"{self.base_url}/{endpoint}"
        
        try:
            async with session.request(method, url, headers=self.headers, **kwargs) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get("ok"):
                        return result.get("result")
                    else:
                        logger.error(f"API error: {result}")
                        return None
                else:
                    error_text = await response.text()
                    logger.error(f"HTTP {response.status}: {error_text}")
                    return None
        except aiohttp.ClientError as e:
            logger.error(f"Request failed: {e}")
            return None

    async def create_invoice(
        self,
        asset: str = "USDT",
        amount: float = 0,
        description: str = "",
        hidden_message: str = "",
        paid_btn_name: str = "openBot",
        paid_btn_url: str = "https://t.me/miller_starsbot",
        payload: str = None,
        allow_comments: bool = False,
        allow_anonymous: bool = True,
        expires_in: int = 3600
    ) -> Optional[dict]:
        data = {
            "asset": asset,
            "amount": str(amount),
            "description": description,
            "hidden_message": hidden_message,
            "paid_btn_name": paid_btn_name,
            "paid_btn_url": paid_btn_url,
            "allow_comments": allow_comments,
            "allow_anonymous": allow_anonymous,
            "expires_in": expires_in
        }
        if payload:
            data["payload"] = payload
        return await self._request("POST", "api/createInvoice", json=data)

    async def get_invoice(self, invoice_id: int) -> Optional[dict]:
        """Получение информации о счете"""
        data = {"invoice_ids": str(invoice_id)}
        result = await self._request("POST", "api/getInvoices", json=data)
        if result and "items" in result and len(result["items"]) > 0:
            return result["items"][0]
        return None

    async def transfer(
        self,
        user_id: int,
        asset: str,
        amount: float,
        spend_id: str
    ) -> Optional[dict]:
        data = {
            "user_id": user_id,
            "asset": asset,
            "amount": str(amount),
            "spend_id": spend_id
        }
        return await self._request("POST", "api/transfer", json=data)