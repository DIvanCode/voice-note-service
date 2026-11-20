from __future__ import annotations

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation
from aiogram.types import CallbackQuery, Message

from bot.handlers.note_confirmation_handler import NoteConfirmationHandler
from bot.handlers.note_edit_handler import NoteEditHandler
from bot.handlers.voice_handler import VoiceHandler
from bot.services.crm_service import CRMService, parse_agent_bindings
from bot.services.note_extraction_service import NoteExtractionService
from bot.services.speech_to_text_service import SpeechToTextService
from bot.services.telegram_service import TelegramService
from bot.states.note_states import NoteState


async def _validate_flow_callback(
    callback: CallbackQuery,
    state: FSMContext,
    flow_id: str,
    *,
    allowed_states: tuple[str, ...] | None = None,
) -> bool:
    data = await state.get_data()
    card_id = data.get("ui_message_id")
    message = getattr(callback, "message", None)
    stale = data.get("flow_id") != flow_id or (
        card_id is not None and getattr(message, "message_id", None) != card_id
    )
    if stale:
        # A button from a previous draft (possibly from before a restart)
        # must never operate on the current draft. Remove it if possible.
        if message is not None and getattr(callback, "bot", None) is not None:
            try:
                await callback.bot.edit_message_reply_markup(
                    chat_id=message.chat.id, message_id=message.message_id,
                    reply_markup=None,
                )
            except Exception:
                pass
        await callback.answer("Эта заметка уже неактуальна.")
        return False
    if allowed_states is not None and await state.get_state() not in allowed_states:
        await callback.answer("Это действие сейчас недоступно.")
        return False
    await callback.answer()
    return True


def build_router(
    telegram_service: TelegramService,
    voice_handler: VoiceHandler,
    confirmation_handler: NoteConfirmationHandler,
    edit_handler: NoteEditHandler,
    agent_bindings: dict[int, str] | None = None,
) -> Router:
    router = Router()
    allowed = set(agent_bindings or {})

    async def valid_callback(callback: CallbackQuery) -> bool:
        if (
            callback.from_user is None
            or callback.from_user.id not in allowed
            or callback.message is None
            or callback.message.chat.type != "private"
        ):
            await callback.answer("Доступ запрещён.", show_alert=True)
            return False
        return True

    @router.message(CommandStart())
    async def on_start(message: Message, state: FSMContext) -> None:
        if message.from_user is None or message.chat.type != "private":
            return
        if message.from_user.id not in allowed:
            await telegram_service.send_error(message.from_user.id, "Доступ к боту не предоставлен.")
            return
        if await state.get_state() is not None:
            # Do not generate another bot message while a note is active.
            return
        await telegram_service.send_start(message.from_user.id)

    @router.message(F.voice)
    async def on_voice(message: Message, state: FSMContext) -> None:
        if message.from_user is None or message.chat.type != "private":
            return
        if message.from_user.id not in allowed:
            await telegram_service.send_error(message.from_user.id, "Доступ к боту не предоставлен.")
            return
        await voice_handler.handle_voice(message, state)

    @router.callback_query(F.data.startswith("note:confirm:"))
    async def on_confirm(callback: CallbackQuery, state: FSMContext) -> None:
        if not await valid_callback(callback) or callback.data is None:
            return
        flow_id = callback.data.removeprefix("note:confirm:")
        if not await _validate_flow_callback(
            callback, state, flow_id, allowed_states=(NoteState.PREVIEW.value,),
        ):
            return
        await confirmation_handler.confirm(callback.from_user.id, state)

    @router.callback_query(F.data.startswith("note:edit:"))
    async def on_edit(callback: CallbackQuery, state: FSMContext) -> None:
        if not await valid_callback(callback) or callback.data is None:
            return
        flow_id = callback.data.removeprefix("note:edit:")
        if not await _validate_flow_callback(
            callback, state, flow_id,
            allowed_states=(NoteState.PREVIEW.value, NoteState.EDITING.value),
        ):
            return
        await edit_handler.start_edit(callback.from_user.id, state)

    @router.callback_query(F.data.startswith("note:field:"))
    async def on_edit_field(callback: CallbackQuery, state: FSMContext) -> None:
        if not await valid_callback(callback) or callback.data is None:
            return
        payload = callback.data.removeprefix("note:field:")
        flow_id, separator, field = payload.partition(":")
        if not separator or not await _validate_flow_callback(
            callback, state, flow_id, allowed_states=(NoteState.EDITING.value,),
        ):
            return
        await edit_handler.select_field(callback.from_user.id, field, state)

    @router.callback_query(F.data.startswith("note:cancel:"))
    async def on_cancel(callback: CallbackQuery, state: FSMContext) -> None:
        if not await valid_callback(callback) or callback.data is None:
            return
        flow_id = callback.data.removeprefix("note:cancel:")
        if not await _validate_flow_callback(
            callback, state, flow_id,
            allowed_states=(NoteState.PREVIEW.value, NoteState.EDITING.value),
        ):
            return
        await edit_handler.cancel(callback.from_user.id, state)

    @router.callback_query(F.data.startswith("note:preview:"))
    async def on_back_to_preview(callback: CallbackQuery, state: FSMContext) -> None:
        if not await valid_callback(callback) or callback.data is None:
            return
        flow_id = callback.data.removeprefix("note:preview:")
        if not await _validate_flow_callback(
            callback, state, flow_id, allowed_states=(NoteState.EDITING.value,),
        ):
            return
        await edit_handler.show_preview(callback.from_user.id, state)

    @router.message(F.text)
    async def on_edit_text(message: Message, state: FSMContext) -> None:
        if (
            message.from_user is None
            or message.from_user.id not in allowed
            or message.chat.type != "private"
            or await state.get_state() != NoteState.EDITING.value
            or message.text is None
        ):
            return
        await edit_handler.save_edit(message.from_user.id, message.text, state)

    return router


async def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

    # Explicit mapping prevents an unknown Telegram account from impersonating
    # an employee using a shared CRM API key.
    agent_bindings = parse_agent_bindings(os.getenv("CRM_AGENT_BINDINGS") or "{}")
    if not agent_bindings:
        logging.warning("No CRM_AGENT_BINDINGS configured: bot denies all users")

    bot = Bot(token=token)
    dispatcher = Dispatcher(
        storage=MemoryStorage(),
        events_isolation=SimpleEventIsolation(),
    )

    telegram_service = TelegramService(bot)
    stt_service = SpeechToTextService(
        model_name=os.getenv("WHISPER_MODEL", "large"),
    )
    extraction_service = NoteExtractionService()
    crm_service = CRMService()

    voice_handler = VoiceHandler(telegram_service, stt_service, extraction_service)
    confirmation_handler = NoteConfirmationHandler(telegram_service, crm_service, agent_bindings)
    edit_handler = NoteEditHandler(telegram_service)

    dispatcher.include_router(
        build_router(
            telegram_service,
            voice_handler,
            confirmation_handler,
            edit_handler,
            agent_bindings,
        )
    )

    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
