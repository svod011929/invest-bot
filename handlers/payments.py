import aiosqlite
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.db import get_user, add_transaction
from keyboards.kb import crypto_currency_kb, pay_invoice_kb
from utils.cryptopay import crypto_pay
from config import config

router = Router()


class DepositFSM(StatesGroup):
    waiting_amount = State()


# ─────────────────────────────────────────────────────────────
#  DEPOSIT ENTRY
# ─────────────────────────────────────────────────────────────

@router.message(F.text == "💳 Пополнить")
async def deposit_menu(message: Message, state: FSMContext):
    await state.clear()
    user = await get_user(message.from_user.id)
    await message.answer(
        f"💳 <b>Пополнение баланса</b>\n\n"
        f"💰 Текущий баланс: <b>${user['balance']:.2f}</b>\n\n"
        f"Выбери валюту:",
        parse_mode="HTML",
        reply_markup=crypto_currency_kb()
    )


# ─────────────────────────────────────────────────────────────
#  SELECT CURRENCY → ENTER AMOUNT
# ─────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("crypto_cur:"))
async def crypto_select_currency(callback: CallbackQuery, state: FSMContext):
    currency = callback.data.split(":")[1]
    await state.update_data(currency=currency)
    await state.set_state(DepositFSM.waiting_amount)

    await callback.message.edit_text(
        f"₿ <b>Пополнение через CryptoPay</b>\n\n"
        f"Валюта: <b>{currency}</b>\n"
        f"Минимальная сумма: <b>$5</b>\n\n"
        f"✏️ Введи сумму в USDT (эквивалент):",
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "deposit:back")
async def deposit_back(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user = await get_user(callback.from_user.id)
    await callback.message.edit_text(
        f"💳 <b>Пополнение баланса</b>\n\n"
        f"💰 Текущий баланс: <b>${user['balance']:.2f}</b>\n\n"
        f"Выбери валюту:",
        parse_mode="HTML",
        reply_markup=crypto_currency_kb()
    )
    await callback.answer()


# ─────────────────────────────────────────────────────────────
#  CREATE INVOICE
# ─────────────────────────────────────────────────────────────

@router.message(DepositFSM.waiting_amount)
async def process_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
    except ValueError:
        return await message.answer("❌ Введи корректную сумму, например: <b>20</b>", parse_mode="HTML")

    if amount < 5:
        return await message.answer("❌ Минимальная сумма пополнения: <b>$5</b>", parse_mode="HTML")

    data     = await state.get_data()
    currency = data.get("currency", "USDT")
    user     = await get_user(message.from_user.id)
    await state.clear()

    try:
        invoice = await crypto_pay.create_invoice(
            amount=amount,
            currency=currency,
            description=f"Пополнение KodoInvest — ${amount}",
            payload=f"deposit:{user['id']}:{amount}"
        )
    except Exception as e:
        err = str(e).replace("<", "‹").replace(">", "›")
        return await message.answer(f"❌ Ошибка создания счёта:\n<code>{err}</code>", parse_mode="HTML")

    invoice_id = invoice["invoice_id"]
    pay_url    = invoice["pay_url"]

    await add_transaction(
        user["id"], "deposit", amount, currency=currency,
        invoice_id=str(invoice_id), status="pending",
        comment=f"CryptoPay {currency}"
    )

    await message.answer(
        f"📄 <b>Счёт создан!</b>\n\n"
        f"💰 Сумма: <b>${amount} ({currency})</b>\n"
        f"🔢 Номер: <code>{invoice_id}</code>\n\n"
        f"Нажми <b>«Оплатить»</b>, затем <b>«Я оплатил»</b>:",
        parse_mode="HTML",
        reply_markup=pay_invoice_kb(pay_url, invoice_id)
    )


# ─────────────────────────────────────────────────────────────
#  CHECK PAYMENT
# ─────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("check_payment:"))
async def check_payment(callback: CallbackQuery):
    invoice_id = int(callback.data.split(":")[1])
    user = await get_user(callback.from_user.id)

    try:
        paid = await crypto_pay.check_paid(invoice_id)
    except Exception:
        return await callback.answer("❌ Ошибка проверки. Попробуй позже.", show_alert=True)

    if not paid:
        return await callback.answer("⏳ Платёж ещё не подтверждён. Подожди немного.", show_alert=True)

    async with aiosqlite.connect(config.DB_PATH) as db:
        async with db.execute(
            "SELECT * FROM transactions WHERE invoice_id = ? AND status = 'completed'",
            (str(invoice_id),)
        ) as cur:
            if await cur.fetchone():
                return await callback.answer("✅ Платёж уже зачислен!", show_alert=True)

        async with db.execute(
            "SELECT * FROM transactions WHERE invoice_id = ? AND status = 'pending'",
            (str(invoice_id),)
        ) as cur:
            tx = await cur.fetchone()

        if not tx:
            return await callback.answer("❌ Транзакция не найдена.", show_alert=True)

        amount = tx[3]
        await db.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, user["id"]))
        await db.execute("UPDATE transactions SET status = 'completed' WHERE invoice_id = ?", (str(invoice_id),))
        await db.commit()

    await callback.message.edit_text(
        f"✅ <b>Баланс пополнен!</b>\n\n"
        f"💰 <b>+${amount:.2f}</b> зачислено на твой счёт.\n"
        f"Теперь можешь открыть вклад 📈",
        parse_mode="HTML"
    )
    await callback.answer("💸 Зачислено!")
