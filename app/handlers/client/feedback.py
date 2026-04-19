import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from app.keyboards.inline import CLIENT_FEEDBACK, admin_menu, client_menu, remove_kb
from app.middlewares.admin_only import is_admin
from app.services.booking import submit_feedback
from app.services.error_reporter import report_error

_log = logging.getLogger(__name__)

router = Router(name="client.feedback")

MAX_LEN = 2000


class FeedbackFSM(StatesGroup):
    waiting_for_text = State()


@router.message(Command("feedback"))
@router.message(F.text == CLIENT_FEEDBACK)
async def start_feedback(message: Message, state: FSMContext) -> None:
    await state.set_state(FeedbackFSM.waiting_for_text)
    await message.answer(
        "Напиши отзыв одним сообщением (до 2000 символов). /cancel — отмена.",
        reply_markup=remove_kb(),
    )


@router.message(FeedbackFSM.waiting_for_text)
async def receive_feedback(message: Message, state: FSMContext, bot: Bot) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("Нужен текст. Пришли отзыв или /cancel.")
        return
    if len(text) > MAX_LEN:
        await message.answer(f"Слишком длинно ({len(text)}>{MAX_LEN}). Сократи и пришли снова.")
        return
    user = message.from_user
    try:
        await submit_feedback(  # type: ignore[union-attr]
            user.id, user.username, text, user.first_name, user.last_name
        )
    except Exception as e:
        _log.exception("submit_feedback failed")
        await report_error(bot, e, where="client.feedback.receive",
                           extra=f"tg_id={user.id} len={len(text)}")
        await message.answer("Не получилось сохранить отзыв. Попробуй позже.")
        await state.clear()
        return
    await state.clear()
    kb = admin_menu() if is_admin(user) else client_menu()
    await message.answer("Спасибо за отзыв! 💛", reply_markup=kb)
