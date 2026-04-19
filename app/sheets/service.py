import asyncio
import logging
from collections.abc import Sequence
from datetime import date, datetime
from zoneinfo import ZoneInfo

from gspread.exceptions import WorksheetNotFound

from app.config import TIMEZONE
from app.sheets.client import get_spreadsheet, parse_row_from_range, retryable

_log = logging.getLogger(__name__)
_MSK = ZoneInfo(TIMEZONE)

DATE_HEADER = ["Время", "Кто записан", "Время записи"]
FEEDBACK_SHEET_NAME = "Feedback"
FEEDBACK_HEADER = ["Дата", "TG", "Текст"]

_HEADER_FMT = {"textFormat": {"bold": True}}
_TS_FMT = "%Y-%m-%d %H:%M"


def _user_cell(username: str | None, tg_id: int) -> str:
    if username:
        clean = username.lstrip("@")
        return f'=HYPERLINK("https://t.me/{clean}","@{clean}")'
    return f"id:{tg_id}"


def _to_msk(dt: datetime) -> str:
    return dt.astimezone(_MSK).strftime(_TS_FMT)


@retryable
def _sync_create_sheet_for_date(day: date, hours: Sequence[int]) -> int:
    ss = get_spreadsheet()
    rows = 1 + len(hours)
    ws = ss.add_worksheet(title=day.isoformat(), rows=rows, cols=3)
    time_values = [[f"{h:02d}:00"] for h in hours]
    ws.batch_update(
        [
            {"range": "A1:C1", "values": [DATE_HEADER]},
            {"range": f"A2:A{rows}", "values": time_values},
        ],
        value_input_option="USER_ENTERED",
    )
    ws.format("A1:C1", _HEADER_FMT)
    ws.freeze(rows=1)
    return int(ws.id)


@retryable
def _sync_write_booking(
    sheet_id: int, row_index: int, username: str | None, tg_id: int, booked_at: datetime
) -> None:
    ss = get_spreadsheet()
    ws = ss.get_worksheet_by_id(sheet_id)
    ws.update(
        range_name=f"B{row_index}:C{row_index}",
        values=[[_user_cell(username, tg_id), _to_msk(booked_at)]],
        value_input_option="USER_ENTERED",
    )


@retryable
def _sync_clear_booking(sheet_id: int, row_index: int) -> None:
    ss = get_spreadsheet()
    ws = ss.get_worksheet_by_id(sheet_id)
    ws.batch_clear([f"B{row_index}:C{row_index}"])


@retryable
def _sync_delete_sheet(sheet_id: int) -> None:
    ss = get_spreadsheet()
    ws = ss.get_worksheet_by_id(sheet_id)
    ss.del_worksheet(ws)


@retryable
def _sync_delete_row(sheet_id: int, row_index: int) -> None:
    ss = get_spreadsheet()
    ws = ss.get_worksheet_by_id(sheet_id)
    ws.delete_rows(row_index)


@retryable
def _sync_append_feedback(
    username: str | None, tg_id: int, text: str, created_at: datetime
) -> int | None:
    ss = get_spreadsheet()
    try:
        ws = ss.worksheet(FEEDBACK_SHEET_NAME)
    except WorksheetNotFound:
        ws = ss.add_worksheet(title=FEEDBACK_SHEET_NAME, rows=100, cols=3)
        ws.update(
            range_name="A1:C1",
            values=[FEEDBACK_HEADER],
            value_input_option="USER_ENTERED",
        )
        ws.format("A1:C1", _HEADER_FMT)
        ws.freeze(rows=1)
    resp = ws.append_row(
        [_to_msk(created_at), _user_cell(username, tg_id), text],
        value_input_option="USER_ENTERED",
    )
    return parse_row_from_range(resp.get("updates", {}).get("updatedRange", ""))


async def create_sheet_for_date(day: date, hours: Sequence[int]) -> int:
    return await asyncio.to_thread(_sync_create_sheet_for_date, day, hours)


async def write_booking(
    sheet_id: int, row_index: int, username: str | None, tg_id: int, booked_at: datetime
) -> None:
    await asyncio.to_thread(_sync_write_booking, sheet_id, row_index, username, tg_id, booked_at)


async def clear_booking(sheet_id: int, row_index: int) -> None:
    await asyncio.to_thread(_sync_clear_booking, sheet_id, row_index)


async def delete_sheet(sheet_id: int) -> None:
    await asyncio.to_thread(_sync_delete_sheet, sheet_id)


async def delete_row(sheet_id: int, row_index: int) -> None:
    await asyncio.to_thread(_sync_delete_row, sheet_id, row_index)


async def append_feedback(
    username: str | None, tg_id: int, text: str, created_at: datetime
) -> int | None:
    return await asyncio.to_thread(_sync_append_feedback, username, tg_id, text, created_at)
