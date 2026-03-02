import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import config
from database.db import init_db
from handlers import start, invest, payments, games, referral, admin, withdraw
from middlewares.ban import BanMiddleware
from middlewares.reset_state import ResetStateMiddleware
from utils.scheduler import setup_scheduler


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


async def main():
    # Init DB
    await init_db()
    logger.info("✅ Database initialized")

    # Bot & Dispatcher
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    # Middlewares
    dp.message.middleware(ResetStateMiddleware())
    dp.message.middleware(BanMiddleware())
    dp.callback_query.middleware(BanMiddleware())

    # Routers
    dp.include_router(start.router)
    dp.include_router(invest.router)
    dp.include_router(payments.router)
    dp.include_router(games.router)
    dp.include_router(referral.router)
    dp.include_router(admin.router)
    dp.include_router(withdraw.router)

    # Scheduler — pass bot instance for notifications
    scheduler = setup_scheduler(bot)
    scheduler.start()
    logger.info("✅ Scheduler started")

    # Start polling
    logger.info("🚀 Bot started")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
