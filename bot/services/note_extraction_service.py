from __future__ import annotations

import asyncio
from collections.abc import Callable

from bot.models.note import Note
from extractor.app.extractor import extract_text, validate_result


class NoteExtractionService:
    """Convert the local model's six fields into a note for Telegram review."""

    def __init__(
        self,
        extract_fn: Callable[[str], dict[str, str | None]] = extract_text,
    ):
        self.extract_fn = extract_fn

    async def extract(self, text: str) -> Note:
        text = text.strip()
        if not text:
            raise ValueError("Transcribed text is empty")

        return await asyncio.to_thread(self._extract_sync, text)

    def _extract_sync(self, text: str) -> Note:
        result = validate_result(self.extract_fn(text))
        return Note(**{
            field: (value.strip() or None) if value is not None else None
            for field, value in result.items()
        })
