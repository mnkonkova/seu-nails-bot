from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.db import User, UserRepo, session_scope
from app.keyboards.inline import CLIENT_SUBSCRIBE, SubCB, subscribe_kb

router = Router(name="client.subscribe")


async def _current(tg_id: int) -> bool:
    async with session_scope() as s:
        user = await s.get(User, tg_id)
        return bool(user and user.subscribed_to_new_dates)


@router.message(Command("subscribe"))
async def cmd_subscribe(message: Message) -> None:
    async with session_scope() as s:
        await UserRepo(s).set_subscription(message.from_user.id, True)  # type: ignore[union-attr]
    await message.answer("🔔 Подписка включена. Я сообщу о новых датах.")


@router.message(Command("unsubscribe"))
async def cmd_unsubscribe(message: Message) -> None:
    async with session_scope() as s:
        await UserRepo(s).set_subscription(message.from_user.id, False)  # type: ignore[union-attr]
    await message.answer("🔕 Ок, уведомлений больше не пришлю.")


@router.message(F.text == CLIENT_SUBSCRIBE)
async def show_subscription(message: Message) -> None:
    is_on = await _current(message.from_user.id)  # type: ignore[union-attr]
    status = "включена 🔔" if is_on else "выключена 🔕"
    await message.answer(
        f"Уведомления о новых датах: {status}.",
        reply_markup=subscribe_kb(currently_on=is_on),
    )


@router.callback_query(SubCB.filter())
async def toggle_subscription(cq: CallbackQuery, callback_data: SubCB) -> None:
    enable = callback_data.action == "on"
    async with session_scope() as s:
        await UserRepo(s).set_subscription(cq.from_user.id, enable)
    status = "включена 🔔" if enable else "выключена 🔕"
    await cq.message.edit_text(  # type: ignore[union-attr]
        f"Уведомления о новых датах: {status}.",
        reply_markup=subscribe_kb(currently_on=enable),
    )
    await cq.answer()
