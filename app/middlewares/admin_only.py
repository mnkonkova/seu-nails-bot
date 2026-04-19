from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message, User

from app.config import settings


def is_admin(user: User | None) -> bool:
    if user is None or user.username is None:
        return False
    return user.username.lower() in settings.admin_usernames


class AdminFilter(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        return is_admin(event.from_user)
