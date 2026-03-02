from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from config import config


# ─────────────────────────────────────────────────────────────
#  MAIN MENU (Reply)
# ─────────────────────────────────────────────────────────────

def main_menu_kb() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="💼 Мой профиль"),
        KeyboardButton(text="📈 Инвестировать"),
    )
    builder.row(
        KeyboardButton(text="🎰 Игры"),
        KeyboardButton(text="👥 Рефералы"),
    )
    builder.row(
        KeyboardButton(text="💳 Пополнить"),
        KeyboardButton(text="📤 Вывести"),
    )
    builder.row(
        KeyboardButton(text="📊 История"),
    )
    return builder.as_markup(resize_keyboard=True)


# ─────────────────────────────────────────────────────────────
#  INVEST PLANS
# ─────────────────────────────────────────────────────────────

async def plans_kb() -> InlineKeyboardMarkup:
    from utils.settings import get_plans
    plans = await get_plans()
    builder = InlineKeyboardBuilder()
    for plan in plans:
        builder.button(
            text=f"{plan['emoji']} {plan['name']} — {plan['daily_rate']}%/день",
            callback_data=f"plan:{plan['id']}"
        )
    builder.button(text="🔙 Назад", callback_data="back:main")
    builder.adjust(1)
    return builder.as_markup()


def confirm_invest_kb(plan_id: int, amount: float) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data=f"invest_confirm:{plan_id}:{amount}")
    builder.button(text="❌ Отмена", callback_data="back:main")
    builder.adjust(2)
    return builder.as_markup()


# ─────────────────────────────────────────────────────────────
#  DEPOSIT
# ─────────────────────────────────────────────────────────────

def crypto_currency_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cur in ["USDT", "TON", "BTC", "ETH", "LTC"]:
        builder.button(text=cur, callback_data=f"crypto_cur:{cur}")
    builder.button(text="🔙 Назад", callback_data="back:main")
    builder.adjust(3, 2, 1)
    return builder.as_markup()


def pay_invoice_kb(pay_url: str, invoice_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="💸 Оплатить", url=pay_url)
    builder.button(text="✅ Я оплатил", callback_data=f"check_payment:{invoice_id}")
    builder.button(text="❌ Отмена", callback_data="back:main")
    builder.adjust(1)
    return builder.as_markup()


# ─────────────────────────────────────────────────────────────
#  GAMES
# ─────────────────────────────────────────────────────────────

def games_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🪙 Орёл или Решка", callback_data="game:coin_flip")
    builder.button(text="🎲 Кости",           callback_data="game:dice")
    builder.button(text="💣 Шахты",            callback_data="game:mines")
    builder.button(text="🔙 Назад",            callback_data="back:main")
    builder.adjust(2, 1, 1)
    return builder.as_markup()


def coin_flip_choice_kb(bet: float) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🦅 Орёл", callback_data=f"coin:{bet}:heads")
    builder.button(text="🪙 Решка", callback_data=f"coin:{bet}:tails")
    builder.button(text="❌ Отмена", callback_data="back:main")
    builder.adjust(2, 1)
    return builder.as_markup()


# ─────────────────────────────────────────────────────────────
#  ADMIN
# ─────────────────────────────────────────────────────────────

def admin_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Статистика",          callback_data="admin:stats")
    builder.button(text="👤 Найти пользователя",  callback_data="admin:find_user")
    builder.button(text="📢 Рассылка",             callback_data="admin:broadcast")
    builder.button(text="⚙️ Настройки",           callback_data="admin:settings")
    builder.adjust(2)
    return builder.as_markup()
