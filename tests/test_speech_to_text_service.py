from pathlib import Path

import pytest

from bot.services.speech_to_text_service import SpeechToTextService


class WorkingSTT(SpeechToTextService):
    def __init__(self):
        self.seen_path: Path | None = None

    def _transcribe_file(self, audio_path: Path) -> str:
        self.seen_path = audio_path
        assert audio_path.exists()
        assert audio_path.suffix == ".ogg"
        assert audio_path.read_bytes() == b"voice-bytes"
        return "hello"


class FakeWhisperModel:
    def __init__(self):
        self.path: str | None = None

    def transcribe(self, path: str):
        self.path = path
        assert Path(path).exists()
        return {"text": "  распознанный текст  "}


@pytest.mark.asyncio
async def test_temp_audio_is_deleted_after_transcription():
    service = WorkingSTT()

    result = await service.transcribe(b"voice-bytes")

    assert result == "hello"
    assert service.seen_path is not None
    assert not service.seen_path.exists()


@pytest.mark.asyncio
async def test_injected_whisper_model_is_called_and_text_is_trimmed():
    model = FakeWhisperModel()
    service = SpeechToTextService(model=model)

    result = await service.transcribe(b"voice-bytes")

    assert result == "распознанный текст"
    assert model.path is not None
    assert not Path(model.path).exists()
