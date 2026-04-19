from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.db.models import Base

_engine = create_async_engine(
    f"sqlite+aiosqlite:///{settings.db_path}",
    echo=False,
    future=True,
)

async_session_maker = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)


@event.listens_for(_engine.sync_engine, "connect")
def _enable_sqlite_fk(dbapi_conn: object, _: object) -> None:
    cur = dbapi_conn.cursor()  # type: ignore[attr-defined]
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


async def init_db() -> None:
    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
