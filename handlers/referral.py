from aiogram import Router, F, Bot
from aiogram.types import Message

from database.db import get_user, get_referral_count, get_transactions
from utils.settings import get_referral_percent

router = Router()


@router.message(F.text == "👥 Рефералы")
async def referrals(message: Message, bot: Bot):
    user      = await get_user(message.from_user.id)
    ref_count = await get_referral_count(user["id"])
    ref_pct   = await get_referral_percent()

    txs        = await get_transactions(user["id"], limit=100)
    ref_earned = sum(tx["amount"] for tx in txs if tx["type"] == "referral")

    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user['referral_code']}"

    text = (
        f"👥 <b>Реферальная программа</b>\n"
        f"━━━━━━━━━━━━━━━━\n\n"
        f"💸 <b>Как работает:</b>\n"
        f"Ты получаешь <b>{ref_pct}%</b> от прибыли каждого "
        f"привлечённого тобой пользователя — автоматически и навсегда!\n\n"
        f"📊 <b>Твоя статистика:</b>\n"
        f"👤 Рефералов: <b>{ref_count}</b>\n"
        f"💰 Заработано: <b>${ref_earned:.2f}</b>\n\n"
        f"🔗 <b>Твоя реферальная ссылка:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        f"📢 Поделись ссылкой и зарабатывай пассивно!"
    )

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(
        text="📤 Поделиться ссылкой",
        switch_inline_query=f"Присоединяйся к KodoInvest и зарабатывай! {ref_link}"
    )
    builder.adjust(1)

    await message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())
