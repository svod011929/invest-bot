import logging
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from database.db import accrue_profits, get_users_for_daily_notify
from config import config

logger = logging.getLogger(__name__)


async def _run_accruals(bot: Bot):
    """Run hourly accrual and send push notifications."""
    try:
        notifications = await accrue_profits()
        for notif in notifications:
            try:
                if notif["type"] == "complete":
                    profit = notif["amount"] - notif["invested"]
                    await bot.send_message(
                        notif["telegram_id"],
                        f"🎉 <b>Вклад завершён!</b>\n\n"
                        f"📋 Вклад #{notif['inv_id']} «{notif['plan_name']}»\n"
                        f"💰 Зачислено: <b>${notif['amount']:.4f}</b>\n"
                        f"📈 Прибыль: <b>+${profit:.4f}</b>\n\n"
                        f"Открой новый вклад 📈",
                        parse_mode="HTML"
                    )
                elif notif["type"] == "referral":
                    await bot.send_message(
                        notif["telegram_id"],
                        f"👥 <b>Реферальный бонус!</b>\n\n"
                        f"Твой реферал завершил вклад.\n"
                        f"💰 Тебе начислено: <b>+${notif['amount']:.4f}</b>",
                        parse_mode="HTML"
                    )
            except Exception as e:
                logger.warning(f"Notify failed for {notif.get('telegram_id')}: {e}")
    except Exception as e:
        logger.error(f"Accrual error: {e}")


async def _send_daily_summary(bot: Bot):
    """Send daily profit summary to users with active investments."""
    if not config.NOTIFY_DAILY_PROFIT:
        return
    try:
        users = await get_users_for_daily_notify()
        for u in users:
            try:
                earned = u["total_earned_today"] or 0
                await bot.send_message(
                    u["telegram_id"],
                    f"📊 <b>Ежедневный отчёт</b>\n\n"
                    f"📈 Активных вкладов: <b>{u['inv_count']}</b>\n"
                    f"💹 Накоплено за всё время: <b>${earned:.4f}</b>\n\n"
                    f"Твои деньги работают 🚀",
                    parse_mode="HTML"
                )
            except Exception:
                pass
    except Exception as e:
        logger.error(f"Daily summary error: {e}")


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")

    # Hourly profit accrual + notifications
    scheduler.add_job(
        _run_accruals, "interval", hours=1,
        args=[bot], id="accrue_profits"
    )

    # Daily summary at 9:00 UTC
    scheduler.add_job(
        _send_daily_summary, "cron", hour=9, minute=0,
        args=[bot], id="daily_summary"
    )

    return scheduler
