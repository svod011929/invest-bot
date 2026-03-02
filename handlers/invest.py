from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.db import get_user, create_investment, get_active_investments, add_transaction
from keyboards.kb import plans_kb, confirm_invest_kb, main_menu_kb
from utils.settings import get_plans, get_plan

router = Router()


class InvestFSM(StatesGroup):
    waiting_amount = State()


@router.message(F.text == "📈 Инвестировать")
async def show_plans(message: Message, state: FSMContext):
    await state.clear()
    user  = await get_user(message.from_user.id)
    plans = await get_plans()

    text = "📈 <b>Инвестиционные планы</b>\n━━━━━━━━━━━━━━━━\n\n"
    for plan in plans:
        total_return = plan["daily_rate"] * plan["days"]
        text += (
            f"{plan['emoji']} <b>{plan['name']}</b>\n"
            f"  💸 От ${plan['min']:.0f}\n"
            f"  📈 {plan['daily_rate']}% в день × {plan['days']} дней = <b>+{total_return:.0f}%</b>\n"
            f"  💰 Пример: ${plan['min']:.0f} → "
            f"<b>${plan['min'] * (1 + plan['daily_rate']/100 * plan['days']):.0f}</b>\n\n"
        )
    text += f"💰 <b>Твой баланс:</b> ${user['balance']:.2f}"

    from keyboards.kb import plans_kb as _plans_kb
    await message.answer(text, parse_mode="HTML", reply_markup=await _plans_kb())


@router.callback_query(F.data.startswith("plan:"))
async def select_plan(callback: CallbackQuery, state: FSMContext):
    plan_id = int(callback.data.split(":")[1])
    plan    = await get_plan(plan_id)
    if not plan:
        return await callback.answer("❌ План не найден")

    user = await get_user(callback.from_user.id)
    await state.update_data(plan_id=plan_id)
    await state.set_state(InvestFSM.waiting_amount)

    await callback.message.edit_text(
        f"{plan['emoji']} <b>Вклад «{plan['name']}»</b>\n\n"
        f"📈 Доходность: <b>{plan['daily_rate']}%/день</b> × {plan['days']} дней\n"
        f"💸 Минимальная сумма: <b>${plan['min']:.0f}</b>\n\n"
        f"💰 Твой баланс: <b>${user['balance']:.2f}</b>\n\n"
        f"✏️ Введи сумму вклада:",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(InvestFSM.waiting_amount)
async def enter_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", "."))
    except ValueError:
        return await message.answer("❌ Введи корректную сумму, например: <b>100</b>", parse_mode="HTML")

    data    = await state.get_data()
    plan    = await get_plan(data["plan_id"])
    user    = await get_user(message.from_user.id)

    if amount < plan["min"]:
        return await message.answer(
            f"❌ Минимальная сумма вклада: <b>${plan['min']:.0f}</b>", parse_mode="HTML"
        )
    if user["balance"] < amount:
        return await message.answer(
            f"❌ Недостаточно средств. Баланс: <b>${user['balance']:.2f}</b>", parse_mode="HTML"
        )

    await state.clear()
    profit = amount * (plan["daily_rate"] / 100) * plan["days"]

    await message.answer(
        f"📋 <b>Подтверждение вклада</b>\n━━━━━━━━━━━━━━━━\n"
        f"{plan['emoji']} План: <b>{plan['name']}</b>\n"
        f"💸 Сумма: <b>${amount:.2f}</b>\n"
        f"📈 Доходность: <b>{plan['daily_rate']}%/день</b> × {plan['days']} дней\n"
        f"💰 Ожидаемая прибыль: <b>+${profit:.2f}</b>\n"
        f"📤 Итого к получению: <b>${amount + profit:.2f}</b>\n\n"
        f"Подтвердить вклад?",
        parse_mode="HTML",
        reply_markup=confirm_invest_kb(plan["id"], amount)
    )


@router.callback_query(F.data.startswith("invest_confirm:"))
async def confirm_invest(callback: CallbackQuery):
    _, plan_id_str, amount_str = callback.data.split(":")
    plan_id = int(plan_id_str)
    amount  = float(amount_str)

    plan = await get_plan(plan_id)
    user = await get_user(callback.from_user.id)

    if user["balance"] < amount:
        return await callback.answer("❌ Недостаточно средств!", show_alert=True)

    inv_id = await create_investment(user["id"], plan, amount)
    await add_transaction(user["id"], "deposit", amount, comment=f"Вклад {plan['name']} #{inv_id}")

    profit = amount * (plan["daily_rate"] / 100) * plan["days"]
    await callback.message.edit_text(
        f"✅ <b>Вклад успешно открыт!</b>\n\n"
        f"{plan['emoji']} <b>{plan['name']}</b> #{inv_id}\n"
        f"💸 Вложено: <b>${amount:.2f}</b>\n"
        f"💰 Ожидаемая прибыль: <b>+${profit:.2f}</b>\n\n"
        f"📊 Прибыль начисляется каждый час.\n"
        f"🏁 Вклад завершится через <b>{plan['days']} дней</b>.",
        parse_mode="HTML"
    )
    await callback.answer("🎉 Вклад открыт!")


@router.callback_query(F.data == "back:main")
async def back_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.answer()
