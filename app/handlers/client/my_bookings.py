import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.db import NotYourBooking, SlotDateRepo, SlotNotFound, SlotRepo, session_scope
from app.keyboards.inline import (
    CLIENT_MY,
    ConfirmCB,
    SlotCB,
    confirm_kb,
)
from app.services.booking import unbook_slot
from app.services.error_reporter import report_error
from app.utils.dates import fmt_date, today_msk

_log = logging.getLogger(__name__)

router = Router(name="client.my_bookings")


def _render_bookings(items: list[tuple[int, str, str, str | None]]) -> str:
    lines = ["<b>Твои записи:</b>"]
    for _, day_str, time_str, ext in items:
        line = f"• {day_str} — {time_str}"
        if ext:
            line += f" (клиент: {ext})"
        lines.append(line)
    return "\n".join(lines)


@router.message(Command("my"))
@router.message(F.text == CLIENT_MY)
async def show_my_bookings(message: Message) -> None:
    today = today_msk()
    async with session_scope() as s:
        slots = await SlotRepo(s).list_user_bookings(message.from_user.id, today)  # type: ignore[union-attr]
        if not slots:
            await message.answer("У тебя нет активных записей.")
            return
        items: list[tuple[int, str, str, str | None]] = []
        for sl in slots:
            date_rec = await SlotDateRepo(s).get(sl.date_id)
            items.append(
                (
                    sl.id,
                    fmt_date(date_rec.date),  # type: ignore[union-attr]
                    sl.time.strftime("%H:%M"),
                    sl.external_client_name,
                )
            )

    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    buttons = [
        [
            InlineKeyboardButton(
                text=f"❌ {d} {t}" + (f" ({ext[:20]})" if ext else ""),
                callback_data=SlotCB(action="cancel", slot_id=sid).pack(),
            )
        ]
        for sid, d, t, ext in items
    ]
    await message.answer(
        _render_bookings(items),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(SlotCB.filter(F.action == "cancel"))
async def confirm_cancel(cq: CallbackQuery, callback_data: SlotCB) -> None:
    async with session_scope() as s:
        slot = await SlotRepo(s).get(callback_data.slot_id)
        if slot is None or slot.booked_by_tg_id != cq.from_user.id:
            await cq.answer("Эта запись уже отменена.", show_alert=True)
            return
        date_rec = await SlotDateRepo(s).get(slot.date_id)
    await cq.message.edit_text(  # type: ignore[union-attr]
        f"Отменить запись на <b>{fmt_date(date_rec.date)}</b> "  # type: ignore[union-attr]
        f"в <b>{slot.time.strftime('%H:%M')}</b>?",
        reply_markup=confirm_kb(kind="unbook", target_id=callback_data.slot_id),
    )
    await cq.answer()


@router.callback_query(ConfirmCB.filter(F.kind == "unbook"))
async def on_confirm_unbook(cq: CallbackQuery, callback_data: ConfirmCB, bot: Bot) -> None:
    if callback_data.action == "no":
        await cq.message.edit_text("Ок, запись остаётся.")  # type: ignore[union-attr]
        await cq.answer()
        return
    try:
        await unbook_slot(callback_data.id, cq.from_user.id)
    except (SlotNotFound, NotYourBooking):
        await cq.message.edit_text("Эту запись нельзя отменить.")  # type: ignore[union-attr]
        await cq.answer()
        return
    except Exception as e:
        _log.exception("unbook_slot failed")
        await report_error(bot, e, where="client.my_bookings.on_confirm_unbook",
                           extra=f"slot_id={callback_data.id} tg_id={cq.from_user.id}")
        await cq.message.edit_text("Не получилось отменить. Попробуй ещё раз.")  # type: ignore[union-attr]
        await cq.answer()
        return
    await cq.message.edit_text("✅ Запись отменена.")  # type: ignore[union-attr]
    await cq.answer()
