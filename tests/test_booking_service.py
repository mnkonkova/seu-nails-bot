"""Service-layer tests: focus on the notification contract between
services.booking and the admin handlers.

Each scenario covers what push messages the handler layer is expected
to fire. Handlers themselves are thin: iterate over the returned
BookingNotification objects and call bot.send_message — tested indirectly
through tests/test_delete_handler_notify.py.
"""
from datetime import timedelta

import pytest

from app.db import NotBooked
from app.services.booking import (
    BookingNotification,
    admin_book_external,
    admin_clear_slot,
    book_slot,
    create_date,
    delete_date,
    delete_slot,
)
from app.utils.dates import today_msk


async def test_delete_date_returns_only_real_bookers(test_db):
    day = today_msk() + timedelta(days=30)
    date_rec = await create_date(day, [10, 11, 12])
    await book_slot(date_rec.slots[0].id, 111, "alice", "Alice", None)
    await book_slot(date_rec.slots[1].id, 222, "bob", "Bob", None)
    await admin_book_external(date_rec.slots[2].id, 999, "Петров")

    ok, notifications = await delete_date(date_rec.id)

    assert ok is True
    assert {n.tg_id for n in notifications} == {111, 222}
    # External booking (tg_id=999, ext_name set) must NOT be in notifications
    assert 999 not in {n.tg_id for n in notifications}
    # Each notification carries day and time
    assert all(n.day == day for n in notifications)
    assert {n.time.hour for n in notifications} == {10, 11}


async def test_delete_date_no_bookings_empty_list(test_db):
    day = today_msk() + timedelta(days=30)
    date_rec = await create_date(day, [10, 11])
    ok, notifications = await delete_date(date_rec.id)
    assert ok is True
    assert notifications == []


async def test_delete_date_missing_returns_false(test_db):
    ok, notifications = await delete_date(12345)
    assert ok is False
    assert notifications == []


async def test_delete_slot_real_booker_emits_notification(test_db):
    day = today_msk() + timedelta(days=30)
    date_rec = await create_date(day, [10])
    await book_slot(date_rec.slots[0].id, 111, "alice", "Alice", None)

    ok, notification = await delete_slot(date_rec.slots[0].id)

    assert ok is True
    assert notification is not None
    assert notification.tg_id == 111
    assert notification.day == day
    assert notification.time.hour == 10


async def test_delete_slot_external_no_notification(test_db):
    day = today_msk() + timedelta(days=30)
    date_rec = await create_date(day, [10])
    await admin_book_external(date_rec.slots[0].id, 999, "Петров")

    ok, notification = await delete_slot(date_rec.slots[0].id)

    assert ok is True
    assert notification is None  # external — don't push


async def test_delete_slot_empty_no_notification(test_db):
    day = today_msk() + timedelta(days=30)
    date_rec = await create_date(day, [10])
    ok, notification = await delete_slot(date_rec.slots[0].id)
    assert ok is True
    assert notification is None


async def test_admin_clear_slot_real_booker_emits_notification(test_db):
    day = today_msk() + timedelta(days=30)
    date_rec = await create_date(day, [10])
    await book_slot(date_rec.slots[0].id, 111, "alice", "Alice", None)

    returned_day, returned_time, notification = await admin_clear_slot(date_rec.slots[0].id)

    assert returned_day == day
    assert returned_time.hour == 10
    assert notification is not None
    assert notification.tg_id == 111
    assert notification.day == day
    assert notification.time.hour == 10


async def test_admin_clear_slot_external_no_notification(test_db):
    day = today_msk() + timedelta(days=30)
    date_rec = await create_date(day, [10])
    await admin_book_external(date_rec.slots[0].id, 999, "Петров")

    returned_day, returned_time, notification = await admin_clear_slot(date_rec.slots[0].id)

    assert returned_day == day
    assert returned_time.hour == 10
    assert notification is None


async def test_admin_clear_slot_already_empty_raises_notbooked(test_db):
    day = today_msk() + timedelta(days=30)
    date_rec = await create_date(day, [10])
    with pytest.raises(NotBooked):
        await admin_clear_slot(date_rec.slots[0].id)


async def test_admin_clear_slot_keeps_slot_rebookable(test_db):
    """After clearing, the same slot can be booked again."""
    day = today_msk() + timedelta(days=30)
    date_rec = await create_date(day, [10])
    slot_id = date_rec.slots[0].id
    await book_slot(slot_id, 111, "alice", None, None)
    await admin_clear_slot(slot_id)
    # Now someone else books it
    slot = await book_slot(slot_id, 222, "bob", "Bob", None)
    assert slot.booked_by_tg_id == 222
    assert slot.external_client_name is None


async def test_booking_notification_dataclass_shape():
    """Contract check: BookingNotification has exactly the fields
    handlers rely on when formatting the push text."""
    from datetime import date as date_cls, time as time_cls

    n = BookingNotification(tg_id=1, day=date_cls(2026, 4, 21), time=time_cls(10, 0))
    assert n.tg_id == 1
    assert n.day.isoformat() == "2026-04-21"
    assert n.time.strftime("%H:%M") == "10:00"
