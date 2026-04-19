"""Push unexpected exceptions to a designated admin in Telegram.

Target is resolved by username (settings.error_report_username) via the
users table — the admin must have /start-ed the bot at least once so their
tg_id is known. If not, we log and silently skip.

All errors are swallowed: the reporter must never raise and must never
cascade into the path that was already dealing with a failure.
"""
import html
import logging
import traceback

from aiogram import Bot
from sqlalchemy import select

from app.config import settings
from app.db import session_scope
from app.db.models import User

_log = logging.getLogger(__name__)

_MAX_TG_MESSAGE = 4000  # <4096 — leave budget for closing tags
_MAX_TB = 3000


async def _resolve_target_tg_id() -> int | None:
    target = settings.error_report_username.lower().lstrip("@")
    try:
        async with session_scope() as s:
            stmt = select(User).where(User.username == target)
            user = (await s.execute(stmt)).scalar_one_or_none()
            return user.tg_id if user is not None else None
    except Exception:
        _log.exception("error_reporter: failed to resolve target tg_id")
        return None


def _format(exc: BaseException, where: str, extra: str | None) -> str:
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    if len(tb) > _MAX_TB:
        tb = "…\n" + tb[-_MAX_TB:]
    parts = [
        "🚨 <b>Ошибка в боте</b>",
        f"📍 <b>Где:</b> <code>{html.escape(where)}</code>",
        f"❗ <b>Что:</b> <code>{html.escape(f'{type(exc).__name__}: {exc}')}</code>",
    ]
    if extra:
        parts.append(f"ℹ️ {html.escape(extra)}")
    parts.append(f"<pre>{html.escape(tb)}</pre>")
    text = "\n\n".join(parts)
    if len(text) > _MAX_TG_MESSAGE:
        text = text[: _MAX_TG_MESSAGE - 10] + "…</pre>"
    return text


async def report_error(
    bot: Bot, exc: BaseException, *, where: str = "?", extra: str | None = None
) -> None:
    """Notify the designated admin about an exception. Never raises."""
    try:
        tg_id = await _resolve_target_tg_id()
        if tg_id is None:
            _log.warning(
                "error_reporter: no target tg_id; user '%s' has not /start-ed yet",
                settings.error_report_username,
            )
            return
        await bot.send_message(tg_id, _format(exc, where, extra))
    except Exception:
        _log.exception("error_reporter: failed to send error report")
