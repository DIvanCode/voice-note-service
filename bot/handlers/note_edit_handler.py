from __future__ import annotations

from typing import Any

from bot.models.note import Note
from bot.states.note_states import NoteState

EDITABLE_FIELDS = {"note", "full_name", "phone", "topic"}
OPTIONAL_FIELDS = {"full_name", "phone", "topic"}


class NoteEditHandler:
    def __init__(self, telegram_service):
        self.telegram = telegram_service

    async def start_edit(self, user_id: int, state: Any) -> None:
        data = await state.get_data()
        if data.get("note") is None or data.get("flow_id") is None:
            await state.clear()
            await self.telegram.send_error(user_id, "Активная заметка не найдена.")
            return

        await state.set_state(NoteState.EDITING.value)
        await state.update_data(editing_field=None)
        await self.telegram.send_edit_menu(user_id, data["flow_id"])

    async def select_field(self, user_id: int, field: str, state: Any) -> None:
        if field not in EDITABLE_FIELDS:
            await self.telegram.send_error(user_id, "Неизвестное поле для редактирования.")
            return

        await state.set_state(NoteState.EDITING.value)
        await state.update_data(editing_field=field)
        await self.telegram.send_edit_prompt(user_id, field)

    async def save_edit(self, user_id: int, edited_text: str, state: Any) -> None:
        data = await state.get_data()
        note_data = data.get("note")
        flow_id = data.get("flow_id")
        field = data.get("editing_field")

        if note_data is None or flow_id is None:
            await state.clear()
            await self.telegram.send_error(user_id, "Активная заметка не найдена.")
            return

        if field not in EDITABLE_FIELDS:
            await self.telegram.send_edit_menu(user_id, flow_id)
            return

        value = edited_text.strip()
        if field == "note" and (not value or value == "-"):
            await self.telegram.send_error(user_id, "Текст заметки не может быть пустым.")
            return

        normalized_value = None if field in OPTIONAL_FIELDS and value == "-" else value
        note_data[field] = normalized_value
        note = Note.from_dict(note_data)

        await state.update_data(note=note.to_dict(), editing_field=None)
        await state.set_state(NoteState.PREVIEW.value)
        await self.telegram.send_note_preview(user_id, note, flow_id)

    async def cancel(self, user_id: int, state: Any) -> None:
        await state.clear()
        await self.telegram.send_cancelled(user_id)
