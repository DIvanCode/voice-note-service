from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(slots=True)
class Note:
    """Structured note produced by the text extraction model."""

    note: str
    full_name: str | None = None
    phone: str | None = None
    topic: str | None = None

    @property
    def can_be_sent_to_crm(self) -> bool:
        """A topic is mandatory before the note may be sent to CRM."""
        return bool(self.topic and self.topic.strip())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Note":
        return cls(
            note=data["note"],
            full_name=data.get("full_name"),
            phone=data.get("phone"),
            topic=data.get("topic"),
        )
