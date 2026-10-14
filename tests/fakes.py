from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace


class FakeState:
    def __init__(self):
        self.state = None
        self.data = {}

    async def get_state(self):
        return self.state

    async def set_state(self, state):
        self.state = state

    async def get_data(self):
        return dict(self.data)

    async def update_data(self, **kwargs):
        self.data.update(kwargs)

    async def clear(self):
        self.state = None
        self.data = {}


@dataclass
class FakeMessage:
    user_id: int = 1
    message_id: int = 100

    def __post_init__(self):
        self.from_user = SimpleNamespace(id=self.user_id)


class FakeTelegram:
    def __init__(self, audio: bytes = b"voice"):
        self.audio = audio
        self.calls = []

    async def download_voice(self, message):
        self.calls.append(("download", None))
        return self.audio

    async def send_note_preview(self, user_id, note, flow_id):
        self.calls.append(("preview", note, flow_id))

    async def send_success(self, user_id):
        self.calls.append(("success", None))

    async def send_error(self, user_id, message):
        self.calls.append(("error", message))

    async def send_busy(self, user_id, flow_id, with_actions=True):
        self.calls.append(("busy", with_actions, flow_id))

    async def send_topic_required(self, user_id):
        self.calls.append(("topic_required", None))

    async def send_edit_menu(self, user_id, flow_id):
        self.calls.append(("edit_menu", flow_id))

    async def send_edit_prompt(self, user_id, field):
        self.calls.append(("edit_prompt", field))

    async def send_cancelled(self, user_id):
        self.calls.append(("cancelled", None))
