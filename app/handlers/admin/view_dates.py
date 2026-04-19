from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from app.db import SlotDateRepo, session_scope
from app.keyboards.inline import ADMIN_VIEW_DATES
from app.middlewares.admin_only import AdminFilter
from app.utils.dates import fmt_date, today_msk

router = Router(name="admin.view_dates")
router.message.filter(AdminFilter())


@router.message(Command("dates"))
@router.message(F.text == ADMIN_VIEW_DATES)
async def show_dates(message: Message) -> None:
    today = today_msk()
    async with session_scope() as s:
        dates = await SlotDateRepo(s).list_active(today)
        if not dates:
            await message.answer("Активных дат нет.")
            return
        lines = []
        for d in dates:
            total = len(d.slots)
            free = sum(1 for sl in d.slots if sl.booked_by_tg_id is None)
            lines.append(f"• <b>{fmt_date(d.date)}</b> — свободно {free}/{total}")
    await message.answer("\n".join(lines))
