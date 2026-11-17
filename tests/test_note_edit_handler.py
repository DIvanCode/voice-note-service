import pytest

from bot.handlers.note_edit_handler import NoteEditHandler
from bot.models.note import Note
from bot.states.note_states import NoteState
from tests.fakes import FakeState, FakeTelegram


def draft(note):
    state = FakeState()
    state.state = NoteState.PREVIEW.value
    state.data.update(note=note.to_dict(), flow_id="123", ui_message_id=500)
    return state


@pytest.mark.asyncio
async def test_edit_sends_new_corrected_card_and_preserves_previous_without_buttons():
    telegram = FakeTelegram()
    state = draft(Note(description="text", lead="ул. Лесная, 1"))
    handler = NoteEditHandler(telegram)

    await handler.start_edit(1, state)
    await handler.select_field(1, "topic", state)
    await handler.save_edit(1, "Покупка квартиры", state)

    assert state.state == NoteState.PREVIEW.value
    assert state.data["note"]["topic"] == "Покупка квартиры"
    assert [call[0] for call in telegram.calls] == [
        "edit_menu", "edit_prompt", "revised_preview", "delete_prompt",
    ]
    assert telegram.calls[0][2] == 500
    assert telegram.calls[1] == ("edit_prompt", "topic", 600)
    assert telegram.calls[2][3] == 500  # previous card
    assert telegram.calls[2][4] == 501  # new corrected card
    assert telegram.calls[2][5].topic is None
    assert telegram.calls[3] == ("delete_prompt", 600)
    assert state.data["ui_message_id"] == 501
    assert state.data["edit_prompt_message_id"] is None


@pytest.mark.asyncio
async def test_optional_field_can_be_cleared_with_dash():
    telegram = FakeTelegram()
    state = draft(Note(description="text", next_step="Позвонить", topic="Тема"))
    state.state = NoteState.EDITING.value
    state.data["editing_field"] = "next_step"
    state.data["edit_prompt_message_id"] = 600
    handler = NoteEditHandler(telegram)

    await handler.save_edit(1, "-", state)

    assert state.data["note"]["next_step"] is None
    assert telegram.calls[-2][0] == "revised_preview"
    assert telegram.calls[-2][3] == 500
    assert telegram.calls[-1] == ("delete_prompt", 600)
    assert state.data["ui_message_id"] == 501


@pytest.mark.asyncio
async def test_back_to_preview_does_not_send_a_new_message():
    telegram = FakeTelegram()
    state = draft(Note(lead="79990000000", topic="Тема"))
    handler = NoteEditHandler(telegram)

    await handler.start_edit(1, state)
    await handler.show_preview(1, state)

    assert state.state == NoteState.PREVIEW.value
    assert [call[0] for call in telegram.calls] == ["edit_menu", "preview"]
    assert telegram.calls[-1][3] == 500


@pytest.mark.asyncio
async def test_typing_without_selected_field_refreshes_menu():
    telegram = FakeTelegram()
    state = draft(Note(lead="79990000000", topic="Тема"))
    state.state = NoteState.EDITING.value
    state.data["editing_field"] = None

    await NoteEditHandler(telegram).save_edit(1, "Текст", state)

    assert [call[0] for call in telegram.calls] == ["edit_menu"]
    assert "Выберите поле" in telegram.calls[0][3]
    assert state.data["note"]["topic"] == "Тема"


@pytest.mark.asyncio
async def test_cancel_clears_active_note_and_removes_buttons():
    telegram = FakeTelegram()
    state = draft(Note(description="text", topic="Тема"))

    await NoteEditHandler(telegram).cancel(1, state)

    assert state.state is None
    assert state.data == {}
    assert telegram.calls == [("cancelled", 500), ("next_note", 1)]


