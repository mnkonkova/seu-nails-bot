import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, time

from sqlalchemy import update

from app.db import (
    Feedback,
    FeedbackRepo,
    Slot,
    SlotDate,
    SlotDateRepo,
    SlotNotFound,
    SlotRepo,
    UserRepo,
    session_scope,
)
from app.db.models import Slot as SlotModel
from app.sheets import service as sheets

_log = logging.getLogger(__name__)


@dataclass(slots=True)
class BookingNotification:
    """Info needed to notify a real TG booker that their booking was cancelled."""

    tg_id: int
    day: date
    time: time


async def create_date(day: date, hours: Sequence[int]) -> SlotDate:
    """Create a new date with the given hours as slots + a matching Sheets tab."""
    sheet_id = await sheets.create_sheet_for_date(day, hours)
    try:
        async with session_scope() as s:
            date_rec = await SlotDateRepo(s).create(day, sheet_id)
            await SlotRepo(s).create_bulk(date_rec.id, hours)
            await s.refresh(date_rec, attribute_names=["slots"])
            return date_rec
    except Exception:
        _log.exception("create_date DB failed, cleaning up sheet %s", sheet_id)
        try:
            await sheets.delete_sheet(sheet_id)
        except Exception:
            _log.exception("orphan sheet %s cleanup failed", sheet_id)
        raise


async def delete_date(date_id: int) -> tuple[bool, list[BookingNotification]]:
    """Delete a date + sheet tab. Returns (ok, notifications) — one entry per real
    (non-external) booker so the caller can push them a message."""
    async with session_scope() as s:
        date_rec = await SlotDateRepo(s).get(date_id)
        if date_rec is None:
            return False, []
        day = date_rec.date
        sheet_id = date_rec.sheet_id
        notifications = [
            BookingNotification(sl.booked_by_tg_id, day, sl.time)  # type: ignore[arg-type]
            for sl in date_rec.slots
            if sl.booked_by_tg_id is not None and sl.external_client_name is None
        ]
        await SlotDateRepo(s).delete(date_id)
        await sheets.delete_sheet(sheet_id)
    return True, notifications


async def delete_slot(slot_id: int) -> tuple[bool, BookingNotification | None]:
    """Delete a single slot, shift later rows. Returns (ok, notification) —
    notification is set if a real TG user was booked."""
    async with session_scope() as s:
        slot = await SlotRepo(s).get(slot_id)
        if slot is None:
            return False, None
        date_rec = await SlotDateRepo(s).get(slot.date_id)
        if date_rec is None:
            return False, None
        slot_time = slot.time
        slot_day = date_rec.date
        booker_tg_id = slot.booked_by_tg_id
        external_name = slot.external_client_name
        sheet_id = date_rec.sheet_id
        row_index = slot.row_index
        date_id = slot.date_id
        await s.delete(slot)
        await s.flush()
        await s.execute(
            update(SlotModel)
            .where(SlotModel.date_id == date_id, SlotModel.row_index > row_index)
            .values(row_index=SlotModel.row_index - 1)
        )
        await sheets.delete_row(sheet_id, row_index)
    notification = None
    if booker_tg_id is not None and external_name is None:
        notification = BookingNotification(booker_tg_id, slot_day, slot_time)
    return True, notification


async def book_slot(
    slot_id: int,
    tg_id: int,
    username: str | None,
    first_name: str | None = None,
    last_name: str | None = None,
) -> Slot:
    """Atomically mark slot as booked in DB and mirror to Sheets."""
    async with session_scope() as s:
        await UserRepo(s).upsert(tg_id, username)
        slot = await SlotRepo(s).book(slot_id, tg_id)
        date_rec = await SlotDateRepo(s).get(slot.date_id)
        if date_rec is None:
            raise SlotNotFound(slot_id)
        await sheets.write_booking(
            date_rec.sheet_id,
            slot.row_index,
            username,
            tg_id,
            first_name,
            last_name,
            slot.booked_at,  # type: ignore[arg-type]
        )
        return slot


async def admin_book_external(slot_id: int, admin_tg_id: int, client_name: str) -> Slot:
    """Admin books a slot on behalf of an offline client. No hyperlink in Sheets."""
    async with session_scope() as s:
        slot = await SlotRepo(s).book_for_external(slot_id, admin_tg_id, client_name)
        date_rec = await SlotDateRepo(s).get(slot.date_id)
        if date_rec is None:
            raise SlotNotFound(slot_id)
        await sheets.write_booking_external(
            date_rec.sheet_id, slot.row_index, client_name, slot.booked_at  # type: ignore[arg-type]
        )
        return slot


async def admin_clear_slot(
    slot_id: int,
) -> tuple[date, time, BookingNotification | None]:
    """Admin force-clears a booking; slot stays rebookable. Returns (day, time,
    notification) where notification is set iff a real TG user (not external)
    was booked."""
    async with session_scope() as s:
        existing = await SlotRepo(s).get(slot_id)
        if existing is None:
            raise SlotNotFound(slot_id)
        former_tg_id = existing.booked_by_tg_id
        former_ext = existing.external_client_name
        slot_time = existing.time
        slot = await SlotRepo(s).clear(slot_id)
        date_rec = await SlotDateRepo(s).get(slot.date_id)
        if date_rec is None:
            raise SlotNotFound(slot_id)
        slot_day = date_rec.date
        await sheets.clear_booking(date_rec.sheet_id, slot.row_index)
    notification = None
    if former_tg_id is not None and former_ext is None:
        notification = BookingNotification(former_tg_id, slot_day, slot_time)
    return slot_day, slot_time, notification


async def unbook_slot(slot_id: int, tg_id: int) -> Slot:
    """Atomically free the slot in DB and clear the Sheets row cells."""
    async with session_scope() as s:
        slot = await SlotRepo(s).unbook(slot_id, tg_id)
        date_rec = await SlotDateRepo(s).get(slot.date_id)
        if date_rec is None:
            raise SlotNotFound(slot_id)
        await sheets.clear_booking(date_rec.sheet_id, slot.row_index)
        return slot


async def submit_feedback(
    tg_id: int,
    username: str | None,
    text: str,
    first_name: str | None = None,
    last_name: str | None = None,
) -> Feedback:
    """Persist feedback to DB and append to the Feedback sheet."""
    async with session_scope() as s:
        await UserRepo(s).upsert(tg_id, username)
        fb = await FeedbackRepo(s).create(tg_id, text)
        row_idx = await sheets.append_feedback(
            username, tg_id, first_name, last_name, text, fb.created_at
        )
        if row_idx is not None:
            fb.sheet_row_index = row_idx
            await s.flush()
        return fb
