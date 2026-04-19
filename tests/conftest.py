from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import Base
from app.db import session as db_session
from app.sheets import service as sheets_service


@pytest.fixture(autouse=True)
def mock_sheets(monkeypatch):
    """Silence all gspread-backed calls — tests hit DB only."""
    monkeypatch.setattr(sheets_service, "create_sheet_for_date", AsyncMock(return_value=42))
    monkeypatch.setattr(sheets_service, "write_booking", AsyncMock())
    monkeypatch.setattr(sheets_service, "write_booking_external", AsyncMock())
    monkeypatch.setattr(sheets_service, "clear_booking", AsyncMock())
    monkeypatch.setattr(sheets_service, "delete_sheet", AsyncMock())
    monkeypatch.setattr(sheets_service, "delete_row", AsyncMock())
    monkeypatch.setattr(sheets_service, "append_feedback", AsyncMock(return_value=2))


@pytest_asyncio.fixture
async def test_db(monkeypatch):
    """Swap session_maker to an in-memory SQLite engine with fresh schema."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    test_maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(db_session, "async_session_maker", test_maker)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()
