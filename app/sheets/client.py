import logging
import threading
from collections.abc import Callable
from typing import TypeVar

import gspread
from google.oauth2.service_account import Credentials
from gspread.exceptions import APIError
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings

SCOPES = ("https://www.googleapis.com/auth/spreadsheets",)

_log = logging.getLogger(__name__)
_lock = threading.Lock()
_cached_ss: gspread.Spreadsheet | None = None

T = TypeVar("T")


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, APIError):
        code = getattr(getattr(exc, "response", None), "status_code", 0)
        return code in (429, 500, 502, 503, 504)
    return isinstance(exc, (ConnectionError, TimeoutError))


def retryable(func: Callable[..., T]) -> Callable[..., T]:
    return retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=20),
        retry=retry_if_exception(_is_retryable),
        before_sleep=before_sleep_log(_log, logging.WARNING),
        reraise=True,
    )(func)


def get_spreadsheet() -> gspread.Spreadsheet:
    global _cached_ss
    if _cached_ss is not None:
        return _cached_ss
    with _lock:
        if _cached_ss is None:
            creds = Credentials.from_service_account_file(
                settings.sheets_credentials_path, scopes=list(SCOPES)
            )
            client = gspread.authorize(creds)
            _cached_ss = client.open_by_key(settings.sheets_spreadsheet_id)
            _log.info("sheets client initialized, spreadsheet=%s", _cached_ss.title)
    return _cached_ss


def parse_row_from_range(range_str: str) -> int | None:
    """Parse row index from 'SheetName!A5:C5' → 5."""
    try:
        cell = range_str.split("!", 1)[1].split(":", 1)[0]
        return int(cell.lstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
    except (IndexError, ValueError):
        return None
