from dataclasses import dataclass, field
from typing import List


@dataclass
class Config:
    # ── Bot ──────────────────────────────────────────────────
    BOT_TOKEN: str = "YOUR_BOT_TOKEN"
    ADMIN_IDS: List[int] = field(default_factory=lambda: [123456789])

    # ── CryptoPay ────────────────────────────────────────────
    CRYPTO_PAY_TOKEN: str = "YOUR_CRYPTOPAY_TOKEN"
    CRYPTO_PAY_API_URL: str = "https://pay.crypt.bot/api"  # mainnet
    # CRYPTO_PAY_API_URL: str = "https://testnet-pay.crypt.bot/api"  # testnet

    # ── Database ─────────────────────────────────────────────
    DB_PATH: str = "invest_bot.db"

    # ── Investment Plans ──────────────────────────────────────
    # (name, emoji, min_usdt, daily_rate_%, duration_days)
    PLANS: List[dict] = field(default_factory=lambda: [
        {"id": 1, "name": "Бронза",  "emoji": "🥉", "min": 10,   "max": 49,   "daily_rate": 1.5, "days": 7},
        {"id": 2, "name": "Серебро", "emoji": "🥈", "min": 50,   "max": 199,  "daily_rate": 2.5, "days": 14},
        {"id": 3, "name": "Золото",  "emoji": "🥇", "min": 200,  "max": 999,  "daily_rate": 4.0, "days": 30},
        {"id": 4, "name": "Платина", "emoji": "💎", "min": 1000, "max": 99999, "daily_rate": 6.0, "days": 60},
    ])

    # ── Rank Thresholds (total invested, USDT) ────────────────
    RANKS: List[dict] = field(default_factory=lambda: [
        {"name": "Новичок",    "emoji": "🌱", "min": 0},
        {"name": "Инвестор",   "emoji": "🔥", "min": 100},
        {"name": "Трейдер",    "emoji": "💼", "min": 500},
        {"name": "Эксперт",    "emoji": "👑", "min": 2000},
        {"name": "Кит",        "emoji": "🐋", "min": 10000},
    ])

    # ── Referral ──────────────────────────────────────────────
    REFERRAL_PERCENT: float = 5.0   # % от прибыли реферала

    # ── Daily Bonus ───────────────────────────────────────────
    DAILY_BONUS_USDT: float = 0.5   # базовый бонус

    # ── Games ─ Coin Flip ────────────────────────────────────
    COIN_FLIP_MIN_BET: float = 0.5
    COIN_FLIP_MAX_BET: float = 50.0
    COIN_FLIP_WIN_MULT: float = 1.9  # x1.9 при победе

    # ── Games ─ Dice ─────────────────────────────────────────
    DICE_MIN_BET: float = 0.5
    DICE_MAX_BET: float = 100.0
    # Multipliers for guess modes
    DICE_EXACT_MULT: float = 5.5   # угадать точное число 1-6
    DICE_HIGH_MULT: float = 1.8    # выпадет 4,5,6
    DICE_LOW_MULT: float = 1.8     # выпадет 1,2,3

    # ── Games ─ Mines ─────────────────────────────────────────
    MINES_MIN_BET: float = 1.0
    MINES_MAX_BET: float = 200.0
    MINES_GRID: int = 25           # 5×5 поле
    # Multiplier per safe cell opened (scales with mine count)
    # base_mult = 1 + (mines / (grid - mines)) * 0.9
    MINES_HOUSE_EDGE: float = 0.97 # 3% комиссия казино

    # ── Withdrawal ────────────────────────────────────────────
    WITHDRAW_MIN_USDT: float = 5.0
    WITHDRAW_FEE_PERCENT: float = 2.0   # 2% комиссия при выводе
    WITHDRAW_CURRENCIES: List[str] = field(default_factory=lambda: ["USDT", "TON", "BTC", "ETH", "LTC"])

    # ── Notifications ─────────────────────────────────────────
    NOTIFY_DAILY_PROFIT: bool = True    # уведомление каждые 24ч о накопленном
    NOTIFY_ON_COMPLETE: bool = True     # уведомление при завершении вклада
    NOTIFY_REFERRAL: bool = True        # уведомление при реферальном бонусе


config = Config()
