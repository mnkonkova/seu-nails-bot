"""Contract tests for error_reporter: resolve target tg_id by username,
format HTML-safe, send via bot, swallow every failure."""
from unittest.mock import AsyncMock

import pytest

from app.db import UserRepo, session_scope
from app.services import error_reporter


async def test_report_error_sends_to_resolved_admin(test_db, monkeypatch):
    async with session_scope() as s:
        await UserRepo(s).upsert(777, "mashakon")
    monkeypatch.setattr(
        "app.services.error_reporter.settings.error_report_username", "mashakon"
    )
    bot = AsyncMock()
    exc = RuntimeError("kaboom")
    await error_reporter.report_error(bot, exc, where="test.case", extra="slot_id=5")
    bot.send_message.assert_awaited_once()
    args, _ = bot.send_message.call_args
    assert args[0] == 777
    body = args[1]
    assert "RuntimeError" in body
    assert "kaboom" in body
    assert "test.case" in body
    assert "slot_id=5" in body


async def test_report_error_no_user_in_db_no_send(test_db, monkeypatch, caplog):
    # Nobody in DB → can't resolve target → log warning, don't crash, don't send
    monkeypatch.setattr(
        "app.services.error_reporter.settings.error_report_username", "mashakon"
    )
    bot = AsyncMock()
    import logging

    caplog.set_level(logging.WARNING)
    await error_reporter.report_error(bot, ValueError("x"), where="t")
    bot.send_message.assert_not_awaited()
    assert any("no target tg_id" in r.message for r in caplog.records)


async def test_report_error_swallows_send_failure(test_db, monkeypatch):
    """If Telegram rejects, we log but never raise."""
    async with session_scope() as s:
        await UserRepo(s).upsert(777, "mashakon")
    monkeypatch.setattr(
        "app.services.error_reporter.settings.error_report_username", "mashakon"
    )
    bot = AsyncMock()
    bot.send_message.side_effect = RuntimeError("tg api 500")
    # Must not raise
    await error_reporter.report_error(bot, ValueError("x"), where="t")
    bot.send_message.assert_awaited_once()


def test_format_escapes_html_in_exception():
    exc = ValueError("<script>alert('xss')</script>")
    text = error_reporter._format(exc, where="h & m", extra="a < b")
    # Injected markup must be escaped, not raw
    assert "<script>alert(" not in text
    assert "&lt;script&gt;" in text
    assert "h &amp; m" in text
    assert "a &lt; b" in text


def test_format_truncates_long_traceback():
    exc = RuntimeError("x")
    # Synthesize an oversized traceback-like string by nesting
    try:
        def deep(n):
            if n > 0:
                deep(n - 1)
            raise RuntimeError("x" * 5000)
        deep(50)
    except RuntimeError as e:
        exc = e
    text = error_reporter._format(exc, where="t", extra=None)
    assert len(text) <= 4000
    assert "RuntimeError" in text
