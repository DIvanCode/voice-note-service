from __future__ import annotations

from typing import Any

from bot.models.note import FIELD_LABELS, Note
from bot.states.note_states import NoteState

EDITABLE_FIELDS = set(FIELD_LABELS)


class NoteEditHandler:
    def __init__(self, telegram_service):
        self.telegram = telegram_service

    async def start_edit(self, user_id: int, state: Any) -> None:
        data = await state.get_data()
        if data.get("note") is None or data.get("flow_id") is None:
            await state.clear()
            await self.telegram.send_error(user_id, "Активная заметка не найдена.", data.get("ui_message_id"))
            return

        await state.set_state(NoteState.EDITING.value)
        await state.update_data(editing_field=None)
        await self.telegram.send_edit_menu(user_id, data["flow_id"], data["ui_message_id"])

    async def select_field(self, user_id: int, field: str, state: Any) -> None:
        data = await state.get_data()
        if field not in EDITABLE_FIELDS:
            await self.telegram.send_edit_menu(
                user_id, data["flow_id"], data["ui_message_id"],
                notice="Неизвестное поле для редактирования.",
            )
            return

        await state.set_state(NoteState.EDITING.value)
        await state.update_data(editing_field=field)
        await self.telegram.send_edit_prompt(
            user_id, field, data["flow_id"], data["ui_message_id"],
        )

    async def show_preview(self, user_id: int, state: Any) -> None:
        data = await state.get_data()
        note_data = data.get("note")
        if note_data is None or data.get("flow_id") is None:
            await state.clear()
            await self.telegram.send_error(user_id, "Активная заметка не найдена.", data.get("ui_message_id"))
            return

        await state.update_data(editing_field=None)
        await state.set_state(NoteState.PREVIEW.value)
        await self.telegram.send_note_preview(
            user_id, Note.from_dict(note_data), data["flow_id"], data["ui_message_id"],
        )

    async def save_edit(self, user_id: int, edited_text: str, state: Any) -> None:
        data = await state.get_data()
        note_data = data.get("note")
        flow_id = data.get("flow_id")
        field = data.get("editing_field")
        card_id = data.get("ui_message_id")

        if note_data is None or flow_id is None:
            await state.clear()
            await self.telegram.send_error(user_id, "Активная заметка не найдена.", card_id)
            return

        if field not in EDITABLE_FIELDS:
            await self.telegram.send_edit_menu(
                user_id, flow_id, card_id,
                notice="Выберите поле, которое хотите исправить.",
            )
            return

        value = edited_text.strip()
        note_data[field] = None if not value or value == "-" else value
        note = Note.from_dict(note_data)

        await state.update_data(note=note.to_dict(), editing_field=None)
        await state.set_state(NoteState.PREVIEW.value)
        await self.telegram.send_note_preview(user_id, note, flow_id, card_id)

    async def cancel(self, user_id: int, state: Any) -> None:
        data = await state.get_data()
        await state.clear()
        await self.telegram.send_cancelled(user_id, data["ui_message_id"])
