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
        self.card_id = 500
        self.prompt_id = 600

    async def download_voice(self, message):
        self.calls.append(("download", None))
        return self.audio

    async def send_processing(self, user_id):
        self.calls.append(("processing", user_id))
        return self.card_id

    async def send_note_preview(self, user_id, note, flow_id, message_id, *, notice=None):
        self.calls.append(("preview", note, flow_id, message_id, notice))

    async def send_success(self, user_id, message_id, note):
        self.calls.append(("success", message_id, note))

    async def send_saving(self, user_id, message_id):
        self.calls.append(("saving", message_id))

    async def send_error(self, user_id, message, message_id=None):
        self.calls.append(("error", message, message_id))

    async def send_edit_menu(self, user_id, flow_id, message_id, note, *, notice=None):
        self.calls.append(("edit_menu", flow_id, message_id, notice, note))

    async def send_edit_prompt(self, user_id, field):
        prompt_id = self.prompt_id
        self.prompt_id += 1
        self.calls.append(("edit_prompt", field, prompt_id))
        return prompt_id

    async def delete_edit_prompt(self, user_id, message_id):
        self.calls.append(("delete_prompt", message_id))

    async def send_revised_note_preview(
        self, user_id, note, flow_id, previous_message_id, previous_note,
    ):
        self.card_id += 1
        self.calls.append((
            "revised_preview", note, flow_id, previous_message_id, self.card_id, previous_note,
        ))
        return self.card_id

    async def send_cancelled(self, user_id, message_id):
        self.calls.append(("cancelled", message_id))

    async def send_next_note_prompt(self, user_id):
        self.calls.append(("next_note", user_id))
