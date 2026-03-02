import random
import json
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.db import get_user, save_game, log_game, create_mines_session, get_active_mines_session, update_mines_session
from keyboards.kb import games_menu_kb, coin_flip_choice_kb
from utils.settings import get_coin_settings, get_dice_settings, get_mines_settings
from config import config

router = Router()


class GameFSM(StatesGroup):
    coin_bet    = State()
    dice_bet    = State()
    dice_mode   = State()
    dice_pick   = State()
    mines_bet   = State()
    mines_count = State()


# ═════════════════════════════════════════════════════════════
#  GAMES MENU
# ═════════════════════════════════════════════════════════════

@router.message(F.text == "🎰 Игры")
async def games_menu(message: Message, state: FSMContext):
    await state.clear()
    user = await get_user(message.from_user.id)
    await message.answer(
        f"🎰 <b>Игровой зал</b>\n\n"
        f"💰 Твой баланс: <b>${user['balance']:.2f}</b>\n\n"
        f"Испытай удачу — все выигрыши мгновенно!",
        parse_mode="HTML",
        reply_markup=games_menu_kb()
    )


@router.callback_query(F.data == "games:menu")
async def games_menu_cb(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user = await get_user(callback.from_user.id)
    await callback.message.edit_text(
        f"🎰 <b>Игровой зал</b>\n\n💰 Баланс: <b>${user['balance']:.2f}</b>",
        parse_mode="HTML",
        reply_markup=games_menu_kb()
    )
    await callback.answer()


# ═════════════════════════════════════════════════════════════
#  🪙  COIN FLIP
# ═════════════════════════════════════════════════════════════

@router.callback_query(F.data == "game:coin_flip")
async def coin_flip_start(callback: CallbackQuery, state: FSMContext):
    user = await get_user(callback.from_user.id)
    cfg  = await get_coin_settings()
    await state.set_state(GameFSM.coin_bet)
    await callback.message.edit_text(
        f"🪙 <b>Орёл или Решка</b>\n\n"
        f"🎲 Победа: <b>×{cfg['mult']}</b>\n"
        f"💸 Ставки: <b>${cfg['min_bet']} – ${cfg['max_bet']}</b>\n"
        f"💰 Баланс: <b>${user['balance']:.2f}</b>\n\n✏️ Введи ставку:",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(GameFSM.coin_bet)
async def coin_bet(message: Message, state: FSMContext):
    try:
        bet = float(message.text.replace(",", "."))
    except ValueError:
        return await message.answer("❌ Введи число, например: <b>10</b>", parse_mode="HTML")

    user = await get_user(message.from_user.id)
    cfg  = await get_coin_settings()

    if bet < cfg["min_bet"] or bet > cfg["max_bet"]:
        return await message.answer(
            f"❌ Ставка: ${cfg['min_bet']}–${cfg['max_bet']}", parse_mode="HTML"
        )
    if user["balance"] < bet:
        return await message.answer(f"❌ Баланс: <b>${user['balance']:.2f}</b>", parse_mode="HTML")

    await state.clear()
    await message.answer(
        f"🪙 Ставка <b>${bet:.2f}</b> — выбери сторону:",
        parse_mode="HTML",
        reply_markup=coin_flip_choice_kb(bet)
    )


@router.callback_query(F.data.startswith("coin:"))
async def coin_result(callback: CallbackQuery):
    _, bet_str, choice = callback.data.split(":")
    try:
        bet = float(bet_str)
    except ValueError:
        return await callback.answer("❌ Некорректная ставка", show_alert=True)

    user = await get_user(callback.from_user.id)
    cfg  = await get_coin_settings()

    # Server-side validation (callback_data could be forged)
    if bet < cfg["min_bet"] or bet > cfg["max_bet"]:
        return await callback.answer("❌ Ставка вне допустимого диапазона", show_alert=True)

    result = random.choice(["heads", "tails"])
    win    = result == choice
    profit = round(bet * cfg["mult"], 4) if win else 0

    game = await save_game(user["id"], "coin_flip", bet, choice, result, win, profit)
    if game is None:
        return await callback.answer("❌ Недостаточно средств!", show_alert=True)

    updated = await get_user(callback.from_user.id)
    r_emoji = "🦅" if result == "heads" else "🪙"
    c_name  = "Орёл" if choice == "heads" else "Решка"
    r_name  = "Орёл" if result == "heads" else "Решка"

    if win:
        text = (f"🪙 Ты: <b>{c_name}</b>\nВыпало: {r_emoji} <b>{r_name}</b>\n\n"
                f"🎉 <b>ПОБЕДА! +${profit:.2f}</b>\n💼 Баланс: <b>${updated['balance']:.2f}</b>")
    else:
        text = (f"🪙 Ты: <b>{c_name}</b>\nВыпало: {r_emoji} <b>{r_name}</b>\n\n"
                f"😔 Не повезло. <b>-${bet:.2f}</b>\n💼 Баланс: <b>${updated['balance']:.2f}</b>")

    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Ещё раз", callback_data="game:coin_flip")
    builder.button(text="🔙 Игры",    callback_data="games:menu")
    builder.adjust(2)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()


# ═════════════════════════════════════════════════════════════
#  🎲  DICE
# ═════════════════════════════════════════════════════════════

@router.callback_query(F.data == "game:dice")
async def dice_start(callback: CallbackQuery, state: FSMContext):
    user = await get_user(callback.from_user.id)
    cfg  = await get_dice_settings()
    await state.set_state(GameFSM.dice_bet)
    await callback.message.edit_text(
        f"🎲 <b>Кости</b>\n\n"
        f"🎯 Угадать точное число → <b>×{cfg['exact_mult']}</b>\n"
        f"⬆️ Высокое (4–6) → <b>×{cfg['hl_mult']}</b>\n"
        f"⬇️ Низкое (1–3) → <b>×{cfg['hl_mult']}</b>\n\n"
        f"💸 Ставки: <b>${cfg['min_bet']} – ${cfg['max_bet']}</b>\n"
        f"💰 Баланс: <b>${user['balance']:.2f}</b>\n\n✏️ Введи ставку:",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(GameFSM.dice_bet)
async def dice_bet_entered(message: Message, state: FSMContext):
    try:
        bet = float(message.text.replace(",", "."))
    except ValueError:
        return await message.answer("❌ Введи число, например: <b>10</b>", parse_mode="HTML")

    user = await get_user(message.from_user.id)
    cfg  = await get_dice_settings()

    if bet < cfg["min_bet"] or bet > cfg["max_bet"]:
        return await message.answer(
            f"❌ Ставка: ${cfg['min_bet']}–${cfg['max_bet']}", parse_mode="HTML"
        )
    if user["balance"] < bet:
        return await message.answer(f"❌ Баланс: <b>${user['balance']:.2f}</b>", parse_mode="HTML")

    await state.update_data(bet=bet)
    await state.set_state(GameFSM.dice_mode)

    cfg = await get_dice_settings()
    builder = InlineKeyboardBuilder()
    builder.button(text=f"🎯 Точное (×{cfg['exact_mult']})", callback_data="dice_mode:exact")
    builder.button(text=f"⬆️ Высокое 4-6 (×{cfg['hl_mult']})", callback_data="dice_mode:high")
    builder.button(text=f"⬇️ Низкое 1-3 (×{cfg['hl_mult']})",  callback_data="dice_mode:low")
    builder.button(text="❌ Отмена", callback_data="games:menu")
    builder.adjust(1)

    await message.answer(
        f"🎲 Ставка: <b>${bet:.2f}</b>\n\nВыбери режим:",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )


@router.callback_query(GameFSM.dice_mode, F.data.startswith("dice_mode:"))
async def dice_mode_selected(callback: CallbackQuery, state: FSMContext):
    mode = callback.data.split(":")[1]
    data = await state.get_data()
    await state.update_data(mode=mode)

    if mode == "exact":
        await state.set_state(GameFSM.dice_pick)
        builder = InlineKeyboardBuilder()
        for n in range(1, 7):
            builder.button(text="⚀⚁⚂⚃⚄⚅"[n-1], callback_data=f"dice_pick:{n}")
        builder.adjust(3)
        cfg = await get_dice_settings()
        await callback.message.edit_text(
            f"🎯 Ставка: <b>${data['bet']:.2f}</b> × {cfg['exact_mult']}\n\nВыбери число (1–6):",
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
    else:
        await state.clear()
        await _roll_dice(callback, data["bet"], mode, None)

    await callback.answer()


@router.callback_query(GameFSM.dice_pick, F.data.startswith("dice_pick:"))
async def dice_pick_number(callback: CallbackQuery, state: FSMContext):
    pick = int(callback.data.split(":")[1])
    data = await state.get_data()
    await state.clear()
    await _roll_dice(callback, data["bet"], "exact", pick)
    await callback.answer()


async def _roll_dice(callback: CallbackQuery, bet: float, mode: str, pick: int | None):
    user = await get_user(callback.from_user.id)
    cfg  = await get_dice_settings()

    if user["balance"] < bet:
        return await callback.answer("❌ Недостаточно средств!", show_alert=True)

    rolled = random.randint(1, 6)
    face   = "⚀⚁⚂⚃⚄⚅"[rolled - 1]

    if mode == "exact":
        win  = rolled == pick
        mult = cfg["exact_mult"]
        mode_text = f"🎯 Ставил на <b>{pick}</b>"
    elif mode == "high":
        win  = rolled >= 4
        mult = cfg["hl_mult"]
        mode_text = "⬆️ Ставил на <b>высокое (4–6)</b>"
    else:
        win  = rolled <= 3
        mult = cfg["hl_mult"]
        mode_text = "⬇️ Ставил на <b>низкое (1–3)</b>"

    profit = round(bet * mult, 4) if win else 0
    game = await save_game(user["id"], "dice", bet, str(pick or mode), str(rolled), win, profit)
    if game is None:
        return await callback.answer("❌ Недостаточно средств!", show_alert=True)
    updated = await get_user(callback.from_user.id)

    if win:
        text = (f"🎲 {mode_text}\n{face} Выпало: <b>{rolled}</b>\n\n"
                f"🎉 <b>ПОБЕДА! +${profit:.2f}</b> (×{mult})\n💼 Баланс: <b>${updated['balance']:.2f}</b>")
    else:
        text = (f"🎲 {mode_text}\n{face} Выпало: <b>{rolled}</b>\n\n"
                f"😔 Не повезло. <b>-${bet:.2f}</b>\n💼 Баланс: <b>${updated['balance']:.2f}</b>")

    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Ещё раз", callback_data="game:dice")
    builder.button(text="🔙 Игры",    callback_data="games:menu")
    builder.adjust(2)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())


# ═════════════════════════════════════════════════════════════
#  💣  MINES
# ═════════════════════════════════════════════════════════════

def _calc_mult(mines: int, safe_opened: int, grid: int = 25) -> float:
    if safe_opened == 0:
        return 1.0
    prob = 1.0
    remaining = grid
    for _ in range(safe_opened):
        prob *= (remaining - mines) / remaining
        remaining -= 1
    mult = config.MINES_HOUSE_EDGE / prob if prob > 0 else 1.0
    return round(min(mult, 500.0), 2)


def _build_board_markup(session: dict, reveal_mine: int = None):
    grid = config.MINES_GRID
    size = 5
    board    = json.loads(session["board"])
    revealed = json.loads(session["revealed"])
    active   = session["status"] == "active"

    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    buttons = []
    for i in range(grid):
        if i in board and (reveal_mine == i or not active):
            buttons.append(InlineKeyboardButton(text="💣", callback_data="mines_noop"))
        elif i in revealed:
            buttons.append(InlineKeyboardButton(text="💎", callback_data="mines_noop"))
        elif not active:
            buttons.append(InlineKeyboardButton(text="⬜", callback_data="mines_noop"))
        else:
            buttons.append(InlineKeyboardButton(text="⬜", callback_data=f"mines_open:{i}"))

    rows = [buttons[i*size:(i+1)*size] for i in range(size)]

    safe_opened = len(revealed)
    if active and safe_opened > 0:
        mult   = _calc_mult(session["mines_count"], safe_opened)
        payout = round(session["bet"] * mult, 4)
        rows.append([InlineKeyboardButton(
            text=f"💰 Забрать ${payout} (×{mult})", callback_data="mines_cashout"
        )])

    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "game:mines")
async def mines_start(callback: CallbackQuery, state: FSMContext):
    user    = await get_user(callback.from_user.id)
    cfg     = await get_mines_settings()
    session = await get_active_mines_session(user["id"])

    if session:
        safe_opened = len(json.loads(session["revealed"]))
        mult   = _calc_mult(session["mines_count"], safe_opened)
        markup = _build_board_markup(session)
        if safe_opened == 0:
            status_line = "Нажимай на клетки!"
        else:
            payout = round(session["bet"] * mult, 4)
            status_line = f"Открыто: {safe_opened} | ×{mult} | 💰 ${payout}"
        await callback.message.edit_text(
            f"💣 <b>Шахты</b> — ${session['bet']:.2f} | {session['mines_count']} мин\n\n{status_line}",
            parse_mode="HTML",
            reply_markup=markup
        )
        return await callback.answer()

    await state.set_state(GameFSM.mines_bet)
    await callback.message.edit_text(
        f"💣 <b>Шахты</b>\n\n"
        f"Открывай клетки на поле 5×5.\n"
        f"Каждая безопасная клетка увеличивает множитель.\n"
        f"Нарвёшься на мину — теряешь всё.\n\n"
        f"💸 Ставки: <b>${cfg['min_bet']} – ${cfg['max_bet']}</b>\n"
        f"💰 Баланс: <b>${user['balance']:.2f}</b>\n\n✏️ Введи ставку:",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(GameFSM.mines_bet)
async def mines_bet_entered(message: Message, state: FSMContext):
    try:
        bet = float(message.text.replace(",", "."))
    except ValueError:
        return await message.answer("❌ Введи число, например: <b>20</b>", parse_mode="HTML")

    user = await get_user(message.from_user.id)
    cfg  = await get_mines_settings()

    if bet < cfg["min_bet"] or bet > cfg["max_bet"]:
        return await message.answer(
            f"❌ Ставка: ${cfg['min_bet']}–${cfg['max_bet']}", parse_mode="HTML"
        )
    if user["balance"] < bet:
        return await message.answer(f"❌ Баланс: <b>${user['balance']:.2f}</b>", parse_mode="HTML")

    await state.update_data(bet=bet)
    await state.set_state(GameFSM.mines_count)

    builder = InlineKeyboardBuilder()
    for label, n in [("1 мина", 1), ("3 мины", 3), ("5 мин", 5), ("10 мин", 10), ("15 мин 🔥", 15)]:
        builder.button(text=label, callback_data=f"mines_cnt:{n}")
    builder.adjust(3, 2)

    await message.answer(
        f"💣 Ставка: <b>${bet:.2f}</b>\n\nСколько мин на поле?",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )


@router.callback_query(GameFSM.mines_count, F.data.startswith("mines_cnt:"))
async def mines_count_selected(callback: CallbackQuery, state: FSMContext):
    mines_count = int(callback.data.split(":")[1])
    data = await state.get_data()
    bet  = data["bet"]
    await state.clear()

    user = await get_user(callback.from_user.id)
    if user["balance"] < bet:
        return await callback.answer("❌ Недостаточно средств!", show_alert=True)

    mine_positions = random.sample(range(config.MINES_GRID), mines_count)
    await create_mines_session(
        user_id=user["id"], bet=bet, mines_count=mines_count,
        board=json.dumps(sorted(mine_positions)), multiplier=1.0
    )

    session = await get_active_mines_session(user["id"])
    markup  = _build_board_markup(session)

    await callback.message.edit_text(
        f"💣 <b>Шахты</b> — ${bet:.2f} | {mines_count} {'мина' if mines_count == 1 else 'мин'}\n\n"
        f"Нажимай на клетки — избегай 💣!",
        parse_mode="HTML",
        reply_markup=markup
    )
    await callback.answer()


@router.callback_query(F.data.startswith("mines_open:"))
async def mines_open_cell(callback: CallbackQuery):
    cell    = int(callback.data.split(":")[1])
    user    = await get_user(callback.from_user.id)
    session = await get_active_mines_session(user["id"])

    if not session:
        return await callback.answer("❌ Нет активной игры", show_alert=True)

    board    = json.loads(session["board"])
    revealed = json.loads(session["revealed"])

    if cell in revealed:
        return await callback.answer()

    if cell in board:
        # 💥 MINE — log result, balance already deducted on session start
        await update_mines_session(session["id"], json.dumps(revealed), session["multiplier"], status="lost")
        await log_game(user["id"], "mines", session["bet"], str(len(revealed)), "mine", False, 0)
        await callback.message.edit_text(
            f"💥 <b>МИНА!</b>\n\n"
            f"Ставка <b>${session['bet']:.2f}</b> потеряна.\n"
            f"Ты открыл <b>{len(revealed)}</b> клеток.\n\nПовезёт в следующий раз!",
            parse_mode="HTML",
            reply_markup=_after_mines_kb()
        )
        await callback.answer("💥 МИНА!", show_alert=True)
    else:
        # ✅ SAFE
        revealed.append(cell)
        safe_count = len(revealed)
        new_mult   = _calc_mult(session["mines_count"], safe_count)
        total_safe = config.MINES_GRID - session["mines_count"]

        if safe_count >= total_safe:
            # All safe — auto-cashout
            payout = await update_mines_session(session["id"], json.dumps(revealed), new_mult, status="won")
            await log_game(user["id"], "mines", session["bet"], str(safe_count), "all_safe", True, payout)
            updated = await get_user(callback.from_user.id)
            await callback.message.edit_text(
                f"🏆 <b>ИДЕАЛЬНО!</b> Все клетки открыты!\n\n"
                f"Множитель: <b>×{new_mult}</b>\n"
                f"Выигрыш: <b>+${payout:.4f}</b>\n"
                f"💼 Баланс: <b>${updated['balance']:.2f}</b>",
                parse_mode="HTML",
                reply_markup=_after_mines_kb()
            )
            await callback.answer(f"🏆 +${payout:.4f}!")
        else:
            await update_mines_session(session["id"], json.dumps(revealed), new_mult, status="active")
            payout = round(session["bet"] * new_mult, 4)
            markup = _build_board_markup({**session, "revealed": json.dumps(revealed), "status": "active"})
            await callback.message.edit_text(
                f"💣 <b>Шахты</b> — ${session['bet']:.2f} | {session['mines_count']} мин\n\n"
                f"✅ Открыто: <b>{safe_count}</b> | ×<b>{new_mult}</b> | 💰 <b>${payout}</b>",
                parse_mode="HTML",
                reply_markup=markup
            )
            await callback.answer(f"✅ ×{new_mult}")


@router.callback_query(F.data == "mines_cashout")
async def mines_cashout(callback: CallbackQuery):
    user    = await get_user(callback.from_user.id)
    session = await get_active_mines_session(user["id"])

    if not session:
        return await callback.answer("❌ Нет активной игры", show_alert=True)

    revealed   = json.loads(session["revealed"])
    safe_count = len(revealed)
    mult       = _calc_mult(session["mines_count"], safe_count)

    # update_mines_session credits balance and returns payout
    payout = await update_mines_session(session["id"], json.dumps(revealed), mult, status="cashed_out")
    await log_game(user["id"], "mines", session["bet"], str(safe_count), "cashout", True, payout)
    updated = await get_user(callback.from_user.id)

    await callback.message.edit_text(
        f"💰 <b>Выведено!</b>\n\n"
        f"Открыто клеток: <b>{safe_count}</b>\n"
        f"Множитель: <b>×{mult}</b>\n"
        f"Выигрыш: <b>+${payout:.4f}</b>\n"
        f"💼 Баланс: <b>${updated['balance']:.2f}</b>",
        parse_mode="HTML",
        reply_markup=_after_mines_kb()
    )
    await callback.answer(f"💰 +${payout:.4f}!")


@router.callback_query(F.data == "mines_noop")
async def mines_noop(callback: CallbackQuery):
    await callback.answer()


def _after_mines_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Новая игра", callback_data="game:mines")
    builder.button(text="🎲 Кости",      callback_data="game:dice")
    builder.button(text="🔙 Игры",       callback_data="games:menu")
    builder.adjust(2, 1)
    return builder.as_markup()
