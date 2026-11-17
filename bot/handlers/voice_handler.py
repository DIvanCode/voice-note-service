from __future__ import annotations

import logging
from typing import Any

from bot.models.note import Note
from bot.states.note_states import NoteState

logger = logging.getLogger(__name__)


class VoiceHandler:
    def __init__(self, telegram_service, stt_service, extraction_service):
        self.telegram = telegram_service
        self.stt = stt_service
        self.extraction = extraction_service

    async def handle_voice(self, message: Any, state: Any) -> None:
        user_id = message.from_user.id
        current_state = await state.get_state()
        if current_state is not None:
            # A second voice must not create another actionable bot message.
            data = await state.get_data()
            card_id = data.get("ui_message_id")
            flow_id = data.get("flow_id")
            try:
                if card_id is not None and flow_id is not None:
                    if current_state == NoteState.PREVIEW.value and data.get("note"):
                        await self.telegram.send_note_preview(
                            user_id, Note.from_dict(data["note"]), flow_id, card_id,
                            notice="Сначала завершите текущую заметку. Затем можно отправить новое голосовое.",
                        )
                    elif current_state == NoteState.EDITING.value and data.get("note"):
                        # Refresh the existing menu, but never create a second
                        # temporary field prompt when another voice arrives.
                        await self.telegram.send_edit_menu(
                            user_id, flow_id, card_id, Note.from_dict(data["note"]),
                            notice="Сначала завершите редактирование текущей заметки.",
                        )
                    # PROCESSING / SAVING already show their current status.
            except Exception as exc:
                logger.warning("Could not refresh active note card (%s)", type(exc).__name__)
            return

        flow_id = str(message.message_id)
        await state.set_state(NoteState.PROCESSING.value)
        await state.update_data(flow_id=flow_id)
        card_id = None
        try:
            card_id = await self.telegram.send_processing(user_id)
            await state.update_data(ui_message_id=card_id)

            audio = await self.telegram.download_voice(message)
            text = await self.stt.transcribe(audio)
            # Keep sensitive transcripts in memory only.
            note = await self.extraction.extract(text)

            await state.update_data(note=note.to_dict())
            await state.set_state(NoteState.PREVIEW.value)
            await self.telegram.send_note_preview(user_id, note, flow_id, card_id)
        except Exception as exc:
            # Do not log audio, transcript, note fields, Telegram IDs or exception text.
            logger.warning("Voice processing failed (%s)", type(exc).__name__)
            await state.clear()
            await self.telegram.send_error(
                user_id,
                "Не удалось обработать голосовое сообщение. Попробуйте позже.",
                card_id,
            )
