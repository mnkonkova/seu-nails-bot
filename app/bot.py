import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import settings
from app.db import init_db
from app.handlers import common
from app.handlers.admin import add_date as adm_add_date
from app.handlers.admin import delete as adm_delete
from app.handlers.admin import view_dates as adm_view
from app.handlers.client import book, browse, feedback, my_bookings, subscribe
from app.middlewares.user_ctx import UserCtxMiddleware
from app.utils.logging import setup_logging


async def main() -> None:
    setup_logging(settings.log_level)
    log = logging.getLogger(__name__)

    await init_db()
    log.info("db ready at %s", settings.db_path)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.outer_middleware(UserCtxMiddleware())

    dp.include_router(common.router)
    dp.include_router(adm_add_date.router)
    dp.include_router(adm_view.router)
    dp.include_router(adm_delete.router)
    dp.include_router(browse.router)
    dp.include_router(book.router)
    dp.include_router(my_bookings.router)
    dp.include_router(feedback.router)
    dp.include_router(subscribe.router)

    log.info("lubabot starting, admins=%s", sorted(settings.admin_usernames))
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
