from datetime import UTC, date, datetime, time

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    tg_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    subscribed_to_new_dates: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )


class SlotDate(Base):
    __tablename__ = "slot_dates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, unique=True, index=True, nullable=False)
    sheet_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    slots: Mapped[list["Slot"]] = relationship(
        back_populates="slot_date",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="Slot.time",
    )


class Slot(Base):
    __tablename__ = "slots"
    __table_args__ = (UniqueConstraint("date_id", "time", name="uq_slots_date_time"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date_id: Mapped[int] = mapped_column(
        ForeignKey("slot_dates.id", ondelete="CASCADE"), index=True, nullable=False
    )
    time: Mapped[time] = mapped_column(Time, nullable=False)
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    booked_by_tg_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.tg_id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    booked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    external_client_name: Mapped[str | None] = mapped_column(String(128), nullable=True)

    slot_date: Mapped[SlotDate] = relationship(back_populates="slots")


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.tg_id", ondelete="CASCADE"), index=True, nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    sheet_row_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
