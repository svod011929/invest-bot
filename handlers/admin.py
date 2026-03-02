import aiosqlite
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.db import (
    get_stats, get_user, update_balance, add_transaction,
    get_active_investments, get_referral_count, get_rank,
    get_all_settings, get_setting, set_setting,
)
from keyboards.kb import admin_kb
from config import config

router = Router()

DB = config.DB_PATH


def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


class AdminFSM(StatesGroup):
    broadcast_text    = State()
    find_user_id      = State()
    add_balance_amount = State()
    setting_value     = State()   # editing a setting


# ═════════════════════════════════════════════════════════════
#  HELPERS
# ═════════════════════════════════════════════════════════════

def _back_kb(target: str):
    b = InlineKeyboardBuilder()
    b.button(text="🔙 Назад", callback_data=target)
    return b.as_markup()


# ═════════════════════════════════════════════════════════════
#  ENTRY  /admin
# ═════════════════════════════════════════════════════════════

@router.message(Command("admin"))
async def admin_panel(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return await message.answer("❌ Нет доступа.")
    await state.clear()
    await message.answer("🛠 <b>Панель администратора</b>", parse_mode="HTML", reply_markup=admin_kb())


@router.callback_query(F.data == "admin:back")
async def admin_back(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "🛠 <b>Панель администратора</b>",
        parse_mode="HTML",
        reply_markup=admin_kb()
    )
    await callback.answer()


# ═════════════════════════════════════════════════════════════
#  STATS
# ═════════════════════════════════════════════════════════════

@router.callback_query(F.data == "admin:stats")
async def admin_stats(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("❌", show_alert=True)

    stats = await get_stats()
    text = (
        f"📊 <b>Статистика бота</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"👥 Всего пользователей: <b>{stats['total_users']}</b>\n"
        f"🆕 Новых сегодня: <b>{stats['new_today']}</b>\n\n"
        f"📈 Активных вкладов: <b>{stats['active_investments']}</b>\n"
        f"💼 В работе: <b>${stats['total_in_work']:.2f}</b>\n\n"
        f"📥 Всего депозитов: <b>${stats['total_deposits']:.2f}</b>"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=_back_kb("admin:back"))
    await callback.answer()


# ═════════════════════════════════════════════════════════════
#  FIND USER
# ═════════════════════════════════════════════════════════════

@router.callback_query(F.data == "admin:find_user")
async def admin_find_user(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(AdminFSM.find_user_id)
    b = InlineKeyboardBuilder()
    b.button(text="🔙 Отмена", callback_data="admin:back")
    await callback.message.edit_text(
        "✏️ Введи <b>Telegram ID</b> пользователя:",
        parse_mode="HTML",
        reply_markup=b.as_markup()
    )
    await callback.answer()


@router.message(AdminFSM.find_user_id)
async def admin_show_user(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    try:
        tg_id = int(message.text.strip())
    except ValueError:
        return await message.answer("❌ Введи числовой ID", reply_markup=_back_kb("admin:back"))

    user = await get_user(tg_id)
    if not user:
        return await message.answer("❌ Пользователь не найден", reply_markup=_back_kb("admin:back"))

    rank      = await get_rank(user["total_invested"])
    ref_count = await get_referral_count(user["id"])
    active    = await get_active_investments(user["id"])

    text = (
        f"👤 <b>Пользователь #{user['id']}</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"TG ID: <code>{user['telegram_id']}</code>\n"
        f"Username: @{user['username'] or '—'}\n"
        f"Имя: {user['first_name'] or '—'}\n"
        f"Ранг: {rank['emoji']} {rank['name']}\n\n"
        f"💰 Баланс: <b>${user['balance']:.2f}</b>\n"
        f"📥 Вложено: <b>${user['total_invested']:.2f}</b>\n"
        f"📤 Заработано: <b>${user['total_earned']:.2f}</b>\n"
        f"📈 Активных вкладов: <b>{len(active)}</b>\n"
        f"👥 Рефералов: <b>{ref_count}</b>\n"
        f"📅 Регистрация: <b>{user['created_at'][:10]}</b>\n"
        f"🚫 Забанен: <b>{'Да' if user['is_banned'] else 'Нет'}</b>"
    )

    b = InlineKeyboardBuilder()
    b.button(text="➕ Начислить / списать", callback_data=f"admin:add_balance:{user['id']}")
    b.button(text="🚫 Бан / Разбан",         callback_data=f"admin:toggle_ban:{user['id']}")
    b.button(text="🔙 Назад",                 callback_data="admin:back")
    b.adjust(1)
    await message.answer(text, parse_mode="HTML", reply_markup=b.as_markup())


# ─────────────────────────────────────────────────────────────
#  ADD BALANCE
# ─────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin:add_balance:"))
async def admin_add_balance_prompt(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    user_id = int(callback.data.split(":")[2])
    await state.update_data(target_user_id=user_id)
    await state.set_state(AdminFSM.add_balance_amount)
    b = InlineKeyboardBuilder()
    b.button(text="🔙 Отмена", callback_data="admin:back")
    await callback.message.answer(
        "✏️ Введи сумму для начисления.\n"
        "Для списания введи отрицательное число, например: <b>-50</b>",
        parse_mode="HTML",
        reply_markup=b.as_markup()
    )
    await callback.answer()


@router.message(AdminFSM.add_balance_amount)
async def admin_add_balance(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    await state.clear()

    try:
        amount = float(message.text.replace(",", "."))
    except ValueError:
        return await message.answer("❌ Некорректная сумма")

    await update_balance(data["target_user_id"], amount)
    await add_transaction(
        data["target_user_id"],
        "deposit" if amount > 0 else "withdraw",
        abs(amount),
        comment="Операция администратора"
    )
    action = "Начислено" if amount > 0 else "Списано"
    await message.answer(
        f"✅ {action}: <b>${abs(amount):.2f}</b>",
        parse_mode="HTML",
        reply_markup=_back_kb("admin:back")
    )


# ─────────────────────────────────────────────────────────────
#  BAN TOGGLE
# ─────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin:toggle_ban:"))
async def admin_toggle_ban(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    user_id = int(callback.data.split(":")[2])
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT is_banned FROM users WHERE id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
        new_val = 0 if row[0] else 1
        await db.execute("UPDATE users SET is_banned = ? WHERE id = ?", (new_val, user_id))
        await db.commit()

    status = "🚫 Забанен" if new_val else "✅ Разбанен"
    await callback.answer(status, show_alert=True)


# ═════════════════════════════════════════════════════════════
#  BROADCAST
# ═════════════════════════════════════════════════════════════

@router.callback_query(F.data == "admin:broadcast")
async def admin_broadcast_prompt(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.update_data(broadcast_parse_mode="HTML")  # default
    b = InlineKeyboardBuilder()
    b.button(text="🔤 HTML",       callback_data="broadcast:fmt:HTML")
    b.button(text="✳️ Markdown",   callback_data="broadcast:fmt:MarkdownV2")
    b.button(text="📄 Без разметки", callback_data="broadcast:fmt:none")
    b.button(text="🔙 Отмена",     callback_data="admin:back")
    b.adjust(3, 1)
    await callback.message.edit_text(
        "📢 <b>Рассылка</b>\n\n"
        "Выбери формат сообщения:\n\n"
        "🔤 <b>HTML</b> — <code>&lt;b&gt;жирный&lt;/b&gt;</code>, <code>&lt;i&gt;курсив&lt;/i&gt;</code>, <code>&lt;code&gt;код&lt;/code&gt;</code>\n"
        "✳️ <b>Markdown</b> — <code>*жирный*</code>, <code>_курсив_</code>, <code>`код`</code>\n"
        "📄 <b>Без разметки</b> — текст как есть",
        parse_mode="HTML",
        reply_markup=b.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("broadcast:fmt:"))
async def broadcast_select_format(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    fmt = callback.data.split(":")[2]
    await state.update_data(broadcast_parse_mode=fmt)
    await state.set_state(AdminFSM.broadcast_text)

    fmt_labels = {
        "HTML":        "🔤 HTML (<b>жирный</b>, <i>курсив</i>, <code>код</code>, <a href='...'>ссылка</a>)",
        "MarkdownV2":  "✳️ Markdown V2 (*жирный*, _курсив_, `код`, [текст](url))\n⚠️ Спецсимволы . ! ( ) - = нужно экранировать через \\",
        "none":        "📄 Без разметки — текст отправится как есть",
    }

    b = InlineKeyboardBuilder()
    b.button(text="🔙 Назад", callback_data="admin:broadcast")

    await callback.message.edit_text(
        f"📢 <b>Рассылка</b> · {fmt_labels.get(fmt, fmt)}\n\n"
        f"Введи текст сообщения:",
        parse_mode="HTML",
        reply_markup=b.as_markup()
    )
    await callback.answer()


@router.message(AdminFSM.broadcast_text)
async def admin_broadcast_send(message: Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    await state.clear()

    fmt = data.get("broadcast_parse_mode", "HTML")
    parse_mode = None if fmt == "none" else fmt

    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT telegram_id FROM users WHERE is_banned = 0") as cur:
            users = await cur.fetchall()

    sent, failed = 0, 0
    progress_msg = await message.answer(f"📢 Рассылка... 0/{len(users)}")
    for i, (tg_id,) in enumerate(users):
        try:
            await bot.send_message(tg_id, message.text, parse_mode=parse_mode)
            sent += 1
        except Exception:
            failed += 1
        if i % 20 == 0:
            try:
                await progress_msg.edit_text(f"📢 Рассылка... {i+1}/{len(users)}")
            except Exception:
                pass

    fmt_label = {"HTML": "HTML", "MarkdownV2": "Markdown V2", "none": "без разметки"}.get(fmt, fmt)
    await progress_msg.edit_text(
        f"📢 <b>Рассылка завершена!</b>\n\n"
        f"🔤 Формат: <b>{fmt_label}</b>\n"
        f"✅ Отправлено: <b>{sent}</b>\n"
        f"❌ Ошибок: <b>{failed}</b>",
        parse_mode="HTML",
        reply_markup=_back_kb("admin:back")
    )


# ═════════════════════════════════════════════════════════════
#  SETTINGS
# ═════════════════════════════════════════════════════════════

SETTINGS_SECTIONS = {
    "plans":    ("📈 Инвестиционные планы",  ["plan_1_daily_rate","plan_1_min","plan_1_days",
                                               "plan_2_daily_rate","plan_2_min","plan_2_days",
                                               "plan_3_daily_rate","plan_3_min","plan_3_days",
                                               "plan_4_daily_rate","plan_4_min","plan_4_days"]),
    "referral": ("👥 Реферальная программа", ["referral_percent"]),
    "bonus":    ("🎁 Бонусы",                ["daily_bonus"]),
    "games":    ("🎰 Игры",                  ["coin_min_bet","coin_max_bet","coin_mult",
                                               "dice_exact_mult","dice_hl_mult",
                                               "mines_min_bet","mines_max_bet"]),
    "withdraw": ("📤 Вывод средств",         ["withdraw_min","withdraw_fee"]),
}


def _settings_main_kb():
    b = InlineKeyboardBuilder()
    for section_id, (label, _) in SETTINGS_SECTIONS.items():
        b.button(text=label, callback_data=f"settings:section:{section_id}")
    b.button(text="🔙 Назад", callback_data="admin:back")
    b.adjust(1)
    return b.as_markup()


def _section_kb(section_id: str, settings: dict):
    _, keys = SETTINGS_SECTIONS[section_id]
    b = InlineKeyboardBuilder()
    for key in keys:
        if key in settings:
            label = settings[key]["label"]
            value = settings[key]["value"]
            b.button(text=f"{label}: {value}", callback_data=f"settings:edit:{key}")
    b.button(text="🔙 Назад", callback_data="admin:settings")
    b.adjust(1)
    return b.as_markup()


@router.callback_query(F.data == "admin:settings")
async def admin_settings(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("❌", show_alert=True)
    await state.clear()
    await callback.message.edit_text(
        "⚙️ <b>Настройки бота</b>\n\nВыбери раздел:",
        parse_mode="HTML",
        reply_markup=_settings_main_kb()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("settings:section:"))
async def settings_section(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    section_id = callback.data.split(":")[2]
    if section_id not in SETTINGS_SECTIONS:
        return await callback.answer("❌ Раздел не найден", show_alert=True)

    title, _ = SETTINGS_SECTIONS[section_id]
    all_settings = await get_all_settings()

    await callback.message.edit_text(
        f"⚙️ <b>{title}</b>\n\nНажми на параметр чтобы изменить:",
        parse_mode="HTML",
        reply_markup=_section_kb(section_id, all_settings)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("settings:edit:"))
async def settings_edit_prompt(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    key = callback.data.split(":", 2)[2]
    all_settings = await get_all_settings()

    if key not in all_settings:
        return await callback.answer("❌ Параметр не найден", show_alert=True)

    label = all_settings[key]["label"]
    current = all_settings[key]["value"]

    # Find which section this key belongs to
    section_id = next(
        (sid for sid, (_, keys) in SETTINGS_SECTIONS.items() if key in keys),
        None
    )

    await state.update_data(setting_key=key, setting_section=section_id)
    await state.set_state(AdminFSM.setting_value)

    b = InlineKeyboardBuilder()
    b.button(text="🔙 Отмена", callback_data=f"settings:section:{section_id}" if section_id else "admin:settings")

    await callback.message.edit_text(
        f"✏️ <b>{label}</b>\n\n"
        f"Текущее значение: <code>{current}</code>\n\n"
        f"Введи новое значение:",
        parse_mode="HTML",
        reply_markup=b.as_markup()
    )
    await callback.answer()


@router.message(AdminFSM.setting_value)
async def settings_save_value(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    await state.clear()

    key = data.get("setting_key")
    section_id = data.get("setting_section")
    new_value = message.text.strip().replace(",", ".")

    # Validate — must be a positive number
    try:
        num = float(new_value)
        if num < 0:
            raise ValueError
    except ValueError:
        return await message.answer(
            "❌ Введи корректное положительное число.",
            reply_markup=_back_kb(f"settings:section:{section_id}" if section_id else "admin:settings")
        )

    all_settings = await get_all_settings()
    label = all_settings[key]["label"] if key in all_settings else key

    await set_setting(key, new_value)

    # Re-fetch section for updated keyboard
    all_settings = await get_all_settings()
    title, _ = SETTINGS_SECTIONS.get(section_id, ("Настройки", []))

    await message.answer(
        f"✅ <b>{label}</b> обновлено: <code>{new_value}</code>",
        parse_mode="HTML",
        reply_markup=_section_kb(section_id, all_settings) if section_id else _settings_main_kb()
    )
