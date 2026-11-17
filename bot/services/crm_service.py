"""Safe adapter for the CRM add-note endpoint (key is in the JSON body)."""
from __future__ import annotations

import json
import os
from urllib.parse import urlsplit

import httpx

from bot.models.note import Note

MAX_RESPONSE_BYTES = 16_384
MAX_NOTE_CHARS = 10_000


class CRMNotConfiguredError(RuntimeError):
    """CRM credentials, endpoint or agent identity are not configured."""


class CRMError(RuntimeError):
    """Known CRM rejection or unknown delivery result; never contains PII."""

    def __init__(self, code: str = "unknown_result"):
        self.code = code
        super().__init__(code)

    @property
    def user_message(self) -> str:
        messages = {
            "no_client_by_phone": "Клиент с таким номером не найден в CRM. Проверьте телефон.",
            "redundant_client_by_phone": "В CRM найдено несколько клиентов с этим номером. Уточните привязку вручную.",
            "no_user_by_phone": "CRM не нашла активного сотрудника. Обратитесь к администратору.",
            "bad_key": "Ошибка авторизации CRM. Обратитесь к администратору.",
            "no_key": "Ошибка авторизации CRM. Обратитесь к администратору.",
            "empty_note": "CRM отклонила пустую заметку. Проверьте текст.",
            "niether_phone_nor_address": "Для сохранения нужен телефон клиента.",
            "not_implemented": "CRM пока не поддерживает поиск клиента по адресу.",
            "invalid_request": "CRM отклонила данные. Проверьте номер и текст заметки.",
            "test_data": "В заметке остался тестовый номер клиента. Укажите настоящий телефон перед отправкой в CRM.",
        }
        return messages.get(
            self.code,
            "Результат отправки не подтверждён. Проверьте CRM перед повторной попыткой, чтобы не создать дубликат.",
        )


def parse_agent_bindings(raw: str) -> dict[int, str]:
    """Only configured Telegram accounts may act as given CRM employees."""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("CRM_AGENT_BINDINGS must be a JSON object") from exc
    if not isinstance(payload, dict) or len(payload) > 100:
        raise ValueError("CRM_AGENT_BINDINGS must be an object with up to 100 entries")
    result: dict[int, str] = {}
    for uid, phone in payload.items():
        if not isinstance(uid, str) or not uid.isascii() or not uid.isdecimal() or int(uid) <= 0:
            raise ValueError("CRM_AGENT_BINDINGS must use numeric Telegram IDs")
        if not isinstance(phone, str) or not _phone(phone):
            raise ValueError("CRM_AGENT_BINDINGS contains an invalid employee phone")
        result[int(uid)] = _phone(phone)
    return result


def _phone(phone: str | None) -> str:
    if not isinstance(phone, str) or not phone.strip():
        return ""
    if any(ch not in "+0123456789 ()-" for ch in phone):
        return ""
    digits = "".join(ch for ch in phone if ch.isdigit())
    return digits if 6 <= len(digits) <= 18 else ""


def _validate_url(url: str) -> None:
    try:
        parsed = urlsplit(url)
        valid = (
            parsed.scheme in {"http", "https"}
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
            and parsed.path == "/client/add-note"
            and (parsed.scheme == "https" or parsed.hostname in {"mock-crm", "localhost", "127.0.0.1"})
        )
        if valid:
            _ = parsed.port  # Reject malformed port values.
    except ValueError as exc:
        raise ValueError("CRM_URL must be an HTTPS add-note endpoint or the local mock") from exc
    if not valid:
        raise ValueError("CRM_URL must be an HTTPS add-note endpoint or the local mock")


class CRMService:
    def __init__(
        self,
        api_url: str | None = None,
        api_key: str | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._url = api_url if api_url is not None else os.getenv("CRM_URL", "")
        self._api_key = api_key if api_key is not None else os.getenv("CRM_API_KEY", "")
        self._transport = transport
        if self._url:
            _validate_url(self._url)

    async def create_note(self, note: Note, *, user_phone: str | None = None) -> None:
        if not self._url or not self._api_key or not _phone(user_phone):
            raise CRMNotConfiguredError("CRM connection or authorized employee is not configured")
        if not note.can_be_sent_to_crm or not note.note.strip():
            raise CRMError("empty_note")
        client_phone = _phone(note.phone)
        if not client_phone:
            raise CRMError("niether_phone_nor_address")
        # CRM chooses clients solely by phone. Changing the extracted name
        # does not make a synthetic placeholder phone safe for production.
        if urlsplit(self._url).scheme == "https" and client_phone == "79990000000":
            raise CRMError("test_data")
        body = f"Тема: {note.topic.strip()}\n\n{note.note.strip()}"
        if len(body) > MAX_NOTE_CHARS:
            raise CRMError("invalid_request")

        # No retries (POST is not idempotent), no proxies or redirects; credentials
        # are never placed into URL or logs. HTTPS verifies certificates by default.
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(15.0, connect=5.0),
                follow_redirects=False,
                trust_env=False,
                transport=self._transport,
            ) as client:
                response = await client.post(self._url, json={
                    "key": self._api_key,
                    "note": body,
                    "user_phone": _phone(user_phone),
                    "client_phone": client_phone,
                })
        except httpx.RequestError:
            raise CRMError("unknown_result") from None

        if len(response.content) > MAX_RESPONSE_BYTES:
            raise CRMError("unknown_result")
        try:
            result = response.json()
        except ValueError:
            raise CRMError("unknown_result") from None
        if not isinstance(result, dict):
            raise CRMError("unknown_result")
        if result.get("status") == "success":
            agent = result.get("agent")
            valid_success = (
                response.status_code in (200, 201, 500)
                and isinstance(agent, dict)
                and type(agent.get("id")) is int
                and type(agent.get("company_id")) is int
                and isinstance(agent.get("full_name"), str)
                and type(result.get("client_id")) is int
            )
            if valid_success:
                # The documented legacy CRM can return HTTP 500 with a valid
                # success payload. Only this strict shape counts as success.
                return
            raise CRMError("unknown_result")

        known_errors = {
            "no_key", "bad_key", "empty_note", "niether_phone_nor_address",
            "no_user_by_phone", "no_client_by_phone", "redundant_client_by_phone",
            "not_implemented", "invalid_request",
        }
        if result.get("status") == "error" and response.status_code < 500:
            code = result.get("error_code")
            raise CRMError(code if code in known_errors else "unknown_result")
        raise CRMError("unknown_result")
