from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from typing import Callable, Dict, Any, Awaitable
import aiosqlite


class BanMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = None
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user

        if user:
            async with aiosqlite.connect("invest_bot.db") as db:
                async with db.execute(
                    "SELECT is_banned FROM users WHERE telegram_id = ?", (user.id,)
                ) as cur:
                    row = await cur.fetchone()
                    if row and row[0]:
                        if isinstance(event, Message):
                            await event.answer("🚫 Ваш аккаунт заблокирован.")
                        elif isinstance(event, CallbackQuery):
                            await event.answer("🚫 Аккаунт заблокирован.", show_alert=True)
                        return

        return await handler(event, data)
