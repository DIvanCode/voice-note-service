from types import SimpleNamespace

import pytest

from bot.models.note import Note
from bot.services.telegram_service import TelegramService


class FakeBot:
    def __init__(self):
        self.messages = []
        self.edits = []
        self.actions = []

    async def send_message(self, user_id, text, **kwargs):
        self.messages.append((user_id, text, kwargs))
        return SimpleNamespace(message_id=500)

    async def send_chat_action(self, user_id, action):
        self.actions.append((user_id, action))

    async def edit_message_text(self, *, chat_id, message_id, text, reply_markup=None):
        self.edits.append((chat_id, message_id, text, reply_markup))
        return True


def callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


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
async def test_processing_shows_typing_and_creates_only_one_card():
    bot = FakeBot()
    card_id = await TelegramService(bot).send_processing(42)

    assert bot.actions == [(42, "typing")]
    assert card_id == 500
    assert len(bot.messages) == 1
    assert "Голосовое получено" in bot.messages[0][1]
    assert bot.edits == []


@pytest.mark.asyncio
async def test_preview_updates_original_card_and_allows_confirmation():
    bot = FakeBot()
    service = TelegramService(bot)
    await service.send_note_preview(
        42,
        Note(lead="79997654321", topic="Встреча", description="Обсудили квартиру"),
        flow_id="voice-100", message_id=500,
    )

    chat_id, message_id, text, markup = bot.edits[0]
    assert (chat_id, message_id) == (42, 500)
    assert bot.messages == []
    assert "Лид:" in text
    assert "Описание:" in text
    assert "Советую дополнить: Следующий шаг, Срок" in text
    assert callbacks(markup) == [
        "note:confirm:voice-100",
        "note:edit:voice-100",
        "note:cancel:voice-100",
    ]


@pytest.mark.asyncio
async def test_preview_without_lead_and_topic_has_no_confirmation():
    bot = FakeBot()
    await TelegramService(bot).send_note_preview(
        42, Note(description="Текст"), "100", 500,
    )

    _, _, text, markup = bot.edits[0]
    assert "добавьте: Лид, Тема" in text
    assert "телефон клиента" in text
    assert "note:confirm:100" not in callbacks(markup)


@pytest.mark.asyncio
async def test_edit_menu_contains_all_six_fields_and_navigation():
    bot = FakeBot()
    service = TelegramService(bot)
    await service.send_edit_menu(42, "100", 500)

    cb = callbacks(bot.edits[0][3])
    assert cb == [
        f"note:field:100:{field}"
        for field in ("lead", "topic", "description", "next_step", "deadline", "additional_info")
    ] + ["note:preview:100", "note:cancel:100"]
    assert bot.messages == []


@pytest.mark.asyncio
async def test_edit_prompt_and_return_are_edits_to_the_same_card():
    bot = FakeBot()
    service = TelegramService(bot)
    await service.send_edit_prompt(42, "lead", "100", 500)
    await service.send_edit_menu(42, "100", 500)

    assert len(bot.messages) == 0
    assert [edit[1] for edit in bot.edits] == [500, 500]
    assert "телефон клиента" in bot.edits[0][2]
    assert callbacks(bot.edits[0][3]) == ["note:edit:100", "note:cancel:100"]


@pytest.mark.asyncio
async def test_send_and_cancel_remove_buttons_without_new_message():
    bot = FakeBot()
    service = TelegramService(bot)
    note = Note(lead="79990000000", topic="Тема", description="Описание")
    await service.send_note_preview(42, note, "100", 500)
    await service.send_saving(42, 500)
    await service.send_success(42, 500, note)

    assert len(bot.messages) == 0
    assert len(bot.edits) == 3
    assert all(edit[1] == 500 for edit in bot.edits)
    assert bot.edits[0][3] is not None
    assert bot.edits[1][3] is None
    assert bot.edits[2][3] is None
    assert "сохранена в CRM" in bot.edits[-1][2]

    await service.send_cancelled(42, 500)
    assert bot.edits[-1][3] is None


@pytest.mark.asyncio
async def test_long_preview_is_truncated_but_complete_description_is_unchanged():
    bot = FakeBot()
    service = TelegramService(bot)
    original_text = "x" * 10000
    note = Note(lead="+7999", topic="Тема", description=original_text)

    await service.send_note_preview(42, note, flow_id="100", message_id=500)

    text = bot.edits[0][2]
    assert len(text) <= 4096
    assert "текст сокращён" in text
    assert note.description == original_text
