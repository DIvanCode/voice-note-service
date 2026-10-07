from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from bot.states.note_states import NoteState

logger = logging.getLogger(__name__)
default_transcript_file = Path(__file__).resolve().parents[2] / "transcriptions.log"
TRANSCRIPT_FILE = Path(os.getenv("TRANSCRIPT_FILE") or default_transcript_file)


class VoiceHandler:
    def __init__(self, telegram_service, stt_service, extraction_service):
        self.telegram = telegram_service
        self.stt = stt_service
        self.extraction = extraction_service

    async def handle_voice(self, message: Any, state: Any) -> None:
        current_state = await state.get_state()
        if current_state is not None:
            data = await state.get_data()
            await self.telegram.send_busy(
                message.from_user.id,
                flow_id=data.get("flow_id"),
                with_actions=current_state in {
                    NoteState.PREVIEW.value,
                    NoteState.EDITING.value,
                },
            )
            return

        flow_id = str(message.message_id)
        await state.set_state(NoteState.PROCESSING.value)
        await state.update_data(flow_id=flow_id)

        try:
            audio = await self.telegram.download_voice(message)
            text = await self.stt.transcribe(audio)
            with TRANSCRIPT_FILE.open("a", encoding="utf-8") as transcript_file:
                transcript_file.write(f"{text}\n\n")
            note = await self.extraction.extract(text)

            await state.update_data(note=note.to_dict())
            await state.set_state(NoteState.PREVIEW.value)
            await self.telegram.send_note_preview(message.from_user.id, note, flow_id)
        except Exception as exc:
            # Do not log audio, transcript, note fields, Telegram IDs or exception text.
            logger.warning("Voice processing failed (%s)", type(exc).__name__)
            await state.clear()
            await self.telegram.send_error(
                message.from_user.id,
                "Не удалось обработать голосовое сообщение. Попробуйте позже.",
            )
