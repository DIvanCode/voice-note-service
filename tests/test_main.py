import pytest

from bot.main import _validate_flow_callback
from tests.fakes import FakeState


class FakeCallback:
    def __init__(self):
        self.answers = []

    async def answer(self, text=None):
        self.answers.append(text)


@pytest.mark.asyncio
async def test_stale_callback_is_rejected():
    state = FakeState()
    state.data["flow_id"] = "current"
    callback = FakeCallback()

    result = await _validate_flow_callback(callback, state, "old")

    assert result is False
    assert callback.answers == ["Эта заметка уже неактуальна."]
    assert state.data["flow_id"] == "current"


@pytest.mark.asyncio
async def test_current_callback_is_accepted():
    state = FakeState()
    state.data["flow_id"] = "current"
    callback = FakeCallback()

    result = await _validate_flow_callback(callback, state, "current")

    assert result is True
    assert callback.answers == [None]
