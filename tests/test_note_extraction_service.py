import pytest

from bot.services.note_extraction_service import NoteExtractionService


@pytest.mark.asyncio
async def test_stub_keeps_transcript_without_inventing_required_fields():
    service = NoteExtractionService()

    note = await service.extract("  исходный распознанный текст  ")

    assert note.description == "исходный распознанный текст"
    assert note.lead is None
    assert note.topic is None
    assert not note.can_be_sent_to_crm


@pytest.mark.asyncio
async def test_stub_rejects_empty_transcript():
    service = NoteExtractionService()

    with pytest.raises(ValueError):
        await service.extract("   ")
