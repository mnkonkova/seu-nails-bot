from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.keyboards.inline import admin_menu, client_menu
from app.middlewares.admin_only import is_admin

router = Router(name="common")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    if is_admin(message.from_user):
        await message.answer("Админ-панель. Выбери действие:", reply_markup=admin_menu())
    else:
        await message.answer(
            "Привет! Здесь можно записаться на приём.\n"
            "Посмотри свободные даты или используй /help.",
            reply_markup=client_menu(),
        )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    if is_admin(message.from_user):
        text = (
            "<b>Админ-команды</b>\n"
            "/add — добавить дату (окна 8:00–22:00)\n"
            "/dates — активные даты\n"
            "/del — удалить дату или окно\n\n"
            "<b>Также доступно как клиенту</b>: /browse /my /feedback /subscribe"
        )
    else:
        text = (
            "<b>Клиентские команды</b>\n"
            "/browse — свободные даты\n"
            "/my — мои записи\n"
            "/feedback — оставить отзыв\n"
            "/subscribe — подписаться на новые даты\n"
            "/unsubscribe — отписаться\n"
            "/cancel — прервать текущий шаг"
        )
    await message.answer(text)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    if await state.get_state() is None:
        await message.answer("Нечего отменять.")
        return
    await state.clear()
    kb = admin_menu() if is_admin(message.from_user) else client_menu()
    await message.answer("Отменено.", reply_markup=kb)
