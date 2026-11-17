import pytest

from bot.handlers.note_confirmation_handler import NoteConfirmationHandler
from bot.models.note import Note
from bot.services.crm_service import CRMError, CRMNotConfiguredError
from bot.states.note_states import NoteState
from tests.fakes import FakeState, FakeTelegram


class SuccessfulCRM:
    def __init__(self):
        self.notes = []

    async def create_note(self, note):
        self.notes.append(note)


def draft(note):
    state = FakeState()
    state.state = NoteState.PREVIEW.value
    state.data.update(note=note.to_dict(), flow_id="123", ui_message_id=500)
    return state


@pytest.mark.asyncio
async def test_note_without_topic_is_not_sent_to_crm():
    telegram = FakeTelegram()
    crm = SuccessfulCRM()
    state = draft(Note(lead="ул. Лесная, 1", topic=None))

    await NoteConfirmationHandler(telegram, crm).confirm(1, state)

    assert crm.notes == []
    assert state.state == NoteState.PREVIEW.value
    assert telegram.calls[-1][0] == "preview"
    assert telegram.calls[-1][3] == 500
    assert "добавьте Тема" in telegram.calls[-1][4]


@pytest.mark.asyncio
async def test_note_without_lead_is_not_sent_to_crm_even_if_topic_is_set():
    telegram = FakeTelegram()
    crm = SuccessfulCRM()
    state = draft(Note(lead="  ", topic="Встреча"))

    await NoteConfirmationHandler(telegram, crm).confirm(1, state)

    assert crm.notes == []
    assert state.state == NoteState.PREVIEW.value
    assert "добавьте Лид" in telegram.calls[-1][4]


@pytest.mark.asyncio
async def test_successful_save_clears_memory_and_removes_actions():
    telegram = FakeTelegram()
    crm = SuccessfulCRM()
    state = draft(Note(lead="+79990000000", topic="Тема"))

    await NoteConfirmationHandler(telegram, crm).confirm(1, state)

    assert len(crm.notes) == 1
    assert crm.notes[0].missing_recommended_fields == ("description", "next_step", "deadline")
    assert state.state is None
    assert state.data == {}
    assert [call[0] for call in telegram.calls] == ["saving", "success", "next_note"]
    assert telegram.calls[0][1] == telegram.calls[1][1] == 500
    assert telegram.calls[-1] == ("next_note", 1)


@pytest.mark.asyncio
async def test_unconfigured_crm_closes_card_and_invites_next_note():
    class StubCRM:
        async def create_note(self, note):
            raise CRMNotConfiguredError()

    telegram = FakeTelegram()
    state = draft(Note(lead="+79990000000", topic="Тема"))

    await NoteConfirmationHandler(telegram, StubCRM()).confirm(1, state)

    assert state.state is None
    assert state.data == {}
    assert [call[0] for call in telegram.calls] == ["saving", "error", "next_note"]
    assert telegram.calls[-2][2] == 500
    assert "не сохранил и закрыл" in telegram.calls[-2][1]
    assert telegram.calls[-1] == ("next_note", 1)


@pytest.mark.asyncio
async def test_known_crm_rejection_restores_draft_and_buttons():
    class RejectingCRM:
        async def create_note(self, note, *, user_phone):
            assert user_phone == "79991234567"
            assert note.lead == "79997654321"
            raise CRMError("no_client_by_phone")

    telegram = FakeTelegram()
    state = draft(Note(lead="79997654321", topic="Встреча", description="Private meeting"))

    await NoteConfirmationHandler(
        telegram, RejectingCRM(), {1: "79991234567"},
    ).confirm(1, state)

    assert state.state == NoteState.PREVIEW.value
    assert state.data["note"]["description"] == "Private meeting"
    assert [call[0] for call in telegram.calls] == ["saving", "preview"]
    # A recoverable CRM rejection keeps the draft active and must not
    # invite a new voice message that the bot would reject as busy.
    assert not any(call[0] == "next_note" for call in telegram.calls)
    assert telegram.calls[-1][3] == 500
    assert "не найден" in telegram.calls[-1][4]
    assert "Private meeting" not in telegram.calls[-1][4]


@pytest.mark.asyncio
async def test_unknown_telegram_id_cannot_save():
    telegram = FakeTelegram()
    crm = SuccessfulCRM()
    state = draft(Note(lead="79997654321", topic="Встреча"))

    await NoteConfirmationHandler(
        telegram, crm, {999: "79991234567"},
    ).confirm(1, state)

    assert crm.notes == []
    assert state.state == NoteState.PREVIEW.value
    assert "Доступ" in telegram.calls[-1][4]
    assert telegram.calls[-1][0] == "preview"


@pytest.mark.asyncio
async def test_successful_crm_request_is_not_retried_when_telegram_edit_fails():
    class FailingTelegram(FakeTelegram):
        async def send_success(self, user_id, message_id, note):
            raise RuntimeError("Telegram edit failed")

    telegram = FailingTelegram()
    crm = SuccessfulCRM()
    state = draft(Note(lead="+79990000000", topic="Тема"))

    await NoteConfirmationHandler(telegram, crm).confirm(1, state)

    assert len(crm.notes) == 1
    assert state.state is None
    assert state.data == {}
    assert telegram.calls[-1] == ("next_note", 1)
