import pytest

from bot.handlers.note_confirmation_handler import NoteConfirmationHandler
from bot.models.note import Note
from bot.services.crm_service import CRMNotConfiguredError
from bot.states.note_states import NoteState
from tests.fakes import FakeState, FakeTelegram


class SuccessfulCRM:
    def __init__(self):
        self.notes = []

    async def create_note(self, note):
        self.notes.append(note)


@pytest.mark.asyncio
async def test_note_without_topic_is_not_sent_to_crm():
    telegram = FakeTelegram()
    crm = SuccessfulCRM()
    state = FakeState()
    state.data["note"] = Note(note="text", topic=None).to_dict()
    handler = NoteConfirmationHandler(telegram, crm)

    await handler.confirm(1, state)

    assert crm.notes == []
    assert state.state == NoteState.PREVIEW.value
    assert telegram.calls[-1][0] == "topic_required"


@pytest.mark.asyncio
async def test_successful_save_clears_memory():
    telegram = FakeTelegram()
    crm = SuccessfulCRM()
    state = FakeState()
    state.data["note"] = Note(note="text", topic="Тема").to_dict()
    handler = NoteConfirmationHandler(telegram, crm)

    await handler.confirm(1, state)

    assert len(crm.notes) == 1
    assert state.state is None
    assert state.data == {}
    assert telegram.calls[-1][0] == "success"


@pytest.mark.asyncio
async def test_unconfigured_crm_clears_note_so_user_can_start_again():
    class StubCRM:
        async def create_note(self, note):
            raise CRMNotConfiguredError()

    telegram = FakeTelegram()
    state = FakeState()
    state.data["note"] = Note(note="text", topic="Тема").to_dict()
    handler = NoteConfirmationHandler(telegram, StubCRM())

    await handler.confirm(1, state)

    assert state.state is None
    assert state.data == {}
    assert telegram.calls[-1][0] == "error"
    assert "автоматически отменена" in telegram.calls[-1][1]
