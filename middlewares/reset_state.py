from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message
from aiogram.fsm.context import FSMContext
from typing import Callable, Dict, Any, Awaitable

# Все кнопки главного меню — при нажатии любой из них FSM сбрасывается
MENU_BUTTONS = {
    "💼 Мой профиль",
    "📈 Инвестировать",
    "🎰 Игры",
    "👥 Рефералы",
    "💳 Пополнить",
    "📤 Вывести",
    "📊 История",
}


class ResetStateMiddleware(BaseMiddleware):
    """
    Сбрасывает FSM-состояние если пользователь нажал кнопку главного меню.
    Это предотвращает ситуацию когда бот «застрял» в ожидании ввода
    и интерпретирует нажатие меню как некорректный ввод.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if isinstance(event, Message) and (
            event.text in MENU_BUTTONS or
            (event.text and event.text.startswith("/start"))
        ):
            state: FSMContext = data.get("state")
            if state:
                current = await state.get_state()
                if current is not None:
                    await state.clear()

        return await handler(event, data)
