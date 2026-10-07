from __future__ import annotations

from typing import Any

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.models.note import Note

PREVIEW_NOTE_LIMIT = 3000
PREVIEW_FIELD_LIMIT = 250


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
            "Привет! Отправьте голосовое сообщение с итогами встречи с клиентом.\n\n"
            "Я распознаю речь, сформирую заметку и покажу её перед отправкой. "
            "После обработки можно изменить тему, текст заметки, ФИО и телефон "
            "или отменить текущую заметку.\n\n"
            "Пока предыдущая заметка не подтверждена или не отменена, новое "
            "голосовое сообщение не принимается.",
        )

    async def send_note_preview(self, user_id: int, note: Note, flow_id: str) -> None:
        text = (
            "Сформированная заметка:\n\n"
            f"Тема:\n{self._preview_value(note.topic, PREVIEW_FIELD_LIMIT)}\n\n"
            f"Заметка:\n{self._preview_value(note.note, PREVIEW_NOTE_LIMIT)}\n\n"
            f"ФИО:\n{self._preview_value(note.full_name, PREVIEW_FIELD_LIMIT)}\n\n"
            f"Телефон:\n{self._preview_value(note.phone, PREVIEW_FIELD_LIMIT)}"
        )

        buttons: list[list[InlineKeyboardButton]] = []
        if note.can_be_sent_to_crm:
            buttons.append(
                [
                    InlineKeyboardButton(
                        text="Подтвердить",
                        callback_data=f"note:confirm:{flow_id}",
                    )
                ]
            )
        buttons.append(
            [
                InlineKeyboardButton(
                    text="Редактировать",
                    callback_data=f"note:edit:{flow_id}",
                )
            ]
        )
        buttons.append(
            [
                InlineKeyboardButton(
                    text="Отменить",
                    callback_data=f"note:cancel:{flow_id}",
                )
            ]
        )

        await self.bot.send_message(
            user_id,
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        )

        if not note.can_be_sent_to_crm:
            await self.bot.send_message(
                user_id,
                "Тема не определена. Такая заметка не может быть отправлена в CRM. "
                "Отредактируйте тему или скопируйте заметку вручную.",
            )

    async def send_edit_menu(self, user_id: int, flow_id: str) -> None:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Тема",
                        callback_data=f"note:field:{flow_id}:topic",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="Заметка",
                        callback_data=f"note:field:{flow_id}:note",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="ФИО",
                        callback_data=f"note:field:{flow_id}:full_name",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="Телефон",
                        callback_data=f"note:field:{flow_id}:phone",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="Отменить заметку",
                        callback_data=f"note:cancel:{flow_id}",
                    )
                ],
            ]
        )
        await self.bot.send_message(user_id, "Что нужно изменить?", reply_markup=keyboard)

    async def send_edit_prompt(self, user_id: int, field: str) -> None:
        labels = {
            "topic": "тему",
            "note": "текст заметки",
            "full_name": "ФИО",
            "phone": "телефон",
        }
        suffix = " Для очистки поля отправьте '-'. " if field != "note" else ""
        await self.bot.send_message(
            user_id,
            f"Отправьте новое значение для поля «{labels[field]}».{suffix}",
        )

    async def send_success(self, user_id: int) -> None:
        await self.bot.send_message(user_id, "Заметка успешно сохранена в CRM.")

    async def send_error(self, user_id: int, message: str) -> None:
        await self.bot.send_message(user_id, message)

    async def send_busy(
        self,
        user_id: int,
        flow_id: str | None,
        with_actions: bool = True,
    ) -> None:
        reply_markup = None
        if with_actions and flow_id is not None:
            reply_markup = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="Подтвердить",
                            callback_data=f"note:confirm:{flow_id}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="Редактировать",
                            callback_data=f"note:edit:{flow_id}",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="Отменить",
                            callback_data=f"note:cancel:{flow_id}",
                        )
                    ],
                ]
            )

        await self.bot.send_message(
            user_id,
            "Сначала завершите текущую заметку: подтвердите, отредактируйте или отмените её."
            if with_actions
            else "Текущее голосовое сообщение ещё обрабатывается. Дождитесь результата.",
            reply_markup=reply_markup,
        )

    async def send_topic_required(self, user_id: int) -> None:
        await self.bot.send_message(
            user_id,
            "Нельзя отправить заметку в CRM без темы. Сначала укажите тему через редактирование.",
        )

    async def send_cancelled(self, user_id: int) -> None:
        await self.bot.send_message(
            user_id,
            "Текущая заметка отменена. Можно отправить новое голосовое сообщение.",
        )

    @staticmethod
    def _preview_value(value: str | None, limit: int) -> str:
        if not value:
            return "не определено"
        if len(value) <= limit:
            return value

        suffix = "\n… [сокращено в preview]"
        return value[: limit - len(suffix)] + suffix
