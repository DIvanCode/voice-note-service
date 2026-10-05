from bot.models.note import Note


class CRMNotConfiguredError(RuntimeError):
    """Raised while the CRM API contract is still unknown."""


class CRMService:
    """CRM integration boundary.

    The production API, authentication/account binding and entity matching are
    intentionally not guessed here. They must be implemented after the CRM
    contract is provided.
    """

    async def create_note(self, note: Note) -> None:
        raise CRMNotConfiguredError("CRM integration is not configured yet")
