import aiosqlite
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.db import get_user, add_transaction
from utils.cryptopay import crypto_pay
from utils.settings import get_withdraw_settings
from config import config

router = Router()

WITHDRAW_CURRENCIES = ["USDT", "TON", "BTC", "ETH", "LTC"]


class WithdrawFSM(StatesGroup):
    choose_currency = State()
    enter_amount    = State()
    confirm         = State()


# ─────────────────────────────────────────────────────────────
#  ENTRY
# ─────────────────────────────────────────────────────────────

@router.message(F.text == "📤 Вывести")
async def withdraw_start(message: Message, state: FSMContext):
    await state.clear()
    user = await get_user(message.from_user.id)
    cfg  = await get_withdraw_settings()

    if user["balance"] < cfg["min"]:
        return await message.answer(
            f"❌ Минимальная сумма вывода: <b>${cfg['min']}</b>\n"
            f"Твой баланс: <b>${user['balance']:.2f}</b>",
            parse_mode="HTML"
        )

    builder = InlineKeyboardBuilder()
    for cur in WITHDRAW_CURRENCIES:
        builder.button(text=cur, callback_data=f"wd_cur:{cur}")
    builder.button(text="❌ Отмена", callback_data="wd_cancel")
    builder.adjust(3, 2, 1)

    await state.set_state(WithdrawFSM.choose_currency)
    await message.answer(
        f"📤 <b>Вывод через CryptoPay</b>\n\n"
        f"💰 Доступно: <b>${user['balance']:.2f}</b>\n"
        f"📊 Комиссия: <b>{cfg['fee_percent']}%</b>\n"
        f"💵 Минимум: <b>${cfg['min']}</b>\n\n"
        f"⚠️ Для получения средств у тебя должен быть запущен "
        f"<a href='https://t.me/CryptoBot'>@CryptoBot</a>\n\n"
        f"Выбери валюту:",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )


# ─────────────────────────────────────────────────────────────
#  CHOOSE CURRENCY → ENTER AMOUNT
# ─────────────────────────────────────────────────────────────

@router.callback_query(WithdrawFSM.choose_currency, F.data.startswith("wd_cur:"))
async def wd_choose_currency(callback: CallbackQuery, state: FSMContext):
    currency = callback.data.split(":")[1]
    await state.update_data(currency=currency)
    await state.set_state(WithdrawFSM.enter_amount)

    user = await get_user(callback.from_user.id)
    cfg  = await get_withdraw_settings()

    await callback.message.edit_text(
        f"📤 Вывод в <b>{currency}</b>\n\n"
        f"💰 Доступно: <b>${user['balance']:.2f}</b>\n"
        f"💵 Минимум: <b>${cfg['min']}</b>\n\n"
        f"✏️ Введи сумму для вывода (в USDT-эквиваленте):",
        parse_mode="HTML"
    )
    await callback.answer()


# ─────────────────────────────────────────────────────────────
#  ENTER AMOUNT
# ─────────────────────────────────────────────────────────────

@router.message(WithdrawFSM.enter_amount)
async def wd_enter_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
    except ValueError:
        return await message.answer("❌ Введи корректное число, например: <b>50</b>", parse_mode="HTML")

    user = await get_user(message.from_user.id)
    cfg  = await get_withdraw_settings()

    if amount < cfg["min"]:
        return await message.answer(f"❌ Минимальная сумма: <b>${cfg['min']}</b>", parse_mode="HTML")
    if amount > user["balance"]:
        return await message.answer(
            f"❌ Недостаточно средств. Доступно: <b>${user['balance']:.2f}</b>", parse_mode="HTML"
        )

    fee = round(amount * cfg["fee_percent"] / 100, 4)
    net = round(amount - fee, 4)
    await state.update_data(amount=amount, fee=fee, net=net)
    await state.set_state(WithdrawFSM.confirm)

    data = await state.get_data()

    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data="wd_confirm")
    builder.button(text="❌ Отмена",      callback_data="wd_cancel")
    builder.adjust(2)

    await message.answer(
        f"📋 <b>Подтверждение вывода</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🔗 Валюта: <b>{data['currency']}</b>\n"
        f"💵 Сумма: <b>${amount:.2f}</b>\n"
        f"📊 Комиссия ({cfg['fee_percent']}%): <b>-${fee:.4f}</b>\n"
        f"💰 К получению: <b>${net:.4f}</b>\n\n"
        f"⚡ Перевод выполняется автоматически через CryptoPay.",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )


# ─────────────────────────────────────────────────────────────
#  CONFIRM → TRANSFER
# ─────────────────────────────────────────────────────────────

@router.callback_query(WithdrawFSM.confirm, F.data == "wd_confirm")
async def wd_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    user = await get_user(callback.from_user.id)

    if user["balance"] < data["amount"]:
        return await callback.answer("❌ Недостаточно средств!", show_alert=True)

    # Freeze balance before transfer attempt
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "UPDATE users SET balance = balance - ? WHERE id = ?",
            (data["amount"], user["id"])
        )
        await db.commit()

    spend_id = f"wd_{user['id']}_{int(__import__('time').time())}"

    try:
        await crypto_pay.transfer(
            user_id=user["telegram_id"],
            asset=data["currency"],
            amount=data["net"],
            spend_id=spend_id,
            comment="Вывод с KodoInvest"
        )
    except Exception as e:
        # Rollback balance on failure
        async with aiosqlite.connect(config.DB_PATH) as db:
            await db.execute(
                "UPDATE users SET balance = balance + ? WHERE id = ?",
                (data["amount"], user["id"])
            )
            await db.commit()

        err = str(e).replace("<", "‹").replace(">", "›")
        return await callback.message.edit_text(
            f"❌ <b>Ошибка вывода</b>\n\n"
            f"<code>{err}</code>\n\n"
            f"Баланс возвращён. Убедись, что запустил "
            f"<a href='https://t.me/CryptoBot'>@CryptoBot</a>.",
            parse_mode="HTML"
        )

    # Log successful withdrawal
    await add_transaction(
        user["id"], "withdraw", data["amount"],
        comment=f"CryptoPay Transfer → {data['currency']} (spend_id: {spend_id})"
    )

    await callback.message.edit_text(
        f"✅ <b>Вывод выполнен!</b>\n\n"
        f"💰 <b>${data['net']:.4f} {data['currency']}</b> отправлено в @CryptoBot.\n"
        f"Деньги уже у тебя в кошельке 🎉",
        parse_mode="HTML"
    )
    await callback.answer("💸 Переведено!")


# ─────────────────────────────────────────────────────────────
#  CANCEL
# ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "wd_cancel")
async def wd_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Вывод отменён.")
    await callback.answer()
