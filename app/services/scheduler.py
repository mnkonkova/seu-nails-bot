import logging

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.db import SlotDateRepo, session_scope
from app.services.booking import delete_date
from app.services.error_reporter import report_error
from app.utils.dates import MSK, today_msk

_log = logging.getLogger(__name__)


async def purge_past_dates(bot: Bot | None = None) -> None:
    """Drop every date < today (MSK) from DB and Google Sheets."""
    today = today_msk()
    async with session_scope() as s:
        past = await SlotDateRepo(s).list_past(today)
        items = [(d.id, d.date) for d in past]
    if not items:
        _log.info("scheduler: no past dates to purge")
        return
    _log.info("scheduler: purging %d past dates", len(items))
    for date_id, day in items:
        try:
            ok, _notifications = await delete_date(date_id)  # past dates: skip notify
            if ok:
                _log.info("scheduler: purged %s (id=%d)", day, date_id)
        except Exception as e:
            _log.exception("scheduler: failed to purge %s (id=%d)", day, date_id)
            if bot is not None:
                await report_error(
                    bot, e, where="scheduler.purge_past_dates",
                    extra=f"date_id={date_id} day={day}",
                )


def create_scheduler(bot: Bot | None = None) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=MSK)
    scheduler.add_job(
        purge_past_dates,
        trigger=CronTrigger(hour=0, minute=5, timezone=MSK),
        id="purge_past_dates",
        name="Daily purge of past dates",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
        kwargs={"bot": bot},
    )
    return scheduler
