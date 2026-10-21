import pytest

from bot.services.note_extraction_service import NoteExtractionService


def fake_extract(text: str) -> dict[str, str | None]:
    return {
        "client": "ООО Ромашка",
        "problem": text,
        "product": None,
        "budget": "5 млн",
        "deadline": None,
        "next_step": "созвониться",
    }


@pytest.mark.asyncio
async def test_extraction_result_is_formatted_into_note_body():
    service = NoteExtractionService(extract_fn=fake_extract)

    note = await service.extract("  нужна квартира  ")

    assert note.note == (
        "client: ООО Ромашка\n"
        "problem: нужна квартира\n"
        "budget: 5 млн\n"
        "next_step: созвониться"
    )
    assert note.full_name == "Тестовый Клиент"
    assert note.phone == "+79990000000"
    assert note.topic == "Тестовая тема"


@pytest.mark.asyncio
async def test_extraction_rejects_empty_transcript_without_model_call():
    def must_not_be_called(text):
        raise AssertionError("model must not be called")

    service = NoteExtractionService(extract_fn=must_not_be_called)

    with pytest.raises(ValueError):
        await service.extract("   ")


@pytest.mark.asyncio
async def test_model_error_is_propagated():
    def broken(text):
        raise RuntimeError("llama is down")

    service = NoteExtractionService(extract_fn=broken)

    with pytest.raises(RuntimeError):
        await service.extract("текст")