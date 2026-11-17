import pytest

from bot.handlers.note_edit_handler import NoteEditHandler
from bot.models.note import Note
from bot.states.note_states import NoteState
from tests.fakes import FakeState, FakeTelegram


@pytest.mark.asyncio
async def test_edit_allows_topic_change_and_returns_to_preview():
    telegram = FakeTelegram()
    state = FakeState()
    state.state = NoteState.PREVIEW.value
    state.data["note"] = Note(description="text", lead="ул. Лесная, 1").to_dict()
    state.data["flow_id"] = "123"
    handler = NoteEditHandler(telegram)

    await handler.start_edit(1, state)
    await handler.select_field(1, "topic", state)
    await handler.save_edit(1, "Покупка квартиры", state)

    assert state.state == NoteState.PREVIEW.value
    assert state.data["note"]["topic"] == "Покупка квартиры"
    assert telegram.calls[-1][0] == "preview"


@pytest.mark.asyncio
async def test_optional_field_can_be_cleared_with_dash():
    telegram = FakeTelegram()
    state = FakeState()
    state.state = NoteState.EDITING.value
    state.data = {
        "note": Note(description="text", next_step="Позвонить", topic="Тема").to_dict(),
        "editing_field": "next_step",
        "flow_id": "123",
    }
    handler = NoteEditHandler(telegram)

    await handler.save_edit(1, "-", state)

    assert state.data["note"]["next_step"] is None


@pytest.mark.asyncio
async def test_cancel_clears_active_note():
    telegram = FakeTelegram()
    state = FakeState()
    state.state = NoteState.PREVIEW.value
    state.data["note"] = Note(description="text", topic="Тема").to_dict()
    state.data["flow_id"] = "123"
    handler = NoteEditHandler(telegram)

    await handler.cancel(1, state)

    assert state.state is None
    assert state.data == {}
    assert telegram.calls[-1][0] == "cancelled"
