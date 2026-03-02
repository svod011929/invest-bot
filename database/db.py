import aiosqlite
import asyncio
from datetime import datetime, date
from config import config

DB_PATH = config.DB_PATH

# ─────────────────────────────────────────────────────────────
#  INIT
# ─────────────────────────────────────────────────────────────

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id     INTEGER UNIQUE NOT NULL,
            username        TEXT,
            first_name      TEXT,
            balance         REAL    DEFAULT 0.0,
            total_invested  REAL    DEFAULT 0.0,
            total_earned    REAL    DEFAULT 0.0,
            referral_code   TEXT    UNIQUE,
            referred_by     INTEGER REFERENCES users(id),
            last_bonus_claim TEXT,
            notify_enabled  INTEGER DEFAULT 1,
            is_banned       INTEGER DEFAULT 0,
            created_at      TEXT    DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS investments (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL REFERENCES users(id),
            plan_id      INTEGER NOT NULL,
            amount       REAL    NOT NULL,
            daily_rate   REAL    NOT NULL,
            days         INTEGER NOT NULL,
            earned       REAL    DEFAULT 0.0,
            start_date   TEXT    NOT NULL,
            end_date     TEXT    NOT NULL,
            last_accrual TEXT,
            status       TEXT    DEFAULT 'active',
            created_at   TEXT    DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id),
            type        TEXT    NOT NULL,
            amount      REAL    NOT NULL,
            currency    TEXT    DEFAULT 'USDT',
            invoice_id  TEXT,
            status      TEXT    DEFAULT 'pending',
            comment     TEXT,
            created_at  TEXT    DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS games (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id),
            game_type   TEXT    NOT NULL,
            bet         REAL    NOT NULL,
            choice      TEXT,
            result      TEXT,
            win         INTEGER DEFAULT 0,
            profit      REAL    DEFAULT 0.0,
            created_at  TEXT    DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS withdrawals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id),
            amount      REAL    NOT NULL,
            fee         REAL    NOT NULL DEFAULT 0,
            net_amount  REAL    NOT NULL,
            currency    TEXT    NOT NULL DEFAULT 'USDT',
            spend_id    TEXT    UNIQUE,
            status      TEXT    DEFAULT 'pending',
            created_at  TEXT    DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS mines_sessions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id),
            bet         REAL    NOT NULL,
            mines_count INTEGER NOT NULL,
            board       TEXT    NOT NULL,
            revealed    TEXT    DEFAULT '[]',
            multiplier  REAL    DEFAULT 1.0,
            status      TEXT    DEFAULT 'active',
            created_at  TEXT    DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS bot_settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            label TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_users_tg          ON users(telegram_id);
        CREATE INDEX IF NOT EXISTS idx_invest_user       ON investments(user_id, status);
        CREATE INDEX IF NOT EXISTS idx_tx_user           ON transactions(user_id);
        CREATE INDEX IF NOT EXISTS idx_mines_user_active ON mines_sessions(user_id, status);
        """)
        await db.commit()
    await init_settings()


# ─────────────────────────────────────────────────────────────
#  USERS
# ─────────────────────────────────────────────────────────────

async def get_or_create_user(telegram_id: int, username: str = None,
                              first_name: str = None, ref_code: str = None) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)) as cur:
            user = await cur.fetchone()
        if user:
            # Update username/first_name if changed
            await db.execute(
                "UPDATE users SET username=?, first_name=? WHERE telegram_id=?",
                (username, first_name, telegram_id)
            )
            await db.commit()
            return dict(user)

        import hashlib, time
        code = hashlib.md5(f"{telegram_id}{time.time()}".encode()).hexdigest()[:8].upper()

        referred_by = None
        if ref_code:
            async with db.execute("SELECT id FROM users WHERE referral_code = ?", (ref_code,)) as cur:
                referrer = await cur.fetchone()
                # Prevent self-referral
                if referrer and referrer["id"] != telegram_id:
                    referred_by = referrer["id"]

        await db.execute(
            "INSERT OR IGNORE INTO users (telegram_id, username, first_name, referral_code, referred_by) "
            "VALUES (?, ?, ?, ?, ?)",
            (telegram_id, username, first_name, code, referred_by)
        )
        await db.commit()

        async with db.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else {}


async def get_user(telegram_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_user_by_id(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


def _safe_field(field: str) -> str:
    """Whitelist DB field names to prevent SQL injection."""
    allowed = {"balance", "total_invested", "total_earned"}
    if field not in allowed:
        raise ValueError(f"Invalid field: {field}")
    return field


async def update_balance(user_id: int, delta: float, field: str = "balance"):
    field = _safe_field(field)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE users SET {field} = {field} + ? WHERE id = ?", (delta, user_id))
        await db.commit()


async def get_rank(total_invested: float) -> dict:
    ranks = config.RANKS
    current = ranks[0]
    for r in ranks:
        if total_invested >= r["min"]:
            current = r
    return current


async def get_referral_count(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users WHERE referred_by = ?", (user_id,)) as cur:
            return (await cur.fetchone())[0]


async def set_notify(user_id: int, enabled: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET notify_enabled = ? WHERE id = ?", (int(enabled), user_id))
        await db.commit()


# ─────────────────────────────────────────────────────────────
#  INVESTMENTS
# ─────────────────────────────────────────────────────────────

async def create_investment(user_id: int, plan: dict, amount: float) -> int:
    from datetime import timedelta
    start = datetime.now()
    end   = start + timedelta(days=plan["days"])
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO investments (user_id, plan_id, amount, daily_rate, days, start_date, end_date, last_accrual) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, plan["id"], amount, plan["daily_rate"], plan["days"],
             start.isoformat(), end.isoformat(), start.isoformat())
        )
        await db.execute(
            "UPDATE users SET balance = balance - ?, total_invested = total_invested + ? WHERE id = ?",
            (amount, amount, user_id)
        )
        await db.commit()
        return cur.lastrowid


async def get_active_investments(user_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM investments WHERE user_id = ? AND status = 'active' ORDER BY created_at DESC",
            (user_id,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_investment_history(user_id: int, limit: int = 10) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM investments WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


# ─────────────────────────────────────────────────────────────
#  TRANSACTIONS
# ─────────────────────────────────────────────────────────────

async def add_transaction(user_id: int, tx_type: str, amount: float,
                           currency: str = "USDT", invoice_id: str = None,
                           status: str = "completed", comment: str = None) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO transactions (user_id, type, amount, currency, invoice_id, status, comment) "
            "VALUES (?,?,?,?,?,?,?)",
            (user_id, tx_type, amount, currency, invoice_id, status, comment)
        )
        await db.commit()
        return cur.lastrowid


async def get_transactions(user_id: int, limit: int = 10) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM transactions WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


# ─────────────────────────────────────────────────────────────
#  DAILY BONUS
# ─────────────────────────────────────────────────────────────

async def can_claim_bonus(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT last_bonus_claim FROM users WHERE id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            if not row or not row[0]:
                return True
            last = datetime.fromisoformat(row[0]).date()
            return last < date.today()


async def claim_bonus(user_id: int, amount: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET balance = balance + ?, last_bonus_claim = ? WHERE id = ?",
            (amount, datetime.now().isoformat(), user_id)
        )
        await db.commit()


# ─────────────────────────────────────────────────────────────
#  GAMES  — safe atomic writes
# ─────────────────────────────────────────────────────────────

async def save_game(user_id: int, game_type: str, bet: float,
                    choice: str, result: str, win: bool, profit: float) -> dict | None:
    """
    Atomically:
      • verifies user has enough balance (bet > 0 and balance >= bet)
      • deducts bet, adds profit if win
      • logs to games table
    Returns result dict or None if balance check fails.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # Atomic balance check + deduct inside one transaction
        async with db.execute("SELECT balance FROM users WHERE id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
        if not row or row["balance"] < bet:
            return None  # Insufficient funds

        net = profit - bet if win else -bet
        await db.execute(
            "INSERT INTO games (user_id, game_type, bet, choice, result, win, profit) VALUES (?,?,?,?,?,?,?)",
            (user_id, game_type, bet, choice, result, int(win), profit if win else 0)
        )
        await db.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (net, user_id))
        await db.commit()
    return {"win": win, "profit": profit, "net": net}


