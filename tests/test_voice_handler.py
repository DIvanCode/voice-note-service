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
        return Note(
            note="result",
            full_name="Иван Иванов",
            phone="+7999",
            topic="Встреча",
        )


@pytest.mark.asyncio
async def test_voice_pipeline_stores_note_and_shows_preview():
    telegram = FakeTelegram()
    state = FakeState()
    handler = VoiceHandler(telegram, STT(), Extraction())

    await handler.handle_voice(FakeMessage(), state)

    assert state.state == NoteState.PREVIEW.value
    assert state.data["note"]["topic"] == "Встреча"
    assert state.data["flow_id"] == "100"
    assert [call[0] for call in telegram.calls] == ["download", "preview"]
    assert telegram.calls[-1][2] == "100"


@pytest.mark.asyncio
async def test_second_voice_is_rejected_while_note_is_active():
    telegram = FakeTelegram()
    state = FakeState()
    state.state = NoteState.PREVIEW.value
    state.data["flow_id"] = "77"
    handler = VoiceHandler(telegram, STT(), Extraction())

    await handler.handle_voice(FakeMessage(), state)

    assert telegram.calls == [("busy", True, "77")]


@pytest.mark.asyncio
async def test_processing_failure_clears_state():
    class BrokenSTT:
        async def transcribe(self, audio):
            raise RuntimeError("secret transcript must not be logged")

    telegram = FakeTelegram()
    state = FakeState()
    handler = VoiceHandler(telegram, BrokenSTT(), Extraction())

    await handler.handle_voice(FakeMessage(), state)

    assert state.state is None
    assert state.data == {}
    assert telegram.calls[-1][0] == "error"


@pytest.mark.asyncio
async def test_second_voice_during_processing_has_no_invalid_actions():
    telegram = FakeTelegram()
    state = FakeState()
    state.state = NoteState.PROCESSING.value
    handler = VoiceHandler(telegram, STT(), Extraction())

    await handler.handle_voice(FakeMessage(), state)

    assert telegram.calls == [("busy", False, None)]
