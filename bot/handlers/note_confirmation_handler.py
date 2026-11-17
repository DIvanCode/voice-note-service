from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from bot.models.note import Note
from bot.services.crm_service import CRMError, CRMNotConfiguredError
from bot.states.note_states import NoteState

logger = logging.getLogger(__name__)


class NoteConfirmationHandler:
    def __init__(self, telegram_service, crm_service, user_phones: Mapping[int, str] | None = None):
        self.telegram = telegram_service
        self.crm = crm_service
        self.user_phones = user_phones

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
            await self.telegram.send_required_fields(user_id, note.missing_required_fields)
            return

        if self.user_phones is not None and user_id not in self.user_phones:
            await state.set_state(NoteState.PREVIEW.value)
            await self.telegram.send_error(user_id, "Доступ к CRM не предоставлен.")
            return

        await state.set_state(NoteState.SAVING.value)
        try:
            if self.user_phones is None:
                # Preserve the original small service interface for test doubles.
                await self.crm.create_note(note)
            else:
                await self.crm.create_note(note, user_phone=self.user_phones[user_id])
        except CRMNotConfiguredError:
            await state.clear()
            await self.telegram.send_error(
                user_id,
                "Сейчас я ещё не могу отправлять заметки в CRM. Эту заметку не сохранил и закрыл. "
                "Можете отправить новое голосовое.",
            )
            return
        except CRMError as exc:
            logger.warning("CRM rejected note (%s)", exc.code)
            await state.set_state(NoteState.PREVIEW.value)
            await self.telegram.send_error(user_id, exc.user_message)
            return
        except Exception as exc:
            logger.warning("CRM save failed (%s)", type(exc).__name__)
            await state.set_state(NoteState.PREVIEW.value)
            await self.telegram.send_error(
                user_id,
                "Результат отправки не подтверждён. Проверьте CRM перед повторной попыткой, чтобы не создать дубликат.",
            )
            return

        await state.clear()
        await self.telegram.send_success(user_id)
