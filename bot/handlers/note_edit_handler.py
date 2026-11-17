from __future__ import annotations

import logging
from typing import Any

from bot.models.note import FIELD_LABELS, Note
from bot.states.note_states import NoteState

EDITABLE_FIELDS = set(FIELD_LABELS)
logger = logging.getLogger(__name__)


class NoteEditHandler:
    def __init__(self, telegram_service):
        self.telegram = telegram_service

    async def _remove_prompt(self, user_id: int, message_id: int | None) -> None:
        if message_id is None:
            return
        try:
            await self.telegram.delete_edit_prompt(user_id, message_id)
        except Exception as exc:
            # Telegram may reject deletion of an old/already removed message;
            # this should not corrupt a draft or create duplicate previews.
            logger.warning("Could not delete field prompt (%s)", type(exc).__name__)

    async def start_edit(self, user_id: int, state: Any) -> None:
        data = await state.get_data()
        if data.get("note") is None or data.get("flow_id") is None:
            await state.clear()
            await self._remove_prompt(user_id, data.get("edit_prompt_message_id"))
            await self.telegram.send_error(user_id, "Активная заметка не найдена.", data.get("ui_message_id"))
            return

        await self.telegram.send_edit_menu(
            user_id, data["flow_id"], data["ui_message_id"], Note.from_dict(data["note"]),
        )
        await state.update_data(editing_field=None, edit_prompt_message_id=None)
        await state.set_state(NoteState.EDITING.value)
        await self._remove_prompt(user_id, data.get("edit_prompt_message_id"))

    async def select_field(self, user_id: int, field: str, state: Any) -> None:
        data = await state.get_data()
        if field not in EDITABLE_FIELDS:
            await self.telegram.send_edit_menu(
                user_id, data["flow_id"], data["ui_message_id"], Note.from_dict(data["note"]),
                notice="Неизвестное поле для редактирования.",
            )
            return

        prompt_id = await self.telegram.send_edit_prompt(user_id, field)
        await state.update_data(editing_field=field, edit_prompt_message_id=prompt_id)
        await state.set_state(NoteState.EDITING.value)
        await self._remove_prompt(user_id, data.get("edit_prompt_message_id"))

    async def show_preview(self, user_id: int, state: Any) -> None:
        data = await state.get_data()
        note_data = data.get("note")
        if note_data is None or data.get("flow_id") is None:
            await state.clear()
            await self._remove_prompt(user_id, data.get("edit_prompt_message_id"))
            await self.telegram.send_error(user_id, "Активная заметка не найдена.", data.get("ui_message_id"))
            return

        await self.telegram.send_note_preview(
            user_id, Note.from_dict(note_data), data["flow_id"], data["ui_message_id"],
        )
        await state.update_data(editing_field=None, edit_prompt_message_id=None)
        await state.set_state(NoteState.PREVIEW.value)
        await self._remove_prompt(user_id, data.get("edit_prompt_message_id"))

    async def save_edit(self, user_id: int, edited_text: str, state: Any) -> None:
        data = await state.get_data()
        note_data = data.get("note")
        flow_id = data.get("flow_id")
        field = data.get("editing_field")
        card_id = data.get("ui_message_id")
        prompt_id = data.get("edit_prompt_message_id")

        if note_data is None or flow_id is None:
            await state.clear()
            await self._remove_prompt(user_id, prompt_id)
            await self.telegram.send_error(user_id, "Активная заметка не найдена.", card_id)
            return

        if field not in EDITABLE_FIELDS:
            await self.telegram.send_edit_menu(
                user_id, flow_id, card_id, Note.from_dict(note_data),
                notice="Выберите поле, которое хотите исправить.",
            )
            return

        previous_note = Note.from_dict(note_data)
        value = edited_text.strip()
        updated_data = dict(note_data)
        updated_data[field] = None if not value or value == "-" else value
        note = Note.from_dict(updated_data)

        # Update the draft pointer only after the new note card exists.
        # An unsuccessful send leaves the original field prompt available.
        new_card_id = await self.telegram.send_revised_note_preview(
            user_id, note, flow_id, card_id, previous_note,
        )
        await state.update_data(
            note=note.to_dict(), editing_field=None,
            ui_message_id=new_card_id, edit_prompt_message_id=None,
        )
        await state.set_state(NoteState.PREVIEW.value)
        await self._remove_prompt(user_id, prompt_id)

    async def cancel(self, user_id: int, state: Any) -> None:
        data = await state.get_data()
        await state.clear()
        await self._remove_prompt(user_id, data.get("edit_prompt_message_id"))
        try:
            await self.telegram.send_cancelled(user_id, data["ui_message_id"])
        finally:
            await self.telegram.send_next_note_prompt(user_id)
