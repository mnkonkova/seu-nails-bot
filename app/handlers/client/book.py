import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from app.db import AlreadyBooked, SlotDateRepo, SlotNotFound, SlotRepo, session_scope
from app.keyboards.inline import ConfirmCB, SlotCB, confirm_kb
from app.services.booking import book_slot
from app.utils.dates import fmt_date

_log = logging.getLogger(__name__)

router = Router(name="client.book")


@router.callback_query(SlotCB.filter(F.action == "pick_book"))
async def show_agreement(cq: CallbackQuery, callback_data: SlotCB) -> None:
    async with session_scope() as s:
        slot = await SlotRepo(s).get(callback_data.slot_id)
        if slot is None or slot.booked_by_tg_id is not None:
            await cq.answer("Это окно уже занято.", show_alert=True)
            return
        date_rec = await SlotDateRepo(s).get(slot.date_id)
    await cq.message.edit_text(  # type: ignore[union-attr]
        f"Записаться на <b>{fmt_date(date_rec.date)}</b> в "  # type: ignore[union-attr]
        f"<b>{slot.time.strftime('%H:%M')}</b>?",
        reply_markup=confirm_kb(kind="book", target_id=callback_data.slot_id),
    )
    await cq.answer()


@router.callback_query(ConfirmCB.filter(F.kind == "book"))
async def on_confirm_book(cq: CallbackQuery, callback_data: ConfirmCB) -> None:
    if callback_data.action == "no":
        await cq.message.edit_text("Бронирование отменено.")  # type: ignore[union-attr]
        await cq.answer()
        return
    user = cq.from_user
    try:
        slot = await book_slot(
            callback_data.id, user.id, user.username, user.first_name, user.last_name
        )
    except AlreadyBooked:
        await cq.message.edit_text("Увы, это окно уже заняли.")  # type: ignore[union-attr]
        await cq.answer()
        return
    except SlotNotFound:
        await cq.message.edit_text("Окно больше не существует.")  # type: ignore[union-attr]
        await cq.answer()
        return
    except Exception:
        _log.exception("book_slot failed")
        await cq.message.edit_text("Не получилось записаться. Попробуй ещё раз.")  # type: ignore[union-attr]
        await cq.answer()
        return
    async with session_scope() as s:
        date_rec = await SlotDateRepo(s).get(slot.date_id)
    await cq.message.edit_text(  # type: ignore[union-attr]
        f"✅ Готово! Ты записан на <b>{fmt_date(date_rec.date)}</b> в "  # type: ignore[union-attr]
        f"<b>{slot.time.strftime('%H:%M')}</b>."
    )
    await cq.answer()
