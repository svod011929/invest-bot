import aiohttp
from config import config


class CryptoPay:
    def __init__(self):
        self.token = config.CRYPTO_PAY_TOKEN
        self.base_url = config.CRYPTO_PAY_API_URL
        self.headers = {"Crypto-Pay-API-Token": self.token}

    async def _request(self, method: str, **params) -> dict:
        url = f"{self.base_url}/{method}"
        # aiohttp requires str/int/float — convert bools to lowercase strings
        clean_params = {
            k: str(v).lower() if isinstance(v, bool) else v
            for k, v in params.items()
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers, params=clean_params) as resp:
                data = await resp.json()
                if not data.get("ok"):
                    raise Exception(f"CryptoPay error: {data}")
                return data["result"]

    async def create_invoice(self, amount: float, currency: str = "USDT",
                              description: str = "", payload: str = "") -> dict:
        """Create a payment invoice. Returns invoice with pay_url."""
        return await self._request(
            "createInvoice",
            asset=currency,
            amount=str(amount),
            description=description,
            payload=payload,
            paid_btn_name="callback",
            paid_btn_url="https://t.me/your_bot",  # replace with your bot link
            allow_comments=False,
            allow_anonymous=False,
        )

    async def get_invoice(self, invoice_id: int) -> dict:
        """Check invoice status."""
        result = await self._request("getInvoices", invoice_ids=str(invoice_id))
        items = result.get("items", [])
        return items[0] if items else None

    async def check_paid(self, invoice_id: int) -> bool:
        invoice = await self.get_invoice(invoice_id)
        return invoice and invoice.get("status") == "paid"

    async def transfer(self, user_id: int, asset: str, amount: float, spend_id: str, comment: str = "") -> dict:
        """
        Send crypto directly to a Telegram user via CryptoPay.
        user_id — Telegram user ID (must have started @CryptoBot).
        spend_id — unique string to prevent duplicate transfers.
        """
        return await self._request(
            "transfer",
            user_id=str(user_id),
            asset=asset,
            amount=str(amount),
            spend_id=spend_id,
            comment=comment,
            disable_send_notification="false",
        )

    async def get_balance(self) -> list:
        return await self._request("getBalance")


crypto_pay = CryptoPay()
