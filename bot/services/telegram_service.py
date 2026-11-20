from __future__ import annotations

from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
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

    async def send_next_note_prompt(self, user_id: int) -> None:
        """Invite the user to start another note after the current one closes."""
        await self.bot.send_message(
            user_id,
            "🎙️ Готов к следующей заметке!\n"
            "Отправьте голосовое сообщение об итогах новой встречи. "
            "Я расшифрую его, подготовлю заметку и дам проверить её перед отправкой в CRM.",
        )

    async def send_processing(self, user_id: int) -> int:
        """Create a processing message that becomes the first note preview."""
        await self.bot.send_chat_action(user_id, "typing")
        sent = await self.bot.send_message(
            user_id,
            "🎙️ Голосовое получено. Расшифровываю и составляю заметку…",
        )
        return sent.message_id

    async def _edit_card(
        self,
        user_id: int,
        message_id: int,
        text: str,
        buttons: list[list[InlineKeyboardButton]] | None = None,
    ) -> None:
        markup = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
        try:
            await self.bot.edit_message_text(
                text=text,
                chat_id=user_id,
                message_id=message_id,
                reply_markup=markup,
            )
        except TelegramBadRequest as exc:
            # Repeated clicks or a duplicate voice can produce an identical edit.
            if "message is not modified" not in str(exc).lower():
                raise

    @staticmethod
    def _preview_text(
        note: Note, *, show_hints: bool = True,
        heading: str = "Проверьте заметку перед отправкой:",
    ) -> str:
        field_lines = [
            f"{label}:\n{TelegramService._preview_value(getattr(note, field), PREVIEW_DESCRIPTION_LIMIT if field == 'description' else PREVIEW_FIELD_LIMIT)}"
            for field, label in FIELD_LABELS.items()
        ]
        text = heading + "\n\n" + "\n\n".join(field_lines)
        if show_hints and note.missing_required_fields:
            labels = ", ".join(FIELD_LABELS[field] for field in note.missing_required_fields)
            text += f"\n\nЧтобы отправить заметку в CRM, добавьте: {labels}. Для CRM нужен телефон клиента в поле «Лид»."
        if show_hints and note.missing_recommended_fields:
            labels = ", ".join(FIELD_LABELS[field] for field in note.missing_recommended_fields)
            text += f"\n\nСоветую дополнить: {labels}. Заметку можно отправить и без них."
        return text

    async def send_note_preview(
        self,
        user_id: int,
        note: Note,
        flow_id: str,
        message_id: int,
        *,
        notice: str | None = None,
    ) -> None:
        text = self._preview_text(note)
        if notice:
            text = notice + "\n\n" + text
        await self._edit_card(
            user_id, message_id, text,
            self._action_buttons(flow_id, note.can_be_sent_to_crm),
        )

    @staticmethod
    def _action_buttons(flow_id: str, can_confirm: bool) -> list[list[InlineKeyboardButton]]:
        buttons = []
        if can_confirm:
            buttons.append([InlineKeyboardButton(text="Отправить в CRM", callback_data=f"note:confirm:{flow_id}")])
        buttons.append([InlineKeyboardButton(text="Исправить", callback_data=f"note:edit:{flow_id}")])
        buttons.append([InlineKeyboardButton(text="Отменить", callback_data=f"note:cancel:{flow_id}")])
        return buttons

    async def send_edit_menu(
        self, user_id: int, flow_id: str, message_id: int, note: Note,
        *, notice: str | None = None,
    ) -> None:
        buttons = [
            [InlineKeyboardButton(text=label, callback_data=f"note:field:{flow_id}:{field}")]
            for field, label in FIELD_LABELS.items()
        ]
        buttons.append([InlineKeyboardButton(text="← К заметке", callback_data=f"note:preview:{flow_id}")])
        buttons.append([InlineKeyboardButton(text="Отменить заметку", callback_data=f"note:cancel:{flow_id}")])
        text = self._preview_text(note, show_hints=False) + "\n\n✏️ Что хотите изменить?"
        if notice:
            text = notice + "\n\n" + text
        await self._edit_card(user_id, message_id, text, buttons)

    async def send_edit_prompt(self, user_id: int, field: str) -> int:
        """Ask for a field value in a separate temporary chat message."""
        hint = " Укажите телефон клиента для поиска в CRM." if field == "lead" else ""
        sent = await self.bot.send_message(
            user_id,
            f"✏️ Редактируем поле «{FIELD_LABELS[field]}».\n"
            f"Отправьте новое значение.{hint} "
            "Чтобы очистить поле, отправьте «-».",
        )
        return sent.message_id

    async def delete_edit_prompt(self, user_id: int, message_id: int) -> None:
        """Delete a temporary field prompt; keep note history untouched."""
        await self.bot.delete_message(chat_id=user_id, message_id=message_id)

    async def send_revised_note_preview(
        self,
        user_id: int,
        note: Note,
        flow_id: str,
        previous_message_id: int,
        previous_note: Note,
    ) -> int:
        """Keep the previous note as history without actions; send an updated card."""
        # First remove the old actions so that only the new revision can be
        # confirmed. Preserve the original fields instead of leaving an edit prompt.
        await self._edit_card(
            user_id,
            previous_message_id,
            self._preview_text(
                previous_note, show_hints=False, heading="Предыдущая версия заметки:"
            ),
        )
        sent = await self.bot.send_message(
            user_id,
            self._preview_text(note),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=self._action_buttons(flow_id, note.can_be_sent_to_crm)
            ),
        )
        return sent.message_id

    async def send_saving(self, user_id: int, message_id: int) -> None:
        # Disable the submit button while the CRM request is in flight.
        await self._edit_card(user_id, message_id, "⏳ Отправляю заметку в CRM…")

    async def send_success(self, user_id: int, message_id: int, note: Note) -> None:
        await self._edit_card(
            user_id, message_id,
            self._preview_text(note, show_hints=False, heading="✅ Заметка сохранена в CRM."),
        )

    async def send_error(self, user_id: int, message: str, message_id: int | None = None) -> None:
        if message_id is None:
            await self.bot.send_message(user_id, message)
        else:
            await self._edit_card(user_id, message_id, "❌ " + message)

    async def send_cancelled(self, user_id: int, message_id: int) -> None:
        await self._edit_card(
            user_id, message_id,
            "Заметку отменили.",
        )

    @staticmethod
    def _preview_value(value: str | None, limit: int) -> str:
        if not value or not value.strip():
            return "не указано"
        if len(value) <= limit:
            return value

        suffix = "\n… [текст сокращён]"
        return value[: limit - len(suffix)] + suffix
