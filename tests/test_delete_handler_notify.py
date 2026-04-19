"""Handler-level contract: _notify() actually calls bot.send_message with
the right tg_id and swallows send errors so the admin flow doesn't break."""
from datetime import date, time
from unittest.mock import AsyncMock

import pytest

from app.handlers.admin.delete import _notify
from app.services.booking import BookingNotification


async def test_notify_calls_send_message_with_booker_id():
    bot = AsyncMock()
    n = BookingNotification(tg_id=111, day=date(2026, 4, 21), time=time(10, 0))
    await _notify(bot, n, reason="окно удалено", admin_id=999)
    bot.send_message.assert_awaited_once()
    args, kwargs = bot.send_message.call_args
    assert args[0] == 111  # booker tg_id
    body = args[1]
    assert "21.04.2026" in body
    assert "10:00" in body
    assert "окно удалено" in body


async def test_notify_skips_when_admin_is_booker():
    """Self-cancel: admin cleared their own booking → no self-push."""
    bot = AsyncMock()
    n = BookingNotification(tg_id=999, day=date(2026, 4, 21), time=time(10, 0))
    await _notify(bot, n, reason="окно освобождено", admin_id=999)
    bot.send_message.assert_not_awaited()


async def test_notify_swallows_send_errors():
    """If Telegram rejects (blocked bot, deactivated chat, …) the admin UX
    must not break. We log and continue."""
    bot = AsyncMock()
    bot.send_message.side_effect = RuntimeError("tg api explodes")
    n = BookingNotification(tg_id=111, day=date(2026, 4, 21), time=time(10, 0))
    # Must not raise
    await _notify(bot, n, reason="дата отменена", admin_id=999)
    bot.send_message.assert_awaited_once()
