import threading

import pytest

from bot.services.note_extraction_service import NoteExtractionService


def fake_extract(text: str) -> dict[str, str | None]:
    return {
        "lead": "  ул. Лесная, 10  ",
        "topic": "Просмотр квартиры",
        "description": text,
        "next_step": "Позвонить клиенту",
        "deadline": None,
        "additional_info": "Нужна парковка",
    }


@pytest.mark.asyncio
async def test_model_result_maps_to_six_note_fields():
    note = await NoteExtractionService(extract_fn=fake_extract).extract(
        "  Обсудили квартиру  "
    )

    assert note.lead == "ул. Лесная, 10"
    assert note.topic == "Просмотр квартиры"
    assert note.description == "Обсудили квартиру"
    assert note.next_step == "Позвонить клиенту"
    assert note.deadline is None
    assert note.additional_info == "Нужна парковка"
    assert note.can_be_sent_to_crm
    assert note.missing_recommended_fields == ("deadline",)


@pytest.mark.asyncio
async def test_model_runs_in_worker_thread():
    caller_thread = threading.get_ident()
    model_thread = None

    def extract(text: str) -> dict[str, str | None]:
        nonlocal model_thread
        model_thread = threading.get_ident()
        return fake_extract(text)

    await NoteExtractionService(extract_fn=extract).extract("Текст")

    assert model_thread is not None
    assert model_thread != caller_thread


@pytest.mark.asyncio
async def test_model_cannot_invent_required_fields():
    def without_lead(_: str) -> dict[str, str | None]:
        return {**fake_extract("Текст"), "lead": "  "}

    note = await NoteExtractionService(extract_fn=without_lead).extract("Текст")

    assert note.lead is None
    assert not note.can_be_sent_to_crm


@pytest.mark.asyncio
async def test_empty_transcript_does_not_call_model():
    def must_not_be_called(_: str):
        raise AssertionError("model must not be called")

    service = NoteExtractionService(extract_fn=must_not_be_called)
    with pytest.raises(ValueError):
        await service.extract("   ")


@pytest.mark.asyncio
async def test_model_error_is_propagated():
    def broken(_: str):
        raise RuntimeError("llama is down")

    service = NoteExtractionService(extract_fn=broken)
    with pytest.raises(RuntimeError):
        await service.extract("текст")


@pytest.mark.asyncio
async def test_invalid_model_shape_is_rejected():
    def invalid(_: str):
        return {"lead": "+79990000000"}

    service = NoteExtractionService(extract_fn=invalid)
    with pytest.raises(ValueError):
        await service.extract("текст")
