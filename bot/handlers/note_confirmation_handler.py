from __future__ import annotations

import logging
from typing import Any

from bot.models.note import Note
from bot.services.crm_service import CRMNotConfiguredError
from bot.states.note_states import NoteState

logger = logging.getLogger(__name__)


class NoteConfirmationHandler:
    def __init__(self, telegram_service, crm_service):
        self.telegram = telegram_service
        self.crm = crm_service

    async def confirm(self, user_id: int, state: Any) -> None:
        data = await state.get_data()
        note_data = data.get("note")
        if note_data is None:
            await state.clear()
            await self.telegram.send_error(user_id, "Активная заметка не найдена.")
            return

        note = Note.from_dict(note_data)
        if not note.can_be_sent_to_crm:
            await state.set_state(NoteState.PREVIEW.value)
            await self.telegram.send_topic_required(user_id)
            return

        await state.set_state(NoteState.SAVING.value)
        try:
            await self.crm.create_note(note)
        except CRMNotConfiguredError:
            # Until CRM is connected, confirmation ends the current test flow so
            # the user can immediately send the next voice message.
            await state.clear()
            await self.telegram.send_error(
                user_id,
                "CRM пока не подключена. Заметка не была отправлена. "
                "Текущая заметка автоматически отменена — можно отправить новое голосовое сообщение.",
            )
            return
        except Exception as exc:
            logger.warning("CRM save failed (%s)", type(exc).__name__)
            await state.set_state(NoteState.PREVIEW.value)
            await self.telegram.send_error(
                user_id,
                "Не удалось сохранить заметку в CRM. Попробуйте позже.",
            )
            return

        await state.clear()
        await self.telegram.send_success(user_id)
