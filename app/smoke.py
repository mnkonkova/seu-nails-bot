"""End-to-end smoke test: exercises the service layer and mirrors to Google Sheets.

Run inside the existing image (separate one-off container so it doesn't fight
the running bot's polling):

    sudo docker run --rm -it --env-file .env -e TZ=Europe/Moscow \\
      -v "$(pwd)/data:/app/data" \\
      -v "$(pwd)/credentials/gsheets.json:/app/credentials/gsheets.json:ro" \\
      --network host lubabot:latest python -m app.smoke

Visually verify the Google Sheet after each step (script pauses for Enter).
Uses a fake tg_id so it doesn't collide with a real user.
"""
import asyncio
import sys
from datetime import timedelta

from app.db import init_db
from app.services.booking import (
    book_slot,
    create_date,
    delete_date,
    submit_feedback,
    unbook_slot,
)
from app.utils.dates import today_msk

SMOKE_TG_ID = 999_000_001
SMOKE_USERNAME = "smoke_tester"
SMOKE_FIRST = "Smoke"
SMOKE_LAST = "Tester"

ANON_TG_ID = 999_000_002
ANON_FIRST = "Анонимус"


def _pause(msg: str) -> None:
    print(f"\n>>> {msg}")
    if sys.stdin.isatty():
        input("    Press Enter to continue... ")


async def main() -> None:
    await init_db()
    day = today_msk() + timedelta(days=365)

    print(f"[1] create_date({day}, hours=[10, 11, 12])")
    date_rec = await create_date(day, [10, 11, 12])
    print(f"    date_id={date_rec.id} sheet_id={date_rec.sheet_id} slots={len(date_rec.slots)}")
    _pause(f"Sheet should have a new tab '{day}' with 10:00/11:00/12:00 rows.")

    slot = date_rec.slots[0]
    print(f"[2] book_slot(slot_id={slot.id}, username={SMOKE_USERNAME})")
    await book_slot(slot.id, SMOKE_TG_ID, SMOKE_USERNAME, SMOKE_FIRST, SMOKE_LAST)
    _pause("Row 2 col B should show '@smoke_tester' with hyperlink to t.me/smoke_tester.")

    print("[3] unbook_slot()")
    await unbook_slot(slot.id, SMOKE_TG_ID)
    _pause("Row 2 cells B and C should be empty, hyperlink cleared.")

    print(f"[4] book_slot as a username-less user (first_name only)")
    await book_slot(slot.id, ANON_TG_ID, None, ANON_FIRST, None)
    _pause(
        "Row 2 col B should show 'Анонимус' as plain text with tg://user?id=... link "
        "(clickable in Telegram client)."
    )

    print("[5] submit_feedback()")
    await submit_feedback(
        SMOKE_TG_ID, SMOKE_USERNAME, "smoke test feedback", SMOKE_FIRST, SMOKE_LAST
    )
    _pause("A 'Feedback' sheet should exist and have a new row with '@smoke_tester' linked.")

    print(f"[6] delete_date(date_id={date_rec.id})")
    await delete_date(date_rec.id)
    _pause(f"Tab '{day}' should be gone from the spreadsheet.")

    print("\nSmoke test finished.")


if __name__ == "__main__":
    asyncio.run(main())
