from __future__ import annotations

from typing import Any

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.models.note import FIELD_LABELS, Note

PREVIEW_DESCRIPTION_LIMIT = 2500
PREVIEW_FIELD_LIMIT = 180


class TelegramService:
    def __init__(self, bot: Bot):
        self.bot = bot

    async def download_voice(self, message: Any) -> bytes:
        if message.voice is None:
            raise ValueError("Message does not contain a voice attachment")

        stream = await self.bot.download(message.voice)
        if stream is None:
            raise RuntimeError("Telegram returned no voice file")
        return stream.getvalue()

    async def send_start(self, user_id: int) -> None:
        await self.bot.send_message(
            user_id,
            "Привет! Расскажите голосом об итогах встречи — я соберу заметку и покажу её вам перед отправкой в CRM.\n\n"
            "Для отправки нужны лид (адрес объекта или телефон человека) и тема. "
            "Описание, следующий шаг и срок лучше тоже указать. При желании добавьте другую важную информацию.\n\n"
            "Любое поле можно исправить перед подтверждением.",
        )

    async def send_note_preview(self, user_id: int, note: Note, flow_id: str) -> None:
        field_lines = [
            f"{label}:\n{self._preview_value(getattr(note, field), PREVIEW_DESCRIPTION_LIMIT if field == 'description' else PREVIEW_FIELD_LIMIT)}"
            for field, label in FIELD_LABELS.items()
        ]
        text = "Проверьте заметку перед отправкой:\n\n" + "\n\n".join(field_lines)
        if note.missing_required_fields:
            labels = ", ".join(FIELD_LABELS[field] for field in note.missing_required_fields)
            text += f"\n\nЧтобы отправить заметку в CRM, добавьте: {labels}. Лид — это адрес объекта или телефон человека."
        if note.missing_recommended_fields:
            labels = ", ".join(FIELD_LABELS[field] for field in note.missing_recommended_fields)
            text += f"\n\nСоветую дополнить: {labels}. Заметку можно отправить и без них."

        buttons = self._action_buttons(flow_id, note.can_be_sent_to_crm)
        await self.bot.send_message(
            user_id,
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        )

    @staticmethod
    def _action_buttons(flow_id: str, can_confirm: bool) -> list[list[InlineKeyboardButton]]:
        buttons = []
        if can_confirm:
            buttons.append([InlineKeyboardButton(text="Отправить в CRM", callback_data=f"note:confirm:{flow_id}")])
        buttons.append([InlineKeyboardButton(text="Исправить", callback_data=f"note:edit:{flow_id}")])
        buttons.append([InlineKeyboardButton(text="Отменить", callback_data=f"note:cancel:{flow_id}")])
        return buttons

    async def send_edit_menu(self, user_id: int, flow_id: str) -> None:
        buttons = [
            [InlineKeyboardButton(text=label, callback_data=f"note:field:{flow_id}:{field}")]
            for field, label in FIELD_LABELS.items()
        ]
        buttons.append([InlineKeyboardButton(text="Отменить заметку", callback_data=f"note:cancel:{flow_id}")])
        await self.bot.send_message(
            user_id,
            "Что хотите изменить?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        )

    async def send_edit_prompt(self, user_id: int, field: str) -> None:
        hint = " Укажите адрес объекта или телефон человека." if field == "lead" else ""
        await self.bot.send_message(
            user_id,
            f"Напишите новое значение для поля «{FIELD_LABELS[field]}».{hint} "
            "Если хотите очистить поле, отправьте «-».",
        )

    async def send_success(self, user_id: int) -> None:
        await self.bot.send_message(user_id, "Готово, заметка сохранена в CRM.")

    async def send_error(self, user_id: int, message: str) -> None:
        await self.bot.send_message(user_id, message)

    async def send_busy(
        self,
        user_id: int,
        flow_id: str | None,
        with_actions: bool = True,
        can_confirm: bool = False,
    ) -> None:
        reply_markup = None
        if with_actions and flow_id is not None:
            reply_markup = InlineKeyboardMarkup(
                inline_keyboard=self._action_buttons(flow_id, can_confirm),
            )

        text = (
            "Давайте сначала закончим текущую заметку. Это голосовое можно просто переслать сюда, "
            "когда подтвердите или отмените текущую."
            if with_actions
            else "Я ещё разбираю предыдущее голосовое. Это сообщение можно просто переслать сюда, "
            "когда закончим с текущей заметкой."
        )
        await self.bot.send_message(user_id, text, reply_markup=reply_markup)

    async def send_required_fields(self, user_id: int, fields: tuple[str, ...]) -> None:
        labels = ", ".join(FIELD_LABELS[field] for field in fields)
        lead_hint = " Для лида подойдёт адрес объекта или телефон человека." if "lead" in fields else ""
        await self.bot.send_message(
            user_id,
            f"Пока не могу отправить заметку в CRM: добавьте {labels}.{lead_hint} "
            "Нажмите «Исправить».",
        )

    async def send_cancelled(self, user_id: int) -> None:
        await self.bot.send_message(user_id, "Заметку отменили. Можете отправить новое голосовое.")

    @staticmethod
    def _preview_value(value: str | None, limit: int) -> str:
        if not value or not value.strip():
            return "не указано"
        if len(value) <= limit:
            return value

        suffix = "\n… [текст сокращён]"
        return value[: limit - len(suffix)] + suffix
