import pytest

from bot.models.note import Note
from bot.services.telegram_service import TelegramService


class FakeBot:
    def __init__(self):
        self.messages = []

    async def send_message(self, user_id, text, **kwargs):
        self.messages.append((user_id, text, kwargs))


@pytest.mark.asyncio
async def test_start_explains_required_and_recommended_fields():
    bot = FakeBot()
    await TelegramService(bot).send_start(42)

    user_id, text, _ = bot.messages[0]
    assert user_id == 42
    assert "голосом" in text
    assert "адрес объекта или телефон" in text
    assert "следующий шаг и срок" in text


@pytest.mark.asyncio
async def test_busy_message_explains_forwarding_and_only_valid_actions():
    bot = FakeBot()
    service = TelegramService(bot)

    await service.send_busy(42, flow_id="abc", with_actions=True, can_confirm=False)

    _, text, kwargs = bot.messages[0]
    assert "переслать" in text
    callbacks = [row[0].callback_data for row in kwargs["reply_markup"].inline_keyboard]
    assert callbacks == ["note:edit:abc", "note:cancel:abc"]


@pytest.mark.asyncio
async def test_processing_busy_message_has_no_actions():
    bot = FakeBot()
    service = TelegramService(bot)

    await service.send_busy(42, flow_id=None, with_actions=False)

    _, text, kwargs = bot.messages[0]
    assert "переслать" in text
    assert kwargs["reply_markup"] is None


@pytest.mark.asyncio
async def test_preview_warns_about_recommended_fields_but_allows_confirmation():
    bot = FakeBot()
    service = TelegramService(bot)
    await service.send_note_preview(
        42,
        Note(lead="ул. Лесная, 1", topic="Встреча", description="Обсудили квартиру"),
        flow_id="voice-100",
    )

    _, text, kwargs = bot.messages[0]
    assert "Лид:" in text
    assert "Описание:" in text
    assert "Советую дополнить: Следующий шаг, Срок" in text
    callbacks = [row[0].callback_data for row in kwargs["reply_markup"].inline_keyboard]
    assert callbacks == [
        "note:confirm:voice-100",
        "note:edit:voice-100",
        "note:cancel:voice-100",
    ]


@pytest.mark.asyncio
async def test_preview_without_lead_and_topic_has_no_confirmation():
    bot = FakeBot()
    await TelegramService(bot).send_note_preview(42, Note(description="Текст"), "100")

    _, text, kwargs = bot.messages[0]
    assert "добавьте: Лид, Тема" in text
    assert "адрес объекта или телефон" in text
    callbacks = [row[0].callback_data for row in kwargs["reply_markup"].inline_keyboard]
    assert "note:confirm:100" not in callbacks


@pytest.mark.asyncio
async def test_edit_menu_contains_all_six_fields():
    bot = FakeBot()
    await TelegramService(bot).send_edit_menu(42, "100")

    callbacks = [row[0].callback_data for row in bot.messages[0][2]["reply_markup"].inline_keyboard]
    assert callbacks[:-1] == [
        f"note:field:100:{field}"
        for field in ("lead", "topic", "description", "next_step", "deadline", "additional_info")
    ]


@pytest.mark.asyncio
async def test_long_preview_is_truncated_but_complete_description_is_unchanged():
    bot = FakeBot()
    service = TelegramService(bot)
    original_text = "x" * 10000
    note = Note(lead="+7999", topic="Тема", description=original_text)

    await service.send_note_preview(42, note, flow_id="100")

    _, text, _ = bot.messages[0]
    assert len(text) <= 4096
    assert "текст сокращён" in text
    assert note.description == original_text
