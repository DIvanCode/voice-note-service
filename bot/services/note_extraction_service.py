from __future__ import annotations

import asyncio
from collections.abc import Callable

from bot.models.note import Note
from extractor.app.extractor import extract_text


class NoteExtractionService:

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
        result = self.extract_fn(text)

        body = "\n".join(
            f"{key}: {value}"
            for key, value in result.items()
            if value is not None
        )
        return Note(
            note=body,
            full_name="Тестовый Клиент",
            phone="+79990000000",
            topic="Тестовая тема",
        )