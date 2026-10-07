import pytest

from bot.services.note_extraction_service import NoteExtractionService


@pytest.mark.asyncio
async def test_stub_returns_transcript_as_note_with_test_fields():
    service = NoteExtractionService()

    note = await service.extract("  исходный распознанный текст  ")

    assert note.note == "исходный распознанный текст"
    assert note.full_name == "Тестовый Клиент"
    assert note.phone == "+79990000000"
    assert note.topic == "Тестовая тема"


@pytest.mark.asyncio
async def test_stub_rejects_empty_transcript():
    service = NoteExtractionService()

    with pytest.raises(ValueError):
        await service.extract("   ")
