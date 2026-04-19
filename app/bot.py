import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent

from app.config import settings
from app.db import init_db
from app.handlers import common
from app.handlers.admin import add_date as adm_add_date
from app.handlers.admin import book_external as adm_book_ext
from app.handlers.admin import delete as adm_delete
from app.handlers.admin import view_dates as adm_view
from app.handlers.client import book, browse, feedback, my_bookings, subscribe
from app.middlewares.user_ctx import UserCtxMiddleware
from app.services.error_reporter import report_error
from app.services.scheduler import create_scheduler, purge_past_dates
from app.utils.logging import setup_logging


async def main() -> None:
    setup_logging(settings.log_level)
    log = logging.getLogger(__name__)

    await init_db()
    log.info("db ready at %s", settings.db_path)

    try:
        await purge_past_dates()
    except Exception:
        log.exception("startup purge failed; continuing")

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.outer_middleware(UserCtxMiddleware())

    dp.include_router(common.router)
    dp.include_router(adm_add_date.router)
    dp.include_router(adm_view.router)
    dp.include_router(adm_book_ext.router)
    dp.include_router(adm_delete.router)
    dp.include_router(browse.router)
    dp.include_router(book.router)
    dp.include_router(my_bookings.router)
    dp.include_router(feedback.router)
    dp.include_router(subscribe.router)

    @dp.errors()
    async def on_global_error(event: ErrorEvent) -> None:
        upd_id = event.update.update_id if event.update is not None else "?"
        log.exception(
            "unhandled error on update=%s: %s", upd_id, event.exception
        )
        await report_error(bot, event.exception, where=f"unhandled:update={upd_id}")

    scheduler = create_scheduler(bot)
    scheduler.start()
    log.info("scheduler started; daily purge at 00:05 MSK")

    log.info("lubabot starting, admins=%s", sorted(settings.admin_usernames))
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()
