from collections.abc import Sequence
from datetime import UTC, date, datetime, time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Feedback, Slot, SlotDate, User


class SlotNotFound(Exception):
    def __init__(self, slot_id: int) -> None:
        super().__init__(f"Slot {slot_id} not found")
        self.slot_id = slot_id


class AlreadyBooked(Exception):
    def __init__(self, slot_id: int) -> None:
        super().__init__(f"Slot {slot_id} is already booked")
        self.slot_id = slot_id


class NotYourBooking(Exception):
    def __init__(self, slot_id: int) -> None:
        super().__init__(f"Slot {slot_id} is not booked by this user")
        self.slot_id = slot_id


class DateAlreadyExists(Exception):
    def __init__(self, day: date) -> None:
        super().__init__(f"Date {day.isoformat()} already has slots")
        self.day = day


class UserRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert(self, tg_id: int, username: str | None) -> User:
        user = await self.session.get(User, tg_id)
        normalized = username.lower() if username else None
        if user is None:
            user = User(tg_id=tg_id, username=normalized)
            self.session.add(user)
            await self.session.flush()
        elif user.username != normalized:
            user.username = normalized
            await self.session.flush()
        return user

    async def set_subscription(self, tg_id: int, enabled: bool) -> bool:
        user = await self.session.get(User, tg_id)
        if user is None:
            return False
        if user.subscribed_to_new_dates != enabled:
            user.subscribed_to_new_dates = enabled
            await self.session.flush()
        return True

    async def list_subscribers(self) -> Sequence[User]:
        stmt = select(User).where(User.subscribed_to_new_dates.is_(True))
        return (await self.session.execute(stmt)).scalars().all()


class SlotDateRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, day: date, sheet_id: int) -> SlotDate:
        existing = await self.get_by_date(day)
        if existing is not None:
            raise DateAlreadyExists(day)
        sd = SlotDate(date=day, sheet_id=sheet_id)
        self.session.add(sd)
        await self.session.flush()
        return sd

    async def get(self, date_id: int) -> SlotDate | None:
        return await self.session.get(SlotDate, date_id)

    async def get_by_date(self, day: date) -> SlotDate | None:
        stmt = select(SlotDate).where(SlotDate.date == day)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_active(self, today: date) -> Sequence[SlotDate]:
        stmt = select(SlotDate).where(SlotDate.date >= today).order_by(SlotDate.date)
        return (await self.session.execute(stmt)).scalars().all()

    async def list_past(self, today: date) -> Sequence[SlotDate]:
        stmt = select(SlotDate).where(SlotDate.date < today).order_by(SlotDate.date)
        return (await self.session.execute(stmt)).scalars().all()

    async def delete(self, date_id: int) -> bool:
        sd = await self.session.get(SlotDate, date_id)
        if sd is None:
            return False
        await self.session.delete(sd)
        return True


class SlotRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_bulk(
        self, date_id: int, hours: Sequence[int], first_row: int = 2
    ) -> list[Slot]:
        slots = [
            Slot(date_id=date_id, time=time(hour=h), row_index=first_row + i)
            for i, h in enumerate(hours)
        ]
        self.session.add_all(slots)
        await self.session.flush()
        return slots

    async def get(self, slot_id: int) -> Slot | None:
        return await self.session.get(Slot, slot_id)

    async def list_by_date(self, date_id: int) -> Sequence[Slot]:
        stmt = select(Slot).where(Slot.date_id == date_id).order_by(Slot.time)
        return (await self.session.execute(stmt)).scalars().all()

    async def list_free_by_date(self, date_id: int) -> Sequence[Slot]:
        stmt = (
            select(Slot)
            .where(Slot.date_id == date_id, Slot.booked_by_tg_id.is_(None))
            .order_by(Slot.time)
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def list_user_bookings(self, tg_id: int, today: date) -> Sequence[Slot]:
        stmt = (
            select(Slot)
            .join(SlotDate, Slot.date_id == SlotDate.id)
            .where(Slot.booked_by_tg_id == tg_id, SlotDate.date >= today)
            .order_by(SlotDate.date, Slot.time)
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def book(self, slot_id: int, tg_id: int) -> Slot:
        slot = await self.session.get(Slot, slot_id, with_for_update=True)
        if slot is None:
            raise SlotNotFound(slot_id)
        if slot.booked_by_tg_id is not None:
            raise AlreadyBooked(slot_id)
        slot.booked_by_tg_id = tg_id
        slot.booked_at = datetime.now(UTC)
        slot.external_client_name = None
        await self.session.flush()
        return slot

    async def book_for_external(
        self, slot_id: int, admin_tg_id: int, client_name: str
    ) -> Slot:
        slot = await self.session.get(Slot, slot_id, with_for_update=True)
        if slot is None:
            raise SlotNotFound(slot_id)
        if slot.booked_by_tg_id is not None:
            raise AlreadyBooked(slot_id)
        slot.booked_by_tg_id = admin_tg_id
        slot.external_client_name = client_name
        slot.booked_at = datetime.now(UTC)
        await self.session.flush()
        return slot

    async def unbook(self, slot_id: int, tg_id: int) -> Slot:
        slot = await self.session.get(Slot, slot_id, with_for_update=True)
        if slot is None:
            raise SlotNotFound(slot_id)
        if slot.booked_by_tg_id != tg_id:
            raise NotYourBooking(slot_id)
        slot.booked_by_tg_id = None
        slot.booked_at = None
        slot.external_client_name = None
        await self.session.flush()
        return slot


class FeedbackRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self, tg_id: int, text: str, sheet_row_index: int | None = None
    ) -> Feedback:
        fb = Feedback(tg_id=tg_id, text=text, sheet_row_index=sheet_row_index)
        self.session.add(fb)
        await self.session.flush()
        return fb

    async def list_by_user(self, tg_id: int) -> Sequence[Feedback]:
        stmt = (
            select(Feedback)
            .where(Feedback.tg_id == tg_id)
            .order_by(Feedback.created_at.desc())
        )
        return (await self.session.execute(stmt)).scalars().all()
