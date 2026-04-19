import asyncio
import logging
from datetime import date

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.config import SLOT_HOURS
from app.db import DateAlreadyExists
from app.keyboards.inline import (
    ADMIN_ADD_DATE,
    HourCB,
    admin_menu,
    hours_picker_kb,
    remove_kb,
)
from app.middlewares.admin_only import AdminFilter
from app.services.booking import create_date
from app.services.notify import broadcast_new_date
from app.utils.dates import fmt_date, parse_date, today_msk

_log = logging.getLogger(__name__)

router = Router(name="admin.add_date")
router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())


class AddDate(StatesGroup):
    waiting_for_date = State()
    picking_hours = State()


@router.message(Command("add"))
@router.message(F.text == ADMIN_ADD_DATE)
async def start_add_date(message: Message, state: FSMContext) -> None:
    await state.set_state(AddDate.waiting_for_date)
    await message.answer(
        "Введи дату (например <code>21.04</code>, <code>21.04.2026</code> или <code>2026-04-21</code>).\n"
        "/cancel — отмена.",
        reply_markup=remove_kb(),
    )


@router.message(AddDate.waiting_for_date)
async def receive_date(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    day = parse_date(text)
    if day is None:
        await message.answer("Не распознал дату. Повтори в формате <code>ДД.ММ</code> или /cancel.")
        return
    if day < today_msk():
        await message.answer("Дата в прошлом. Введи другую или /cancel.")
        return
    selected = list(SLOT_HOURS)
    await state.set_state(AddDate.picking_hours)
    await state.update_data(day=day.isoformat(), selected=selected)
    await message.answer(
        f"Выбери окна для <b>{fmt_date(day)}</b>. По умолчанию все 08:00–22:00, сними лишние и жми «Готово».",
        reply_markup=hours_picker_kb(SLOT_HOURS, set(selected)),
    )


async def _refresh_kb(cq: CallbackQuery, selected: set[int]) -> None:
    try:
        await cq.message.edit_reply_markup(  # type: ignore[union-attr]
            reply_markup=hours_picker_kb(SLOT_HOURS, selected)
        )
    except TelegramBadRequest:
        pass


@router.callback_query(AddDate.picking_hours, HourCB.filter(F.action == "toggle"))
async def on_toggle_hour(cq: CallbackQuery, callback_data: HourCB, state: FSMContext) -> None:
    data = await state.get_data()
    selected = set(data.get("selected", []))
    if callback_data.hour in selected:
        selected.discard(callback_data.hour)
    else:
        selected.add(callback_data.hour)
    await state.update_data(selected=sorted(selected))
    await _refresh_kb(cq, selected)
    await cq.answer()


@router.callback_query(AddDate.picking_hours, HourCB.filter(F.action == "all"))
async def on_pick_all(cq: CallbackQuery, state: FSMContext) -> None:
    selected = set(SLOT_HOURS)
    await state.update_data(selected=sorted(selected))
    await _refresh_kb(cq, selected)
    await cq.answer()


@router.callback_query(AddDate.picking_hours, HourCB.filter(F.action == "none"))
async def on_pick_none(cq: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(selected=[])
    await _refresh_kb(cq, set())
    await cq.answer()


@router.callback_query(AddDate.picking_hours, HourCB.filter(F.action == "done"))
async def on_done(cq: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    selected: list[int] = sorted(set(data.get("selected", [])))
    if not selected:
        await cq.answer("Выбери хотя бы одно окно.", show_alert=True)
        return
    day = date.fromisoformat(data["day"])
    try:
        date_rec = await create_date(day, selected)
    except DateAlreadyExists:
        await state.clear()
        await cq.message.edit_text(f"Дата {fmt_date(day)} уже существует.")  # type: ignore[union-attr]
        await cq.answer()
        return
    except Exception:
        _log.exception("create_date failed for %s", day)
        await state.clear()
        await cq.message.edit_text("Не получилось создать дату (ошибка Sheets или БД).")  # type: ignore[union-attr]
        await cq.message.answer("Админ-меню:", reply_markup=admin_menu())  # type: ignore[union-attr]
        await cq.answer()
        return

    await state.clear()
    await cq.message.edit_text(  # type: ignore[union-attr]
        f"✅ Дата <b>{fmt_date(day)}</b> создана, окон: {len(date_rec.slots)}.\n"
        "Подписчики получают уведомление…"
    )
    await cq.message.answer("Админ-меню:", reply_markup=admin_menu())  # type: ignore[union-attr]
    await cq.answer()
    asyncio.create_task(_broadcast_safely(bot, day))


async def _broadcast_safely(bot: Bot, day: date) -> None:
    try:
        stats = await broadcast_new_date(bot, day)
        _log.info("broadcast done for %s: %s", day, stats)
    except Exception:
        _log.exception("broadcast failed for %s", day)
