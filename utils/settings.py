"""
utils/settings.py
Читает актуальные значения из таблицы bot_settings.
Используй вместо config.X везде где значение может быть изменено через админ-панель.
"""
from database.db import get_setting
from config import config


async def get_float(key: str, fallback: float) -> float:
    val = await get_setting(key)
    try:
        return float(val) if val is not None else fallback
    except (ValueError, TypeError):
        return fallback


# ─────────────────────────────────────────────────────────────
#  PLANS  (возвращает список как в config.PLANS, но с БД-значениями)
# ─────────────────────────────────────────────────────────────

async def get_plans() -> list[dict]:
    plans = []
    for p in config.PLANS:
        i = p["id"]
        plans.append({
            **p,
            "daily_rate": await get_float(f"plan_{i}_daily_rate", p["daily_rate"]),
            "min":        await get_float(f"plan_{i}_min",        p["min"]),
            "days":       int(await get_float(f"plan_{i}_days",   p["days"])),
        })
    return plans


async def get_plan(plan_id: int) -> dict | None:
    plans = await get_plans()
    return next((p for p in plans if p["id"] == plan_id), None)


# ─────────────────────────────────────────────────────────────
#  REFERRAL
# ─────────────────────────────────────────────────────────────

async def get_referral_percent() -> float:
    return await get_float("referral_percent", config.REFERRAL_PERCENT)


# ─────────────────────────────────────────────────────────────
#  DAILY BONUS
# ─────────────────────────────────────────────────────────────

async def get_daily_bonus() -> float:
    return await get_float("daily_bonus", config.DAILY_BONUS_USDT)


# ─────────────────────────────────────────────────────────────
#  GAMES
# ─────────────────────────────────────────────────────────────

async def get_coin_settings() -> dict:
    return {
        "min_bet":  await get_float("coin_min_bet", config.COIN_FLIP_MIN_BET),
        "max_bet":  await get_float("coin_max_bet", config.COIN_FLIP_MAX_BET),
        "mult":     await get_float("coin_mult",    config.COIN_FLIP_WIN_MULT),
    }


async def get_dice_settings() -> dict:
    return {
        "min_bet":     await get_float("coin_min_bet",    config.DICE_MIN_BET),
        "max_bet":     await get_float("coin_max_bet",    config.DICE_MAX_BET),
        "exact_mult":  await get_float("dice_exact_mult", config.DICE_EXACT_MULT),
        "hl_mult":     await get_float("dice_hl_mult",    config.DICE_HIGH_MULT),
    }


async def get_mines_settings() -> dict:
    return {
        "min_bet": await get_float("mines_min_bet", config.MINES_MIN_BET),
        "max_bet": await get_float("mines_max_bet", config.MINES_MAX_BET),
    }


# ─────────────────────────────────────────────────────────────
#  WITHDRAW
# ─────────────────────────────────────────────────────────────

async def get_withdraw_settings() -> dict:
    return {
        "min":        await get_float("withdraw_min",  config.WITHDRAW_MIN_USDT),
        "fee_percent": await get_float("withdraw_fee", config.WITHDRAW_FEE_PERCENT),
    }
