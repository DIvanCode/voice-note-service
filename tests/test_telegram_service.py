import pytest

from bot.models.note import Note
from bot.services.telegram_service import TelegramService


class FakeBot:
    def __init__(self):
        self.messages = []

    async def send_message(self, user_id, text, **kwargs):
        self.messages.append((user_id, text, kwargs))


@pytest.mark.asyncio
async def test_start_message_contains_voice_instruction():
    bot = FakeBot()
    service = TelegramService(bot)

    await service.send_start(42)

    assert bot.messages
    user_id, text, _ = bot.messages[0]
    assert user_id == 42
    assert "голосовое сообщение" in text
    assert "изменить" in text


@pytest.mark.asyncio
async def test_busy_message_contains_note_action_buttons_bound_to_flow():
    bot = FakeBot()
    service = TelegramService(bot)

    await service.send_busy(42, flow_id="abc", with_actions=True)

    _, text, kwargs = bot.messages[0]
    assert "Сначала завершите текущую заметку" in text

    keyboard = kwargs["reply_markup"].inline_keyboard
    callbacks = [row[0].callback_data for row in keyboard]
    assert callbacks == [
        "note:confirm:abc",
        "note:edit:abc",
        "note:cancel:abc",
    ]


@pytest.mark.asyncio
async def test_processing_busy_message_has_no_actions():
    bot = FakeBot()
    service = TelegramService(bot)

    await service.send_busy(42, flow_id=None, with_actions=False)

    _, text, kwargs = bot.messages[0]
    assert "ещё обрабатывается" in text
    assert kwargs["reply_markup"] is None


@pytest.mark.asyncio
async def test_preview_callbacks_are_bound_to_flow():
    bot = FakeBot()
    service = TelegramService(bot)

    await service.send_note_preview(
        42,
        Note(note="text", full_name="Иван", phone="+7999", topic="Тема"),
        flow_id="voice-100",
    )

    _, _, kwargs = bot.messages[0]
    keyboard = kwargs["reply_markup"].inline_keyboard
    callbacks = [row[0].callback_data for row in keyboard]
    assert callbacks == [
        "note:confirm:voice-100",
        "note:edit:voice-100",
        "note:cancel:voice-100",
    ]


@pytest.mark.asyncio
async def test_long_preview_is_truncated_but_complete_note_is_unchanged():
    bot = FakeBot()
    service = TelegramService(bot)
    original_text = "x" * 10000
    note = Note(
        note=original_text,
        full_name="Иван",
        phone="+7999",
        topic="Тема",
    )

    await service.send_note_preview(42, note, flow_id="100")

    _, text, _ = bot.messages[0]
    assert len(text) <= 4096
    assert "сокращено в preview" in text
    assert note.note == original_text
