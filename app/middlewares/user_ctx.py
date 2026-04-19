import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User as TGUser

from app.db import UserRepo, session_scope

_log = logging.getLogger(__name__)


class UserCtxMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user: TGUser | None = data.get("event_from_user")
        if tg_user is not None and not tg_user.is_bot:
            try:
                async with session_scope() as s:
                    db_user = await UserRepo(s).upsert(tg_user.id, tg_user.username)
                data["db_user"] = db_user
            except Exception:
                _log.exception("user upsert failed for tg_id=%s", tg_user.id)
        return await handler(event, data)
