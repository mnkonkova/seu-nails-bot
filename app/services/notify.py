import asyncio
import logging
from dataclasses import dataclass
from datetime import date

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

from app.db import UserRepo, session_scope
from app.services.error_reporter import report_error

_log = logging.getLogger(__name__)
_SEND_INTERVAL = 0.05  # ~20 msg/s, well under Telegram's 30/s global broadcast cap


@dataclass(slots=True)
class BroadcastStats:
    sent: int = 0
    failed: int = 0
    unsubscribed: int = 0


def _render_new_date(day: date) -> str:
    return (
        f"📅 Открыта запись на <b>{day.strftime('%d.%m.%Y')}</b>.\n"
        "Посмотреть свободные окна: /browse"
    )


async def _send_one(bot: Bot, tg_id: int, text: str, stats: BroadcastStats) -> None:
    try:
        await bot.send_message(tg_id, text)
        stats.sent += 1
    except TelegramForbiddenError:
        async with session_scope() as s:
            await UserRepo(s).set_subscription(tg_id, False)
        stats.unsubscribed += 1
        _log.info("auto-unsubscribed blocked user tg_id=%s", tg_id)
    except TelegramRetryAfter as e:
        _log.warning("flood wait %ss for tg_id=%s", e.retry_after, tg_id)
        await asyncio.sleep(e.retry_after)
        try:
            await bot.send_message(tg_id, text)
            stats.sent += 1
        except Exception:
            _log.exception("broadcast retry failed for tg_id=%s", tg_id)
            stats.failed += 1
    except Exception:
        _log.exception("broadcast failed for tg_id=%s", tg_id)
        stats.failed += 1


async def broadcast_new_date(bot: Bot, day: date) -> BroadcastStats:
    async with session_scope() as s:
        subs = await UserRepo(s).list_subscribers()
        tg_ids = [u.tg_id for u in subs]
    stats = BroadcastStats()
    if not tg_ids:
        return stats
    text = _render_new_date(day)
    for tg_id in tg_ids:
        await _send_one(bot, tg_id, text, stats)
        await asyncio.sleep(_SEND_INTERVAL)
    _log.info(
        "broadcast day=%s total=%d sent=%d failed=%d unsubscribed=%d",
        day, len(tg_ids), stats.sent, stats.failed, stats.unsubscribed,
    )
    if stats.failed > 0:
        try:
            await report_error(
                bot,
                RuntimeError(f"broadcast failed for {stats.failed}/{len(tg_ids)} users"),
                where="notify.broadcast_new_date",
                extra=f"day={day} sent={stats.sent} failed={stats.failed}",
            )
        except Exception:
            _log.exception("failed to send broadcast error report")
    return stats
