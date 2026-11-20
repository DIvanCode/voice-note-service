from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from bot.models.note import FIELD_LABELS, Note
from bot.services.crm_service import CRMError, CRMNotConfiguredError
from bot.states.note_states import NoteState

logger = logging.getLogger(__name__)


class NoteConfirmationHandler:
    def __init__(self, telegram_service, crm_service, user_phones: Mapping[int, str] | None = None):
        self.telegram = telegram_service
        self.crm = crm_service
        self.user_phones = user_phones

    async def _restore_preview(
        self, user_id: int, state: Any, note: Note, data: dict[str, Any], notice: str,
    ) -> None:
        await state.set_state(NoteState.PREVIEW.value)
        await self.telegram.send_note_preview(
            user_id, note, data["flow_id"], data["ui_message_id"], notice=notice,
        )

    async def confirm(self, user_id: int, state: Any) -> None:
        data = await state.get_data()
        note_data = data.get("note")
        if note_data is None:
            await state.clear()
            try:
                await self.telegram.send_error(
                    user_id, "Активная заметка не найдена.", data.get("ui_message_id"),
                )
            finally:
                await self.telegram.send_next_note_prompt(user_id)
            return

        note = Note.from_dict(note_data)
        if not note.can_be_sent_to_crm:
            labels = ", ".join(FIELD_LABELS[field] for field in note.missing_required_fields)
            await self._restore_preview(
                user_id, state, note, data,
                f"Пока не могу отправить заметку в CRM: добавьте {labels}. Нажмите «Исправить».",
            )
            return

        if self.user_phones is not None and user_id not in self.user_phones:
            await self._restore_preview(
                user_id, state, note, data, "Доступ к CRM не предоставлен.",
            )
            return

        await state.set_state(NoteState.SAVING.value)
        try:
            await self.telegram.send_saving(user_id, data["ui_message_id"])
        except Exception as exc:
            # A Telegram UI issue must not be reported as a CRM failure.
            logger.warning("Could not set CRM saving status (%s)", type(exc).__name__)

        try:
            if self.user_phones is None:
                # Preserve the original small service interface for test doubles.
                await self.crm.create_note(note)
            else:
                await self.crm.create_note(note, user_phone=self.user_phones[user_id])
        except CRMNotConfiguredError:
            await state.clear()
            try:
                await self.telegram.send_error(
                    user_id,
                    "Сейчас я ещё не могу отправлять заметки в CRM. Эту заметку не сохранил и закрыл.",
                    data.get("ui_message_id"),
                )
            finally:
                await self.telegram.send_next_note_prompt(user_id)
            return
        except CRMError as exc:
            logger.warning("CRM rejected note (%s)", exc.code)
            await self._restore_preview(user_id, state, note, data, exc.user_message)
            return
        except Exception as exc:
            logger.warning("CRM save failed (%s)", type(exc).__name__)
            await self._restore_preview(
                user_id, state, note, data,
                "Результат отправки не подтверждён. Проверьте CRM перед повторной попыткой, чтобы не создать дубликат.",
            )
            return

        # The CRM has accepted the note: never keep an actionable draft if the
        # Telegram message edit fails after a successful POST.
        await state.clear()
        try:
            await self.telegram.send_success(user_id, data["ui_message_id"], note)
        except Exception as exc:
            logger.warning("Could not update saved note card (%s)", type(exc).__name__)
        await self.telegram.send_next_note_prompt(user_id)
