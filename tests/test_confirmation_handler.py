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


@pytest.mark.asyncio
async def test_known_crm_error_preserves_note_and_does_not_report_success():
    from bot.services.crm_service import CRMError

    class RejectingCRM:
        async def create_note(self, note, *, user_phone):
            assert user_phone == "79991234567"
            raise CRMError("no_client_by_phone")

    telegram = FakeTelegram()
    state = FakeState()
    state.data["note"] = Note(note="private text", phone="79990000000", topic="Встреча").to_dict()
    handler = NoteConfirmationHandler(telegram, RejectingCRM(), {1: "79991234567"})

    await handler.confirm(1, state)

    assert state.state == NoteState.PREVIEW.value
    assert state.data["note"]["note"] == "private text"
    assert telegram.calls[-1][0] == "error"
    assert "не найден" in telegram.calls[-1][1]
    assert "private text" not in telegram.calls[-1][1]


@pytest.mark.asyncio
async def test_unbound_user_cannot_send_to_crm():
    telegram = FakeTelegram()
    crm = SuccessfulCRM()
    state = FakeState()
    state.data["note"] = Note(note="text", phone="79990000000", topic="Встреча").to_dict()
    handler = NoteConfirmationHandler(telegram, crm, {999: "79991234567"})

    await handler.confirm(1, state)

    assert crm.notes == []
    assert state.state == NoteState.PREVIEW.value
    assert "Доступ" in telegram.calls[-1][1]