@pytest.mark.asyncio
async def test_two_successive_corrections_make_history_instead_of_overwriting():
    telegram = FakeTelegram()
    state = draft(Note(lead="79990000000", topic="Старая тема"))
    handler = NoteEditHandler(telegram)

    await handler.start_edit(1, state)
    await handler.select_field(1, "topic", state)
    await handler.save_edit(1, "Новая тема", state)

    await handler.start_edit(1, state)
    await handler.select_field(1, "description", state)
    await handler.save_edit(1, "Описание после правки", state)

    revisions = [call for call in telegram.calls if call[0] == "revised_preview"]
    assert [(call[3], call[4]) for call in revisions] == [(500, 501), (501, 502)]
    assert revisions[0][5].topic == "Старая тема"
    assert revisions[1][5].topic == "Новая тема"
    assert state.data["note"]["description"] == "Описание после правки"
    assert state.data["ui_message_id"] == 502


@pytest.mark.asyncio
async def test_failed_new_message_keeps_original_draft_editable():
    class BrokenTelegram(FakeTelegram):
        async def send_revised_note_preview(self, *args):
            raise RuntimeError("Telegram temporarily unavailable")

    telegram = BrokenTelegram()
    state = draft(Note(lead="79990000000", topic="Старая тема"))
    handler = NoteEditHandler(telegram)
    await handler.start_edit(1, state)
    await handler.select_field(1, "topic", state)

    with pytest.raises(RuntimeError):
        await handler.save_edit(1, "Новая тема", state)

    assert state.state == NoteState.EDITING.value
    assert state.data["note"]["topic"] == "Старая тема"
    assert state.data["editing_field"] == "topic"
    assert state.data["ui_message_id"] == 500
    assert state.data["edit_prompt_message_id"] == 600


@pytest.mark.asyncio
async def test_switch_field_replaces_old_temporary_prompt():
    telegram = FakeTelegram()
    state = draft(Note(lead="79990000000", topic="Тема"))
    handler = NoteEditHandler(telegram)

    await handler.start_edit(1, state)
    await handler.select_field(1, "topic", state)
    await handler.select_field(1, "description", state)

    assert [c for c in telegram.calls if c[0] == "edit_prompt"] == [
        ("edit_prompt", "topic", 600),
        ("edit_prompt", "description", 601),
    ]
    assert telegram.calls[-1] == ("delete_prompt", 600)
    assert state.data["editing_field"] == "description"
    assert state.data["edit_prompt_message_id"] == 601


@pytest.mark.asyncio
async def test_back_from_edit_deletes_temporary_prompt():
    telegram = FakeTelegram()
    state = draft(Note(lead="79990000000", topic="Тема"))
    handler = NoteEditHandler(telegram)

    await handler.start_edit(1, state)
    await handler.select_field(1, "topic", state)
    await handler.show_preview(1, state)

    assert [c[0] for c in telegram.calls] == [
        "edit_menu", "edit_prompt", "preview", "delete_prompt",
    ]
    assert telegram.calls[-1] == ("delete_prompt", 600)
    assert state.data["edit_prompt_message_id"] is None


@pytest.mark.asyncio
async def test_cancel_during_field_edit_deletes_prompt_and_buttons():
    telegram = FakeTelegram()
    state = draft(Note(lead="79990000000", topic="Тема"))
    handler = NoteEditHandler(telegram)

    await handler.start_edit(1, state)
    await handler.select_field(1, "topic", state)
    await handler.cancel(1, state)

    assert telegram.calls[-3:] == [
        ("delete_prompt", 600), ("cancelled", 500), ("next_note", 1),
    ]
    assert state.data == {}


@pytest.mark.asyncio
async def test_delete_failure_does_not_lose_saved_correction():
    class BrokenTelegram(FakeTelegram):
        async def delete_edit_prompt(self, user_id, message_id):
            raise RuntimeError("Delete not available")

    telegram = BrokenTelegram()
    state = draft(Note(lead="79990000000", topic="Старая тема"))
    handler = NoteEditHandler(telegram)
    await handler.start_edit(1, state)
    await handler.select_field(1, "topic", state)
    await handler.save_edit(1, "Новая тема", state)

    assert state.state == NoteState.PREVIEW.value
    assert state.data["note"]["topic"] == "Новая тема"
    assert state.data["edit_prompt_message_id"] is None
    assert state.data["ui_message_id"] == 501
