from types import SimpleNamespace

import pytest

from bot.main import _validate_flow_callback
from bot.states.note_states import NoteState
from tests.fakes import FakeState


class FakeCallbackBot:
    def __init__(self):
        self.removed = []

    async def edit_message_reply_markup(self, *, chat_id, message_id, reply_markup):
        self.removed.append((chat_id, message_id, reply_markup))


class FakeCallback:
    def __init__(self, message_id=500, bot=None):
        self.answers = []
        self.message = SimpleNamespace(
            message_id=message_id,
            chat=SimpleNamespace(id=42),
        )
        self.bot = bot

    async def answer(self, text=None):
        self.answers.append(text)


@pytest.mark.asyncio
async def test_stale_callback_is_rejected_and_its_buttons_removed():
    state = FakeState()
    state.data.update(flow_id="current", ui_message_id=500)
    bot = FakeCallbackBot()
    callback = FakeCallback(message_id=400, bot=bot)

    result = await _validate_flow_callback(callback, state, "old")

    assert result is False
    assert callback.answers == ["Эта заметка уже неактуальна."]
    assert bot.removed == [(42, 400, None)]
    assert state.data["flow_id"] == "current"


@pytest.mark.asyncio
async def test_callback_from_different_card_is_rejected_even_if_flow_matches():
    state = FakeState()
    state.data.update(flow_id="current", ui_message_id=500)
    bot = FakeCallbackBot()
    callback = FakeCallback(message_id=300, bot=bot)

    result = await _validate_flow_callback(callback, state, "current")

    assert result is False
    assert bot.removed == [(42, 300, None)]


@pytest.mark.asyncio
async def test_current_callback_is_accepted_only_for_active_card_and_state():
    state = FakeState()
    state.data.update(flow_id="current", ui_message_id=500)
    state.state = NoteState.PREVIEW.value
    callback = FakeCallback(message_id=500)

    result = await _validate_flow_callback(
        callback, state, "current",
        allowed_states=(NoteState.PREVIEW.value,),
    )

    assert result is True
    assert callback.answers == [None]


@pytest.mark.asyncio
async def test_confirm_is_rejected_during_saving_to_avoid_double_post():
    state = FakeState()
    state.data.update(flow_id="current", ui_message_id=500)
    state.state = NoteState.SAVING.value
    callback = FakeCallback(message_id=500)

    result = await _validate_flow_callback(
        callback, state, "current",
        allowed_states=(NoteState.PREVIEW.value,),
    )

    assert result is False
    assert callback.answers == ["Это действие сейчас недоступно."]
