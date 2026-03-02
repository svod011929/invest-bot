from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command

from database.db import get_or_create_user, get_user, get_rank, get_referral_count, can_claim_bonus, claim_bonus
from database.db import add_transaction, get_active_investments
from keyboards.kb import main_menu_kb
from config import config

router = Router()


# ─────────────────────────────────────────────────────────────
#  /start
# ─────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message):
    args = message.text.split()[1] if len(message.text.split()) > 1 else None

    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        ref_code=args,
    )

    rank = await get_rank(user["total_invested"])
    is_new = user["total_invested"] == 0 and user["balance"] == 0

    if is_new:
        welcome = (
            f"👋 Добро пожаловать, <b>{message.from_user.first_name}</b>!\n\n"
            f"🚀 <b>KodoInvest</b> — платформа, где твои деньги работают на тебя.\n\n"
            f"💡 <b>Как это работает:</b>\n"
            f"  1️⃣ Пополни баланс через CryptoPay или Stars\n"
            f"  2️⃣ Выбери инвестиционный план\n"
            f"  3️⃣ Получай прибыль каждый день\n"
            f"  4️⃣ Приглашай друзей и зарабатывай ещё\n\n"
            f"🎁 <b>Твой стартовый ранг:</b> {rank['emoji']} {rank['name']}\n"
            f"🔑 <b>Твой реф. код:</b> <code>{user['referral_code']}</code>"
        )
    else:
        welcome = (
            f"👋 С возвращением, <b>{message.from_user.first_name}</b>!\n\n"
            f"{rank['emoji']} Ранг: <b>{rank['name']}</b>\n"
            f"💰 Баланс: <b>${user['balance']:.2f}</b>"
        )

    await message.answer(welcome, parse_mode="HTML", reply_markup=main_menu_kb())


# ─────────────────────────────────────────────────────────────
#  PROFILE
# ─────────────────────────────────────────────────────────────

@router.message(F.text == "💼 Мой профиль")
async def profile(message: Message):
    user = await get_user(message.from_user.id)
    if not user:
        return await message.answer("Сначала нажми /start")

    rank = await get_rank(user["total_invested"])
    ref_count = await get_referral_count(user["id"])
    active_invs = await get_active_investments(user["id"])

    # Count unrealized profit across active investments
    unrealized = sum(inv["earned"] for inv in active_invs)

    # Next rank info
    ranks = config.RANKS
    current_rank_idx = next((i for i, r in enumerate(ranks) if r["name"] == rank["name"]), 0)
    next_rank = ranks[current_rank_idx + 1] if current_rank_idx + 1 < len(ranks) else None
    next_rank_text = (
        f"\n📈 До ранга <b>{next_rank['emoji']} {next_rank['name']}</b>: "
        f"<b>${next_rank['min'] - user['total_invested']:.0f}</b> инвестиций"
    ) if next_rank and user["total_invested"] < next_rank["min"] else "\n🏆 Максимальный ранг достигнут!"

    text = (
        f"👤 <b>Профиль</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🎖 Ранг: {rank['emoji']} <b>{rank['name']}</b>{next_rank_text}\n\n"
        f"💰 Баланс: <b>${user['balance']:.2f}</b>\n"
        f"📊 В работе: <b>${sum(i['amount'] for i in active_invs):.2f}</b> ({len(active_invs)} вкладов)\n"
        f"💹 Накоплено: <b>${unrealized:.4f}</b>\n\n"
        f"📥 Всего вложено: <b>${user['total_invested']:.2f}</b>\n"
        f"📤 Всего заработано: <b>${user['total_earned']:.2f}</b>\n\n"
        f"👥 Рефералов: <b>{ref_count}</b>\n"
        f"🔗 Реф. код: <code>{user['referral_code']}</code>\n"
    )

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    notify_on = user.get("notify_enabled", 1)
    builder = InlineKeyboardBuilder()
    builder.button(text="🎁 Забрать дневной бонус", callback_data="claim_bonus")
    builder.button(
        text=f"🔔 Уведомления: {'вкл' if notify_on else 'выкл'}",
        callback_data="toggle_notify"
    )
    builder.adjust(1)

    await message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())


# ─────────────────────────────────────────────────────────────
#  DAILY BONUS
# ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "claim_bonus")
async def cb_claim_bonus(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    can = await can_claim_bonus(user["id"])

    if not can:
        return await callback.answer("⏳ Бонус уже получен сегодня! Приходи завтра.", show_alert=True)

    # Bonus grows with rank
    from utils.settings import get_daily_bonus
    rank     = await get_rank(user["total_invested"])
    ranks    = config.RANKS
    rank_idx = next((i for i, r in enumerate(ranks) if r["name"] == rank["name"]), 0)
    base     = await get_daily_bonus()
    bonus    = round(base * (1 + rank_idx * 0.5), 4)

    await claim_bonus(user["id"], bonus)
    await add_transaction(user["id"], "bonus", bonus, comment="Ежедневный бонус")

    await callback.answer(f"🎁 +${bonus:.2f} добавлено на баланс!", show_alert=True)
    await callback.message.edit_reply_markup(reply_markup=None)


# ─────────────────────────────────────────────────────────────
#  TOGGLE NOTIFICATIONS
# ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "toggle_notify")
async def cb_toggle_notify(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    from database.db import set_notify
    current = user.get("notify_enabled", 1)
    new_state = not bool(current)
    await set_notify(user["id"], new_state)

    status = "включены 🔔" if new_state else "выключены 🔕"
    await callback.answer(f"Уведомления {status}", show_alert=True)


# ─────────────────────────────────────────────────────────────
#  HISTORY
# ─────────────────────────────────────────────────────────────

@router.message(F.text == "📊 История")
async def history(message: Message):
    user = await get_user(message.from_user.id)
    from database.db import get_transactions, get_investment_history
    txs = await get_transactions(user["id"], limit=10)
    invs = await get_investment_history(user["id"], limit=5)

    TYPE_EMOJI = {
        "deposit": "📥", "withdraw": "📤", "profit": "💰",
        "referral": "👥", "bonus": "🎁", "game": "🎰"
    }

    if not txs:
        return await message.answer("📭 История пуста.")

    lines = ["📊 <b>Последние транзакции</b>\n"]
    for tx in txs:
        emoji = TYPE_EMOJI.get(tx["type"], "•")
        sign = "+" if tx["type"] != "withdraw" else "-"
        lines.append(
            f"{emoji} {sign}${tx['amount']:.2f} — {tx['type']} "
            f"<i>({tx['created_at'][:10]})</i>"
        )

    await message.answer("\n".join(lines), parse_mode="HTML")
