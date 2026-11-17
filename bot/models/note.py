from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


FIELD_LABELS = {
    "lead": "Лид",
    "topic": "Тема",
    "description": "Описание",
    "next_step": "Следующий шаг",
    "deadline": "Срок",
    "additional_info": "Дополнительная информация",
}
REQUIRED_FIELDS = ("lead", "topic")
RECOMMENDED_FIELDS = ("description", "next_step", "deadline")


@dataclass(slots=True)
class Note:
    """Structured note prepared for review before CRM submission."""

    lead: str | None = None
    topic: str | None = None
    description: str | None = None
    next_step: str | None = None
    deadline: str | None = None
    additional_info: str | None = None

    @staticmethod
    def _filled(value: str | None) -> bool:
        return bool(value and value.strip())

    @property
    def missing_required_fields(self) -> tuple[str, ...]:
        return tuple(field for field in REQUIRED_FIELDS if not self._filled(getattr(self, field)))

    @property
    def missing_recommended_fields(self) -> tuple[str, ...]:
        return tuple(field for field in RECOMMENDED_FIELDS if not self._filled(getattr(self, field)))

    @property
    def can_be_sent_to_crm(self) -> bool:
        return not self.missing_required_fields

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Note":
        return cls(**{field: data.get(field) for field in FIELD_LABELS})
