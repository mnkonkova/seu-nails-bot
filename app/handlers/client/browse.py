from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.db import SlotDateRepo, SlotRepo, session_scope
from app.keyboards.inline import CLIENT_BROWSE, DateCB, dates_kb, slots_kb
from app.utils.dates import fmt_date, today_msk

router = Router(name="client.browse")


@router.message(Command("browse"))
@router.message(F.text == CLIENT_BROWSE)
async def show_free_dates(message: Message) -> None:
    today = today_msk()
    async with session_scope() as s:
        dates = await SlotDateRepo(s).list_active(today)
        rows: list[tuple[int, object, int, int]] = []
        for d in dates:
            total = len(d.slots)
            free = sum(1 for sl in d.slots if sl.booked_by_tg_id is None)
            if free > 0:
                rows.append((d.id, d.date, free, total))  # type: ignore[arg-type]
    if not rows:
        await message.answer("Свободных дат пока нет. Можешь /subscribe, чтобы узнать о новых.")
        return
    await message.answer(
        "Выбери дату:",
        reply_markup=dates_kb(rows, action="browse"),  # type: ignore[arg-type]
    )


@router.callback_query(DateCB.filter(F.action == "browse"))
async def show_slots(cq: CallbackQuery, callback_data: DateCB) -> None:
    async with session_scope() as s:
        date_rec = await SlotDateRepo(s).get(callback_data.date_id)
        if date_rec is None:
            await cq.answer("Эта дата уже недоступна.", show_alert=True)
            return
        free = await SlotRepo(s).list_free_by_date(date_rec.id)
    if not free:
        await cq.message.edit_text(  # type: ignore[union-attr]
            f"<b>{fmt_date(date_rec.date)}</b> — свободных окон не осталось."
        )
        await cq.answer()
        return
    items = [(sl.id, sl.time, False) for sl in free]
    await cq.message.edit_text(  # type: ignore[union-attr]
        f"Свободные окна на <b>{fmt_date(date_rec.date)}</b>:",
        reply_markup=slots_kb(items, action="pick_book"),
    )
    await cq.answer()
