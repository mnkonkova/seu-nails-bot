import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.db import AlreadyBooked, SlotDateRepo, SlotNotFound, SlotRepo, session_scope
from app.keyboards.inline import (
    ADMIN_BOOK_EXTERNAL,
    ConfirmCB,
    DateCB,
    SlotCB,
    admin_menu,
    confirm_kb,
    dates_kb,
    slots_kb,
)
from app.middlewares.admin_only import AdminFilter
from app.services.booking import admin_book_external
from app.utils.dates import fmt_date, today_msk

_log = logging.getLogger(__name__)

router = Router(name="admin.book_external")
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())

NAME_MAX = 120


class ExtBook(StatesGroup):
    waiting_for_name = State()


@router.message(Command("adminbook"))
@router.message(F.text == ADMIN_BOOK_EXTERNAL)
async def pick_date(message: Message, state: FSMContext) -> None:
    await state.clear()
    today = today_msk()
    async with session_scope() as s:
        dates = await SlotDateRepo(s).list_active(today)
        rows = [
            (d.id, d.date, sum(1 for sl in d.slots if sl.booked_by_tg_id is None), len(d.slots))
            for d in dates
        ]
    rows = [r for r in rows if r[2] > 0]
    if not rows:
        await message.answer("Нет дат со свободными окнами.")
        return
    await message.answer("Выбери дату:", reply_markup=dates_kb(rows, action="adm_book_pick"))


@router.callback_query(DateCB.filter(F.action == "adm_book_pick"))
async def pick_slot(cq: CallbackQuery, callback_data: DateCB) -> None:
    async with session_scope() as s:
        date_rec = await SlotDateRepo(s).get(callback_data.date_id)
        if date_rec is None:
            await cq.answer("Дата уже удалена.", show_alert=True)
            return
        free = await SlotRepo(s).list_free_by_date(date_rec.id)
    if not free:
        await cq.message.edit_text(  # type: ignore[union-attr]
            f"На {fmt_date(date_rec.date)} нет свободных окон."
        )
        await cq.answer()
        return
    items = [(sl.id, sl.time, False) for sl in free]
    await cq.message.edit_text(  # type: ignore[union-attr]
        f"<b>{fmt_date(date_rec.date)}</b>. Выбери окно:",
        reply_markup=slots_kb(items, action="adm_book_ext"),
    )
    await cq.answer()


@router.callback_query(SlotCB.filter(F.action == "adm_book_ext"))
async def ask_for_name(
    cq: CallbackQuery, callback_data: SlotCB, state: FSMContext
) -> None:
    async with session_scope() as s:
        slot = await SlotRepo(s).get(callback_data.slot_id)
        if slot is None or slot.booked_by_tg_id is not None:
            await cq.answer("Это окно уже занято.", show_alert=True)
            return
        date_rec = await SlotDateRepo(s).get(slot.date_id)
    await state.set_state(ExtBook.waiting_for_name)
    await state.update_data(
        slot_id=callback_data.slot_id,
        day=fmt_date(date_rec.date),  # type: ignore[union-attr]
        time=slot.time.strftime("%H:%M"),
    )
    await cq.message.edit_text(  # type: ignore[union-attr]
        f"Записываешь клиента на <b>{fmt_date(date_rec.date)} "  # type: ignore[union-attr]
        f"{slot.time.strftime('%H:%M')}</b>.\n"
        "Пришли имя клиента (как будет видно в таблице). /cancel — отмена."
    )
    await cq.answer()


@router.message(ExtBook.waiting_for_name)
async def receive_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer("Нужно непустое имя. Пришли ещё раз или /cancel.")
        return
    if len(name) > NAME_MAX:
        await message.answer(
            f"Слишком длинно ({len(name)}>{NAME_MAX}). Сократи и пришли снова."
        )
        return
    data = await state.get_data()
    await state.update_data(client_name=name)
    await message.answer(
        f"Записать <b>{name}</b> на <b>{data['day']} {data['time']}</b>?",
        reply_markup=confirm_kb(kind="bookext", target_id=int(data["slot_id"])),
    )


@router.callback_query(ExtBook.waiting_for_name, ConfirmCB.filter(F.kind == "bookext"))
async def on_confirm(
    cq: CallbackQuery, callback_data: ConfirmCB, state: FSMContext
) -> None:
    data = await state.get_data()
    if callback_data.action == "no":
        await state.clear()
        await cq.message.edit_text("Отменено.")  # type: ignore[union-attr]
        await cq.message.answer("Админ-меню:", reply_markup=admin_menu())  # type: ignore[union-attr]
        await cq.answer()
        return
    client_name = data.get("client_name")
    if not client_name:
        await state.clear()
        await cq.answer("Состояние потеряно, начни заново.", show_alert=True)
        return
    try:
        await admin_book_external(callback_data.id, cq.from_user.id, client_name)
    except AlreadyBooked:
        await state.clear()
        await cq.message.edit_text("Это окно уже заняли — не получилось.")  # type: ignore[union-attr]
        await cq.message.answer("Админ-меню:", reply_markup=admin_menu())  # type: ignore[union-attr]
        await cq.answer()
        return
    except SlotNotFound:
        await state.clear()
        await cq.message.edit_text("Окно больше не существует.")  # type: ignore[union-attr]
        await cq.message.answer("Админ-меню:", reply_markup=admin_menu())  # type: ignore[union-attr]
        await cq.answer()
        return
    except Exception:
        _log.exception("admin_book_external failed")
        await state.clear()
        await cq.message.edit_text(  # type: ignore[union-attr]
            "Не получилось записать (ошибка БД или Sheets)."
        )
        await cq.message.answer("Админ-меню:", reply_markup=admin_menu())  # type: ignore[union-attr]
        await cq.answer()
        return
    await state.clear()
    await cq.message.edit_text(  # type: ignore[union-attr]
        f"✅ <b>{client_name}</b> записан на {data['day']} {data['time']}."
    )
    await cq.message.answer("Админ-меню:", reply_markup=admin_menu())  # type: ignore[union-attr]
    await cq.answer()
