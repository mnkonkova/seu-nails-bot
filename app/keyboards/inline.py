from collections.abc import Sequence
from datetime import date, time

from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

CLIENT_BROWSE = "📅 Свободные даты"
CLIENT_MY = "📋 Мои записи"
CLIENT_FEEDBACK = "✍ Оставить отзыв"
CLIENT_SUBSCRIBE = "🔔 Подписка"

ADMIN_ADD_DATE = "➕ Добавить дату"
ADMIN_VIEW_DATES = "📋 Активные даты"
ADMIN_DELETE = "🗑 Удалить"
ADMIN_BOOK_EXTERNAL = "📝 Записать клиента"


def client_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=CLIENT_BROWSE), KeyboardButton(text=CLIENT_MY)],
            [KeyboardButton(text=CLIENT_FEEDBACK), KeyboardButton(text=CLIENT_SUBSCRIBE)],
        ],
        resize_keyboard=True,
    )


def admin_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=ADMIN_ADD_DATE), KeyboardButton(text=ADMIN_VIEW_DATES)],
            [KeyboardButton(text=ADMIN_BOOK_EXTERNAL)],
            [KeyboardButton(text=ADMIN_DELETE)],
        ],
        resize_keyboard=True,
    )


def remove_kb() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


class DateCB(CallbackData, prefix="d"):
    action: str
    date_id: int


class SlotCB(CallbackData, prefix="s"):
    action: str
    slot_id: int


class ConfirmCB(CallbackData, prefix="c"):
    action: str  # 'yes' | 'no'
    kind: str    # 'book' | 'unbook' | 'deldate' | 'delslot'
    id: int


class DelModeCB(CallbackData, prefix="dm"):
    mode: str    # 'whole' | 'slots'
    date_id: int


class SubCB(CallbackData, prefix="sub"):
    action: str  # 'on' | 'off'


class HourCB(CallbackData, prefix="h"):
    action: str  # 'toggle' | 'all' | 'none' | 'done'
    hour: int    # 0 when action != 'toggle'


def dates_kb(rows: Sequence[tuple[int, date, int, int]], action: str) -> InlineKeyboardMarkup:
    """rows: (date_id, day, free, total)."""
    buttons = [
        [
            InlineKeyboardButton(
                text=f"{day.strftime('%d.%m.%Y')} — свободно {free}/{total}",
                callback_data=DateCB(action=action, date_id=date_id).pack(),
            )
        ]
        for date_id, day, free, total in rows
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def slots_kb(slots: Sequence[tuple[int, time, bool]], action: str) -> InlineKeyboardMarkup:
    """slots: (slot_id, time, is_booked). Booked slots shown with 🔒."""
    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for slot_id, t, booked in slots:
        label = t.strftime("%H:%M") + (" 🔒" if booked else "")
        row.append(
            InlineKeyboardButton(
                text=label,
                callback_data=SlotCB(action=action, slot_id=slot_id).pack(),
            )
        )
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def del_mode_kb(date_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗑 Удалить дату целиком",
                    callback_data=DelModeCB(mode="whole", date_id=date_id).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🕒 Удалить отдельное окно",
                    callback_data=DelModeCB(mode="slots", date_id=date_id).pack(),
                )
            ],
        ]
    )


def confirm_kb(kind: str, target_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить",
                    callback_data=ConfirmCB(action="yes", kind=kind, id=target_id).pack(),
                ),
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data=ConfirmCB(action="no", kind=kind, id=target_id).pack(),
                ),
            ]
        ]
    )


def hours_picker_kb(all_hours: Sequence[int], selected: set[int]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for h in all_hours:
        mark = "✓ " if h in selected else ""
        row.append(
            InlineKeyboardButton(
                text=f"{mark}{h:02d}:00",
                callback_data=HourCB(action="toggle", hour=h).pack(),
            )
        )
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(
        [
            InlineKeyboardButton(text="Все", callback_data=HourCB(action="all", hour=0).pack()),
            InlineKeyboardButton(text="Сброс", callback_data=HourCB(action="none", hour=0).pack()),
            InlineKeyboardButton(
                text=f"✅ Готово ({len(selected)})",
                callback_data=HourCB(action="done", hour=0).pack(),
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def subscribe_kb(currently_on: bool) -> InlineKeyboardMarkup:
    if currently_on:
        btn = InlineKeyboardButton(
            text="🔕 Отписаться", callback_data=SubCB(action="off").pack()
        )
    else:
        btn = InlineKeyboardButton(
            text="🔔 Подписаться", callback_data=SubCB(action="on").pack()
        )
    return InlineKeyboardMarkup(inline_keyboard=[[btn]])
