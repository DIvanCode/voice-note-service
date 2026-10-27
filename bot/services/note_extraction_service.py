from bot.models.note import Note


class NoteExtractionService:
    """Temporary replacement for the future LLM/ML note extraction model.

    Keep the transcript as a description. No lead or topic is inferred until
    extraction is implemented, so the user must supply them before submission.
    """

    async def extract(self, text: str) -> Note:
        text = text.strip()
        if not text:
            raise ValueError("Transcribed text is empty")

        return Note(description=text)
