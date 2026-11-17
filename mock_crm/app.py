"""A small CRM HTTP server implementing the supplied add-note contract.

Fixtures are synthetic. Created notes exist only in process memory, never on disk.
The administrative browser view uses HTTP Basic auth and is exposed on loopback
by Compose; use SSH port forwarding for remote access.
"""
from __future__ import annotations

import html
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

MAX_REQUEST_BYTES = 32_768
MAX_NOTE_CHARS = 10_000
MAX_STORED_NOTES = 1_000
basic = HTTPBasic(auto_error=False)


def _phone(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    stripped = value.strip()
    if not stripped or any(char not in "+0123456789 ()-" for char in stripped):
        return ""
    digits = "".join(char for char in stripped if char.isdigit())
    return digits if 6 <= len(digits) <= 18 else ""


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"status": "error", "error_code": code, "message": message},
    )


def create_app(
    *,
    api_key: str | None = None,
    view_password: str | None = None,
    fixtures: dict[str, Any] | None = None,
) -> FastAPI:
    api_key = api_key if api_key is not None else os.getenv("MOCK_CRM_API_KEY")
    view_password = (
        view_password if view_password is not None else os.getenv("MOCK_CRM_VIEW_PASSWORD")
    )
    if not api_key or len(api_key) < 16 or not view_password or len(view_password) < 16:
        raise RuntimeError("Set strong MOCK_CRM_API_KEY and MOCK_CRM_VIEW_PASSWORD (min 16 chars)")
    if secrets.compare_digest(api_key, view_password):
        raise RuntimeError("Mock CRM API and viewer credentials must differ")

    data = fixtures if fixtures is not None else json.loads(
        Path(__file__).with_name("fixtures.json").read_text(encoding="utf-8")
    )
    agents, clients = data["agents"], data["clients"]
    notes: list[dict[str, Any]] = []
    app = FastAPI(title="Mock CRM", docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def no_cache(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'"
        )
        return response

    def require_viewer(credentials: HTTPBasicCredentials | None = Depends(basic)) -> None:
        valid = (
            credentials is not None
            and secrets.compare_digest(credentials.username.encode(), b"viewer")
            and secrets.compare_digest(credentials.password.encode(), view_password.encode())
        )
        if not valid:
            from fastapi import HTTPException

            raise HTTPException(
                status_code=401,
                detail="Authentication required",
                headers={"WWW-Authenticate": 'Basic realm="Mock CRM notes"'},
            )

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.post("/client/add-note")
    async def add_note(request: Request):
        if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
            return _error(415, "invalid_request", "Ожидается application/json")
        try:
            content_length = int(request.headers.get("content-length") or 0)
        except ValueError:
            return _error(400, "invalid_request", "Некорректный Content-Length")
        if content_length > MAX_REQUEST_BYTES:
            return _error(413, "invalid_request", "Слишком большой запрос")

        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_REQUEST_BYTES:
                return _error(413, "invalid_request", "Слишком большой запрос")
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _error(400, "invalid_request", "Некорректный JSON")
        if not isinstance(payload, dict):
            return _error(400, "invalid_request", "Ожидается JSON-объект")

        key = payload.get("key")
        if not isinstance(key, str) or not key:
            return _error(403, "no_key", "Ключ не указан")
        if not secrets.compare_digest(key, api_key):
            return _error(400, "bad_key", "Ключ не найден")
        note = payload.get("note")
        if not isinstance(note, str) or not note.strip():
            return _error(400, "empty_note", "Заметка не указана")
        if len(note) > MAX_NOTE_CHARS:
            return _error(400, "invalid_request", "Заметка слишком длинная")

        client_phone = _phone(payload.get("client_phone"))
        address = payload.get("client_address")
        has_address = isinstance(address, dict) and bool(
            address.get("street_name") and address.get("house_number")
        )
        if not client_phone:
            if has_address:
                return _error(501, "not_implemented", "Поиск по адресу еще не реализован полноценно")
            return _error(400, "niether_phone_nor_address", "Не указан ни телефон клиента ни адрес")

        user_phone = _phone(payload.get("user_phone"))
        agent = next((item for item in agents if item["active"] and _phone(item["phone"]) == user_phone), None)
        if agent is None:
            return _error(404, "no_user_by_phone", "Не найден активный сотрудник с таким телефоном.")
        matches = [
            item for item in clients
            if _phone(item["phone"]) == client_phone and item["company_id"] == agent["company_id"]
        ]
        if not matches:
            return _error(404, "no_client_by_phone", "Не найден клиент с таким телефоном")
        if len(matches) > 1:
            return _error(409, "redundant_client_by_phone", "Найдено более одного клиента с таким телефоном")

        if len(notes) >= MAX_STORED_NOTES:
            return _error(507, "storage_full", "Тестовое хранилище заметок заполнено")
        client = matches[0]
        notes.append({
            "id": len(notes) + 1,
            "client_id": client["id"],
            "agent_id": agent["id"],
            "note": note.strip(),
            "type": "public",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        return JSONResponse(status_code=201, content={
            "status": "success",
            "agent": {key: agent[key] for key in ("id", "company_id", "full_name")},
            "client_id": client["id"],
            "message": "Заметка добавлена!",
        })

    @app.get("/api/notes", dependencies=[Depends(require_viewer)])
    async def get_notes():
        return {"notes": list(notes)}

    @app.get("/", response_class=HTMLResponse, dependencies=[Depends(require_viewer)])
    @app.get("/notes", response_class=HTMLResponse, dependencies=[Depends(require_viewer)])
    async def view_notes():
        rows = "".join(
            "<tr>"
            + "".join(f"<td>{html.escape(str(value))}</td>" for value in (
                note["id"], note["created_at"], note["client_id"],
                note["agent_id"], note["type"], note["note"],
            ))
            + "</tr>" for note in reversed(notes)
        )
        return (
            '<!doctype html><html lang="ru"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>Mock CRM — заметки</title><style>'
            'body{font:16px system-ui,sans-serif;max-width:1100px;margin:3rem auto;padding:0 1rem}'
            'table{width:100%;border-collapse:collapse}td,th{padding:.7rem;border:1px solid #ddd;'
            'text-align:left;vertical-align:top}td:last-child{white-space:pre-wrap;overflow-wrap:anywhere}'
            'th{background:#f3f4f6}</style></head><body>'
            '<h1>Mock CRM · созданные заметки</h1>'
            '<p>Синтетическая тестовая среда. Заметки хранятся только в памяти контейнера.</p>'
            '<table><thead><tr><th>ID</th><th>Создана (UTC)</th><th>Клиент</th>'
            '<th>Агент</th><th>Тип</th><th>Заметка</th></tr></thead><tbody>'
            + rows + '</tbody></table></body></html>'
        )

    return app