async def log_game(user_id: int, game_type: str, bet: float,
                   choice: str, result: str, win: bool, profit: float):
    """Log game result WITHOUT touching balance (used by mines which manages balance separately)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO games (user_id, game_type, bet, choice, result, win, profit) VALUES (?,?,?,?,?,?,?)",
            (user_id, game_type, bet, choice, result, int(win), profit if win else 0)
        )
        await db.commit()


# ─────────────────────────────────────────────────────────────
#  MINES SESSIONS
# ─────────────────────────────────────────────────────────────

async def create_mines_session(user_id: int, bet: float, mines_count: int,
                                board: str, multiplier: float) -> int | None:
    """
    Atomically deducts bet and creates session.
    Returns session id, or None if insufficient balance.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # Cancel any stale active session (shouldn't happen but safety net)
        await db.execute(
            "UPDATE mines_sessions SET status = 'lost' WHERE user_id = ? AND status = 'active'",
            (user_id,)
        )
        async with db.execute("SELECT balance FROM users WHERE id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
        if not row or row["balance"] < bet:
            return None
        cur = await db.execute(
            "INSERT INTO mines_sessions (user_id, bet, mines_count, board, multiplier) VALUES (?,?,?,?,?)",
            (user_id, bet, mines_count, board, multiplier)
        )
        await db.execute("UPDATE users SET balance = balance - ? WHERE id = ?", (bet, user_id))
        await db.commit()
        return cur.lastrowid


async def get_active_mines_session(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM mines_sessions WHERE user_id = ? AND status = 'active' "
            "ORDER BY created_at DESC LIMIT 1",
            (user_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def update_mines_session(session_id: int, revealed: str, multiplier: float,
                                status: str = "active") -> float:
    """
    Update mines session state.
    On win/cashout: credits payout to user balance.
    Returns payout amount (0 if not a winning state).
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        await db.execute(
            "UPDATE mines_sessions SET revealed = ?, multiplier = ?, status = ? WHERE id = ?",
            (revealed, multiplier, status, session_id)
        )

        payout = 0.0
        if status in ("won", "cashed_out"):
            async with db.execute(
                "SELECT bet, mines_count, user_id FROM mines_sessions WHERE id = ?", (session_id,)
            ) as cur:
                row = await cur.fetchone()
            if row:
                payout = round(row["bet"] * multiplier, 4)
                profit = round(payout - row["bet"], 4)
                await db.execute(
                    "UPDATE users SET balance = balance + ?, total_earned = total_earned + ? WHERE id = ?",
                    (payout, profit, row["user_id"])
                )

        await db.commit()
        return payout


# ─────────────────────────────────────────────────────────────
#  NOTIFICATIONS
# ─────────────────────────────────────────────────────────────

async def get_users_for_daily_notify() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT DISTINCT u.telegram_id, u.first_name, u.id,
                   SUM(i.earned) as total_earned_today,
                   COUNT(i.id)   as inv_count
            FROM users u
            JOIN investments i ON i.user_id = u.id
            WHERE i.status = 'active'
              AND u.notify_enabled = 1
              AND u.is_banned = 0
            GROUP BY u.id
        """) as cur:
            return [dict(r) for r in await cur.fetchall()]


# ─────────────────────────────────────────────────────────────
#  SCHEDULER: PROFIT ACCRUAL
# ─────────────────────────────────────────────────────────────

async def accrue_profits() -> list[dict]:
    from utils.settings import get_referral_percent, get_plan
    now = datetime.now()
    notifications = []

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM investments WHERE status = 'active'") as cur:
            investments = [dict(r) for r in await cur.fetchall()]

        for inv in investments:
            async with db.execute(
                "SELECT telegram_id, notify_enabled, referred_by FROM users WHERE id = ?",
                (inv["user_id"],)
            ) as cur2:
                _row = await cur2.fetchone()
                if not _row:
                    continue
                user_row = dict(_row)

            end_date  = datetime.fromisoformat(inv["end_date"])
            live_plan = await get_plan(inv["plan_id"])
            plan_name = live_plan["name"] if live_plan else f"#{inv['plan_id']}"
            ref_pct   = await get_referral_percent()

            if now >= end_date:
                total_profit = inv["amount"] * (inv["daily_rate"] / 100) * inv["days"]
                payout = round(max(inv["amount"] + total_profit - inv["earned"], 0), 4)

                await db.execute(
                    "UPDATE investments SET status='completed', earned=earned+? WHERE id=?",
                    (payout, inv["id"])
                )
                await db.execute(
                    "UPDATE users SET balance=balance+?, total_earned=total_earned+? WHERE id=?",
                    (payout, payout - inv["amount"], inv["user_id"])
                )
                await db.execute(
                    "INSERT INTO transactions (user_id,type,amount,status,comment) VALUES(?,?,?,?,?)",
                    (inv["user_id"], "profit", payout, "completed", f"Завершение вклада #{inv['id']}")
                )

                if user_row["notify_enabled"]:
                    notifications.append({
                        "type": "complete",
                        "telegram_id": user_row["telegram_id"],
                        "inv_id": inv["id"],
                        "amount": payout,
                        "invested": inv["amount"],
                        "plan_name": plan_name,
                    })

                if user_row["referred_by"]:
                    async with db.execute(
                        "SELECT telegram_id, notify_enabled FROM users WHERE id = ?",
                        (user_row["referred_by"],)
                    ) as cur3:
                        _ref = await cur3.fetchone()
                        if not _ref:
                            continue
                        ref_row = dict(_ref)

                    ref_bonus = round((payout - inv["amount"]) * ref_pct / 100, 4)
                    if ref_bonus > 0:
                        await db.execute(
                            "UPDATE users SET balance=balance+?, total_earned=total_earned+? WHERE id=?",
                            (ref_bonus, ref_bonus, user_row["referred_by"])
                        )
                        await db.execute(
                            "INSERT INTO transactions (user_id,type,amount,status,comment) VALUES(?,?,?,?,?)",
                            (user_row["referred_by"], "referral", ref_bonus, "completed",
                             f"Реферальный бонус с вклада #{inv['id']}")
                        )
                        if ref_row["notify_enabled"] and config.NOTIFY_REFERRAL:
                            notifications.append({
                                "type": "referral",
                                "telegram_id": ref_row["telegram_id"],
                                "amount": ref_bonus,
                            })
            else:
                hourly = round(inv["amount"] * (inv["daily_rate"] / 100) / 24, 6)
                await db.execute(
                    "UPDATE investments SET earned=earned+?, last_accrual=? WHERE id=?",
                    (hourly, now.isoformat(), inv["id"])
                )

        await db.commit()
    return notifications


# ─────────────────────────────────────────────────────────────
#  BOT SETTINGS
# ─────────────────────────────────────────────────────────────

async def init_settings():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                label TEXT
            )
        """)
        defaults = [
            ("plan_1_daily_rate", str(config.PLANS[0]["daily_rate"]), "🥉 Бронза % в день"),
            ("plan_1_min",        str(config.PLANS[0]["min"]),        "🥉 Бронза мин. $"),
            ("plan_1_days",       str(config.PLANS[0]["days"]),       "🥉 Бронза дней"),
            ("plan_2_daily_rate", str(config.PLANS[1]["daily_rate"]), "🥈 Серебро % в день"),
            ("plan_2_min",        str(config.PLANS[1]["min"]),        "🥈 Серебро мин. $"),
            ("plan_2_days",       str(config.PLANS[1]["days"]),       "🥈 Серебро дней"),
            ("plan_3_daily_rate", str(config.PLANS[2]["daily_rate"]), "🥇 Золото % в день"),
            ("plan_3_min",        str(config.PLANS[2]["min"]),        "🥇 Золото мин. $"),
            ("plan_3_days",       str(config.PLANS[2]["days"]),       "🥇 Золото дней"),
            ("plan_4_daily_rate", str(config.PLANS[3]["daily_rate"]), "💎 Платина % в день"),
            ("plan_4_min",        str(config.PLANS[3]["min"]),        "💎 Платина мин. $"),
            ("plan_4_days",       str(config.PLANS[3]["days"]),       "💎 Платина дней"),
            ("referral_percent",  str(config.REFERRAL_PERCENT),       "👥 Реферальный %"),
            ("daily_bonus",       str(config.DAILY_BONUS_USDT),       "🎁 Дневной бонус $"),
            ("coin_min_bet",      str(config.COIN_FLIP_MIN_BET),      "🪙 Монета мин. ставка"),
            ("coin_max_bet",      str(config.COIN_FLIP_MAX_BET),      "🪙 Монета макс. ставка"),
            ("coin_mult",         str(config.COIN_FLIP_WIN_MULT),     "🪙 Монета множитель"),
            ("dice_exact_mult",   str(config.DICE_EXACT_MULT),        "🎲 Кости точное ×"),
            ("dice_hl_mult",      str(config.DICE_HIGH_MULT),         "🎲 Кости выс/низ ×"),
            ("mines_min_bet",     str(config.MINES_MIN_BET),          "💣 Шахты мин. ставка"),
            ("mines_max_bet",     str(config.MINES_MAX_BET),          "💣 Шахты макс. ставка"),
            ("withdraw_min",      str(config.WITHDRAW_MIN_USDT),      "📤 Вывод мин. $"),
            ("withdraw_fee",      str(config.WITHDRAW_FEE_PERCENT),   "📤 Вывод комиссия %"),
        ]
        for key, value, label in defaults:
            await db.execute(
                "INSERT OR IGNORE INTO bot_settings (key, value, label) VALUES (?, ?, ?)",
                (key, value, label)
            )
        await db.commit()


async def get_setting(key: str, default=None):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM bot_settings WHERE key = ?", (key,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else default


async def set_setting(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO bot_settings (key, value, label) "
            "VALUES (?, ?, (SELECT label FROM bot_settings WHERE key = ?))",
            (key, value, key)
        )
        await db.commit()


async def get_all_settings() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT key, value, label FROM bot_settings ORDER BY key") as cur:
            return {r["key"]: {"value": r["value"], "label": r["label"]}
                    for r in await cur.fetchall()}


# ─────────────────────────────────────────────────────────────
#  ADMIN
# ─────────────────────────────────────────────────────────────

async def get_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            total_users = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM investments WHERE status='active'") as cur:
            active_inv = (await cur.fetchone())[0]
        async with db.execute("SELECT COALESCE(SUM(amount),0) FROM investments WHERE status='active'") as cur:
            total_in_work = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT COALESCE(SUM(amount),0) FROM transactions WHERE type='deposit' AND status='completed'"
        ) as cur:
            total_deposits = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM users WHERE date(created_at) = date('now')"
        ) as cur:
            new_today = (await cur.fetchone())[0]

    return {
        "total_users":        total_users,
        "active_investments": active_inv,
        "total_in_work":      round(total_in_work, 2),
        "total_deposits":     round(total_deposits, 2),
        "new_today":          new_today,
    }
