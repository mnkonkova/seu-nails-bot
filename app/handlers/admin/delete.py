import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from app.db import NotBooked, SlotDateRepo, SlotRepo, session_scope
from app.db.models import User
from app.keyboards.inline import (
    ADMIN_DELETE,
    ConfirmCB,
    DateCB,
    DelModeCB,
    SlotCB,
    booked_slots_kb,
    confirm_kb,
    dates_kb,
    del_mode_kb,
    slots_kb,
)
from app.middlewares.admin_only import AdminFilter
from app.services.booking import (
    BookingNotification,
    admin_clear_slot,
    delete_date,
    delete_slot,
)
from app.utils.dates import fmt_date, today_msk

_log = logging.getLogger(__name__)

router = Router(name="admin.delete")
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())


async def _notify(bot: Bot, n: BookingNotification, reason: str, admin_id: int) -> None:
    """Send one cancellation push. Swallows errors — admin already got an OK."""
    if n.tg_id == admin_id:
        return
    try:
        await bot.send_message(
            n.tg_id,
            f"⚠️ Ваша запись на <b>{fmt_date(n.day)}</b> в "
            f"<b>{n.time.strftime('%H:%M')}</b> отменена администратором ({reason}).",
        )
    except Exception:
        _log.exception("failed to notify tg_id=%s", n.tg_id)


@router.message(Command("del"))
@router.message(F.text == ADMIN_DELETE)
async def pick_date_to_delete(message: Message) -> None:
    today = today_msk()
    async with session_scope() as s:
        dates = await SlotDateRepo(s).list_active(today)
        rows = [
            (d.id, d.date, sum(1 for sl in d.slots if sl.booked_by_tg_id is None), len(d.slots))
            for d in dates
        ]
    if not rows:
        await message.answer("Удалять нечего — активных дат нет.")
        return
    await message.answer("Выбери дату:", reply_markup=dates_kb(rows, action="adm_del_pick"))


@router.callback_query(DateCB.filter(F.action == "adm_del_pick"))
async def pick_mode(cq: CallbackQuery, callback_data: DateCB) -> None:
    async with session_scope() as s:
        date_rec = await SlotDateRepo(s).get(callback_data.date_id)
    if date_rec is None:
        await cq.answer("Дата уже удалена.", show_alert=True)
        return
    await cq.message.edit_text(  # type: ignore[union-attr]
        f"Что удалить для <b>{fmt_date(date_rec.date)}</b>?",
        reply_markup=del_mode_kb(callback_data.date_id),
    )
    await cq.answer()


@router.callback_query(DelModeCB.filter(F.mode == "whole"))
async def confirm_whole(cq: CallbackQuery, callback_data: DelModeCB) -> None:
    async with session_scope() as s:
        date_rec = await SlotDateRepo(s).get(callback_data.date_id)
    if date_rec is None:
        await cq.answer("Дата уже удалена.", show_alert=True)
        return
    await cq.message.edit_text(  # type: ignore[union-attr]
        f"Удалить дату <b>{fmt_date(date_rec.date)}</b> со всеми окнами?",
        reply_markup=confirm_kb(kind="deldate", target_id=callback_data.date_id),
    )
    await cq.answer()


def _booker_label(slot, users_by_id: dict[int, User]) -> str:
    if slot.external_client_name:
        return slot.external_client_name
    u = users_by_id.get(slot.booked_by_tg_id)
    if u is None:
        return f"id:{slot.booked_by_tg_id}"
    if u.username:
        return f"@{u.username}"
    name = " ".join(filter(None, [u.first_name, u.last_name]))
    return name or f"id:{u.tg_id}"


@router.callback_query(DelModeCB.filter(F.mode == "clear"))
async def show_booked_to_clear(cq: CallbackQuery, callback_data: DelModeCB) -> None:
    async with session_scope() as s:
        date_rec = await SlotDateRepo(s).get(callback_data.date_id)
        if date_rec is None:
            await cq.answer("Дата уже удалена.", show_alert=True)
            return
        booked = await SlotRepo(s).list_booked_by_date(date_rec.id)
        if not booked:
            await cq.message.edit_text(  # type: ignore[union-attr]
                f"На {fmt_date(date_rec.date)} нет занятых окон."
            )
            await cq.answer()
            return
        tg_ids = list({sl.booked_by_tg_id for sl in booked if sl.booked_by_tg_id is not None})
        users_by_id: dict[int, User] = {}
        if tg_ids:
            rows = await s.execute(select(User).where(User.tg_id.in_(tg_ids)))
            users_by_id = {u.tg_id: u for u in rows.scalars().all()}
        items = [(sl.id, sl.time, _booker_label(sl, users_by_id)) for sl in booked]
    await cq.message.edit_text(  # type: ignore[union-attr]
        f"Занятые окна на <b>{fmt_date(date_rec.date)}</b>. Выбери, какое освободить:",
        reply_markup=booked_slots_kb(items, action="adm_clear"),
    )
    await cq.answer()


