import pytest

from bot.handlers.voice_handler import VoiceHandler
from bot.models.note import Note
from bot.states.note_states import NoteState
from tests.fakes import FakeMessage, FakeState, FakeTelegram


class STT:
    async def transcribe(self, audio):
        assert audio == b"voice"
        return "transcript"


class Extraction:
    async def extract(self, text):
        assert text == "transcript"
        return Note(lead="+7999", topic="Встреча", description="result")


@pytest.mark.asyncio
async def test_voice_pipeline_creates_one_card_then_edits_it_to_preview():
    telegram = FakeTelegram()
    state = FakeState()

    await VoiceHandler(telegram, STT(), Extraction()).handle_voice(FakeMessage(), state)

    assert state.state == NoteState.PREVIEW.value
    assert state.data["note"]["topic"] == "Встреча"
    assert state.data["flow_id"] == "100"
    assert state.data["ui_message_id"] == 500
    assert [call[0] for call in telegram.calls] == ["processing", "download", "preview"]
    assert telegram.calls[-1][2] == "100"
    assert telegram.calls[-1][3] == 500


@pytest.mark.asyncio
async def test_second_voice_updates_existing_preview_not_new_message():
    telegram = FakeTelegram()
    state = FakeState()
    state.state = NoteState.PREVIEW.value
    state.data.update(
        flow_id="77", ui_message_id=500,
        note=Note(lead="79997654321", topic="Встреча").to_dict(),
    )

    await VoiceHandler(telegram, STT(), Extraction()).handle_voice(FakeMessage(), state)

    assert [call[0] for call in telegram.calls] == ["preview"]
    assert telegram.calls[0][2] == "77"
    assert telegram.calls[0][3] == 500
    assert "Сначала завершите" in telegram.calls[0][4]


@pytest.mark.asyncio
async def test_processing_failure_edits_processing_card_to_error():
    class BrokenSTT:
        async def transcribe(self, audio):
            raise RuntimeError("secret transcript must not be logged")

    telegram = FakeTelegram()
    state = FakeState()

    await VoiceHandler(telegram, BrokenSTT(), Extraction()).handle_voice(FakeMessage(), state)

    assert state.state is None
    assert state.data == {}
    assert [call[0] for call in telegram.calls] == ["processing", "download", "error"]
    assert telegram.calls[-1][2] == 500


@pytest.mark.asyncio
async def test_second_voice_during_processing_does_not_create_any_bot_message():
    telegram = FakeTelegram()
    state = FakeState()
    state.state = NoteState.PROCESSING.value
    state.data.update(flow_id="77", ui_message_id=500)

    await VoiceHandler(telegram, STT(), Extraction()).handle_voice(FakeMessage(), state)

    assert telegram.calls == []


@pytest.mark.asyncio
async def test_second_voice_while_editing_keeps_same_card():
    telegram = FakeTelegram()
    state = FakeState()
    state.state = NoteState.EDITING.value
    state.data.update(flow_id="77", ui_message_id=500, editing_field="topic")

    await VoiceHandler(telegram, STT(), Extraction()).handle_voice(FakeMessage(), state)

    assert telegram.calls[0][0] == "edit_prompt"
    assert telegram.calls[0][3] == 500
    assert "Сначала завершите" in telegram.calls[0][4]
