from bot.models.note import Note


class NoteExtractionService:
    """Temporary replacement for the future LLM/ML note extraction model.

    Until the real model is connected, the recognized text is returned as the
    note body and the remaining fields contain explicit test values. This keeps
    the complete Telegram flow usable without pretending that extraction has
    already been implemented.
    """

    async def extract(self, text: str) -> Note:
        text = text.strip()
        if not text:
            raise ValueError("Transcribed text is empty")

        return Note(
            note=text,
            full_name="Тестовый Клиент",
            phone="+79990000000",
            topic="Тестовая тема",
        )
