from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.config import TIMEZONE

MSK = ZoneInfo(TIMEZONE)

_FORMATS = ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d.%m")


def today_msk() -> date:
    return datetime.now(MSK).date()


def parse_date(text: str, today: date | None = None) -> date | None:
    text = text.strip()
    today = today or today_msk()
    for fmt in _FORMATS:
        try:
            d = datetime.strptime(text, fmt).date()
        except ValueError:
            continue
        if fmt == "%d.%m":
            d = d.replace(year=today.year)
            if d < today:
                d = d.replace(year=today.year + 1)
        return d
    return None


def fmt_date(d: date) -> str:
    return d.strftime("%d.%m.%Y")
