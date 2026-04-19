import logging
from collections.abc import Sequence
from datetime import date

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


async def create_date(day: date, hours: Sequence[int]) -> SlotDate:
    """Create a new date with the given hours as slots + a matching Sheets tab.

    Sheet is created first (external, can fail). On DB failure we best-effort
    delete the orphan sheet. Broadcast to subscribers is the handler's job.
    """
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


async def delete_date(date_id: int) -> bool:
    """Delete a date and all its slots (DB cascade) + the Sheets tab atomically."""
    async with session_scope() as s:
        date_rec = await SlotDateRepo(s).get(date_id)
        if date_rec is None:
            return False
        sheet_id = date_rec.sheet_id
        await SlotDateRepo(s).delete(date_id)
        await sheets.delete_sheet(sheet_id)
        return True


async def delete_slot(slot_id: int) -> bool:
    """Delete one slot, shift row_index for later slots, delete the Sheets row."""
    async with session_scope() as s:
        slot = await SlotRepo(s).get(slot_id)
        if slot is None:
            return False
        date_rec = await SlotDateRepo(s).get(slot.date_id)
        if date_rec is None:
            return False
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
        return True


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
