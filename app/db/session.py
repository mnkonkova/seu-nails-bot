import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy import Connection, event, inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.db.models import Base

_log = logging.getLogger(__name__)

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


def _apply_adhoc_migrations(sync_conn: Connection) -> None:
    """Lightweight ALTER TABLEs for columns create_all can't add to existing tables."""
    insp = inspect(sync_conn)
    if "slots" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("slots")}
        if "external_client_name" not in cols:
            _log.info("migrating: adding slots.external_client_name")
            sync_conn.execute(
                text("ALTER TABLE slots ADD COLUMN external_client_name VARCHAR(128)")
            )


async def init_db() -> None:
    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_apply_adhoc_migrations)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