@router.callback_query(SlotCB.filter(F.action == "adm_clear"))
async def confirm_clear(cq: CallbackQuery, callback_data: SlotCB) -> None:
    async with session_scope() as s:
        slot = await SlotRepo(s).get(callback_data.slot_id)
        if slot is None or slot.booked_by_tg_id is None:
            await cq.answer("Это окно уже свободно.", show_alert=True)
            return
        date_rec = await SlotDateRepo(s).get(slot.date_id)
    await cq.message.edit_text(  # type: ignore[union-attr]
        f"Освободить окно <b>{slot.time.strftime('%H:%M')}</b> на "
        f"{fmt_date(date_rec.date)}?",  # type: ignore[union-attr]
        reply_markup=confirm_kb(kind="clearslot", target_id=callback_data.slot_id),
    )
    await cq.answer()


@router.callback_query(ConfirmCB.filter(F.kind == "clearslot"))
async def on_confirm_clear(cq: CallbackQuery, callback_data: ConfirmCB, bot: Bot) -> None:
    if callback_data.action == "no":
        await cq.message.edit_text("Отменено.")  # type: ignore[union-attr]
        await cq.answer()
        return
    try:
        day, t, notification = await admin_clear_slot(callback_data.id)
    except NotBooked:
        await cq.message.edit_text("Это окно уже свободно.")  # type: ignore[union-attr]
        await cq.answer()
        return
    except Exception:
        _log.exception("admin_clear_slot failed")
        await cq.message.edit_text("Ошибка при освобождении окна.")  # type: ignore[union-attr]
        await cq.answer()
        return
    await cq.message.edit_text(  # type: ignore[union-attr]
        f"✅ Окно <b>{t.strftime('%H:%M')}</b> на {fmt_date(day)} освобождено."
    )
    await cq.answer()
    if notification is not None:
        await _notify(bot, notification, reason="окно освобождено", admin_id=cq.from_user.id)


@router.callback_query(DelModeCB.filter(F.mode == "slots"))
async def show_slots_for_deletion(cq: CallbackQuery, callback_data: DelModeCB) -> None:
    async with session_scope() as s:
        date_rec = await SlotDateRepo(s).get(callback_data.date_id)
        if date_rec is None:
            await cq.answer("Дата уже удалена.", show_alert=True)
            return
        slots = await SlotRepo(s).list_by_date(date_rec.id)
    if not slots:
        await cq.message.edit_text(f"У даты {fmt_date(date_rec.date)} нет окон.")  # type: ignore[union-attr]
        await cq.answer()
        return
    items = [(sl.id, sl.time, sl.booked_by_tg_id is not None) for sl in slots]
    await cq.message.edit_text(  # type: ignore[union-attr]
        f"Окна <b>{fmt_date(date_rec.date)}</b>. Выбери окно для удаления:",
        reply_markup=slots_kb(items, action="adm_del_slot"),
    )
    await cq.answer()


@router.callback_query(SlotCB.filter(F.action == "adm_del_slot"))
async def confirm_slot(cq: CallbackQuery, callback_data: SlotCB) -> None:
    async with session_scope() as s:
        slot = await SlotRepo(s).get(callback_data.slot_id)
        if slot is None:
            await cq.answer("Окно уже удалено.", show_alert=True)
            return
        date_rec = await SlotDateRepo(s).get(slot.date_id)
    warn = " (оно занято!)" if slot.booked_by_tg_id is not None else ""
    await cq.message.edit_text(  # type: ignore[union-attr]
        f"Удалить окно <b>{slot.time.strftime('%H:%M')}</b> на "
        f"{fmt_date(date_rec.date)}{warn}?",  # type: ignore[union-attr]
        reply_markup=confirm_kb(kind="delslot", target_id=callback_data.slot_id),
    )
    await cq.answer()


@router.callback_query(ConfirmCB.filter(F.kind == "deldate"))
async def on_confirm_deldate(cq: CallbackQuery, callback_data: ConfirmCB, bot: Bot) -> None:
    if callback_data.action == "no":
        await cq.message.edit_text("Отменено.")  # type: ignore[union-attr]
        await cq.answer()
        return
    try:
        ok, notifications = await delete_date(callback_data.id)
    except Exception:
        _log.exception("delete_date failed")
        await cq.message.edit_text("Ошибка при удалении (БД или Sheets).")  # type: ignore[union-attr]
        await cq.answer()
        return
    await cq.message.edit_text(  # type: ignore[union-attr]
        "✅ Удалено." if ok else "Дата уже была удалена."
    )
    await cq.answer()
    for n in notifications:
        await _notify(bot, n, reason="дата отменена", admin_id=cq.from_user.id)


@router.callback_query(ConfirmCB.filter(F.kind == "delslot"))
async def on_confirm_delslot(cq: CallbackQuery, callback_data: ConfirmCB, bot: Bot) -> None:
    if callback_data.action == "no":
        await cq.message.edit_text("Отменено.")  # type: ignore[union-attr]
        await cq.answer()
        return
    try:
        ok, notification = await delete_slot(callback_data.id)
    except Exception:
        _log.exception("delete_slot failed")
        await cq.message.edit_text("Ошибка при удалении (БД или Sheets).")  # type: ignore[union-attr]
        await cq.answer()
        return
    await cq.message.edit_text(  # type: ignore[union-attr]
        "✅ Окно удалено." if ok else "Окно уже было удалено."
    )
    await cq.answer()
    if notification is not None:
        await _notify(bot, notification, reason="окно удалено", admin_id=cq.from_user.id)
