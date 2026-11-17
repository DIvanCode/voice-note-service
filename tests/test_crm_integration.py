import json
import re

import httpx
import pytest
from httpx import ASGITransport

from bot.models.note import Note
from bot.services.crm_service import CRMError, CRMService, parse_agent_bindings
from mock_crm.app import create_app

KEY = "test-api-key-do-not-use-12345"
VIEW = "test-view-password-987654321"
AGENT = "79991234567"
CLIENT = "79990000000"


@pytest.fixture
def app():
    return create_app(api_key=KEY, view_password=VIEW)


def _note(lead=CLIENT, topic="Встреча", description="Текст"):
    return Note(lead=lead, topic=topic, description=description)


@pytest.mark.asyncio
async def test_save_and_view_requires_separate_password(app):
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://mock-crm") as client:
        payload = {"key": KEY, "note": "Тема: Встреча\n\nОписание: Договорились", "user_phone": AGENT, "client_phone": CLIENT}
        saved = await client.post("/client/add-note", json=payload)
        assert saved.status_code == 201
        assert saved.json()["client_id"] == 789
        assert saved.json()["agent"]["id"] == 123
        assert (await client.get("/api/notes")).status_code == 401
        assert (await client.get("/notes", auth=("viewer", "bad"))).status_code == 401
        notes = await client.get("/api/notes", auth=("viewer", VIEW))
        assert notes.status_code == 200
        assert notes.json()["notes"][0]["type"] == "public"
        assert notes.json()["notes"][0]["client_full_name"] == "Тестовый Клиент"
        assert notes.json()["notes"][0]["agent_full_name"] == "Тестовый Агент"
        assert "Договорились" in notes.json()["notes"][0]["note"]
        assert notes.headers["Cache-Control"] == "no-store"
        page = await client.get("/notes", auth=("viewer", VIEW))
        assert page.status_code == 200
        assert "<th>Тип</th>" not in page.text
        assert "<th>Клиент</th>" in page.text
        assert "<th>Агент</th>" in page.text
        assert "Тестовый Клиент" in page.text
        assert "Тестовый Агент" in page.text
        assert re.search(r"\\d{2}\\.\\d{2}\\.\\d{4}, \\d{2}:\\d{2} UTC", page.text)


@pytest.mark.asyncio
async def test_mock_rejects_and_does_not_store_invalid_requests(app):
    p = {"key": KEY, "note": "Привет", "user_phone": AGENT, "client_phone": CLIENT}
    cases = [
        ({**p, "key": ""}, 403, "no_key"),
        ({**p, "key": "wrong"}, 400, "bad_key"),
        ({**p, "note": ""}, 400, "empty_note"),
        ({**p, "client_phone": ""}, 400, "niether_phone_nor_address"),
        ({**p, "client_phone": "", "client_address": {"street_name": "Тест", "house_number": "1"}}, 501, "not_implemented"),
        ({**p, "user_phone": "79991110000"}, 404, "no_user_by_phone"),
        ({**p, "client_phone": "79990000001"}, 404, "no_client_by_phone"),
        ({**p, "client_phone": "79998887766"}, 409, "redundant_client_by_phone"),
    ]
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://mock-crm") as client:
        for body, code, error in cases:
            response = await client.post("/client/add-note", json=body)
            assert response.status_code == code
            assert response.json()["error_code"] == error
        response = await client.get("/api/notes", auth=("viewer", VIEW))
        assert response.json()["notes"] == []


@pytest.mark.asyncio
async def test_dashboard_escapes_html(app):
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://mock-crm") as client:
        r = await client.post("/client/add-note", json={"key": KEY, "note": "<script>alert(1)</script>", "user_phone": AGENT, "client_phone": CLIENT})
        assert r.status_code == 201
        page = await client.get("/notes", auth=("viewer", VIEW))
        assert "&lt;script&gt;" in page.text
        assert "<script>" not in page.text


@pytest.mark.asyncio
async def test_six_fields_sent_to_crm_and_successful_http_500_accepted():
    calls = []

    def handler(request):
        calls.append(request)
        assert request.url.path == "/client/add-note"
        payload = json.loads(request.content)
        assert payload == {
            "key": KEY,
            "note": "Лид: +79990000000\n\nТема: Встреча\n\nОписание: Текст\n\nСледующий шаг: Позвонить\n\nСрок: Завтра\n\nДополнительная информация: Договор",
            "user_phone": AGENT,
            "client_phone": CLIENT,
        }
        return httpx.Response(500, json={
            "status": "success",
            "agent": {"id": 123, "company_id": 456, "full_name": "Тестовый Агент"},
            "client_id": 789,
            "message": "Заметка добавлена!",
        })

    crm = CRMService("http://mock-crm:8000/client/add-note", KEY, transport=httpx.MockTransport(handler))
    await crm.create_note(Note(
        lead="+" + CLIENT, topic="Встреча", description="Текст",
        next_step="Позвонить", deadline="Завтра", additional_info="Договор",
    ), user_phone=AGENT)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_errors_are_safe_and_no_retries():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(500, json={"status": "error", "error_code": "internal_server_error", "message": "secret note"})

    crm = CRMService("http://mock-crm:8000/client/add-note", KEY, transport=httpx.MockTransport(handler))
    with pytest.raises(CRMError) as exc:
        await crm.create_note(_note(), user_phone=AGENT)
    assert exc.value.code == "unknown_result"
    assert "secret" not in str(exc.value)
    assert len(calls) == 1


def test_agent_bindings_and_https_policy():
    assert parse_agent_bindings('{"123456": "+7 (999) 123-45-67"}') == {123456: "79991234567"}
    for value in ['{"abc":"79991234567"}', '{"123":"bad"}', '[]', 'garbage']:
        with pytest.raises(ValueError):
            parse_agent_bindings(value)
    with pytest.raises(ValueError):
        CRMService("http://example.com/client/add-note", KEY)
    with pytest.raises(ValueError):
        CRMService("https://example.com/client/add-note?key=secret", KEY)


@pytest.mark.asyncio
async def test_http_client_to_mock_end_to_end(app):
    crm = CRMService("http://mock-crm:8000/client/add-note", KEY, transport=ASGITransport(app=app))
    await crm.create_note(Note(lead=CLIENT, topic="Сделка", description="Обсудили цену"), user_phone=AGENT)
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://mock-crm") as client:
        resp = await client.get("/api/notes", auth=("viewer", VIEW))
    assert len(resp.json()["notes"]) == 1
    assert "Лид: 79990000000" in resp.json()["notes"][0]["note"]
    assert "Тема: Сделка" in resp.json()["notes"][0]["note"]
    assert "Описание: Обсудили цену" in resp.json()["notes"][0]["note"]


@pytest.mark.asyncio
@pytest.mark.parametrize("lead", ["79990000000", "+7 (999) 000-00-00", "+79990000000"])
async def test_synthetic_phone_not_sent_to_production_even_if_fields_change(lead):
    calls = []
    crm = CRMService(
        "https://your-crm.example/client/add-note",
        KEY,
        transport=httpx.MockTransport(lambda request: calls.append(request) or httpx.Response(201)),
    )
    with pytest.raises(CRMError) as exc:
        await crm.create_note(Note(lead=lead, topic="Новая тема", description="Исправлено"), user_phone=AGENT)
    assert exc.value.code == "test_data"
    assert calls == []


@pytest.mark.asyncio
async def test_address_lead_is_not_sent_or_guessed():
    calls = []
    crm = CRMService(
        "http://mock-crm:8000/client/add-note",
        KEY,
        transport=httpx.MockTransport(lambda request: calls.append(request) or httpx.Response(201)),
    )
    with pytest.raises(CRMError) as exc:
        await crm.create_note(_note(lead="ул. Лесная, дом 10"), user_phone=AGENT)
    assert exc.value.code == "not_implemented"
    assert calls == []


@pytest.mark.asyncio
async def test_non_placeholder_phone_sends_to_real_crm():
    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        return httpx.Response(201, json={
            "status": "success",
            "agent": {"id": 123, "company_id": 456, "full_name": "Тестовый Агент"},
            "client_id": 790,
            "message": "Заметка добавлена!",
        })

    crm = CRMService("https://your-crm.example/client/add-note", KEY, transport=httpx.MockTransport(handler))
    await crm.create_note(_note(lead="+79997654321"), user_phone=AGENT)
    assert len(sent) == 1
    assert sent[0]["client_phone"] == "79997654321"


@pytest.mark.asyncio
async def test_transport_errors_are_uncertain_and_not_retried():
    calls = []

    def broken(request):
        calls.append(request)
        raise httpx.ReadTimeout("sensitive upstream exception")

    crm = CRMService("http://mock-crm:8000/client/add-note", KEY, transport=httpx.MockTransport(broken))
    with pytest.raises(CRMError) as exc:
        await crm.create_note(_note(), user_phone=AGENT)
    assert exc.value.code == "unknown_result"
    assert "sensitive" not in str(exc.value)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_notes_ui_escapes_client_and_agent_names_from_fixtures():
    fixtures = {
        "agents": [
            {"id": 123, "company_id": 456, "full_name": "<b>Агент</b>", "phone": AGENT, "active": True}
        ],
        "clients": [
            {"id": 789, "company_id": 456, "full_name": "<script>alert(1)</script>", "phone": CLIENT}
        ],
    }
    app = create_app(api_key=KEY, view_password=VIEW, fixtures=fixtures)
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://mock-crm") as client:
        saved = await client.post("/client/add-note", json={
            "key": KEY, "note": "Лид: " + CLIENT + "\\n\\nТема: Тест",
            "user_phone": AGENT, "client_phone": CLIENT,
        })
        assert saved.status_code == 201
        page = await client.get("/notes", auth=("viewer", VIEW))
        assert "&lt;b&gt;Агент&lt;/b&gt;" in page.text
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page.text
        assert "<script>alert(1)</script>" not in page.text
        assert "<b>Агент</b>" not in page.text


@pytest.mark.asyncio
async def test_only_filled_agent_fields_are_included_in_crm_note(app):
    crm = CRMService("http://mock-crm:8000/client/add-note", KEY, transport=ASGITransport(app=app))
    await crm.create_note(
        Note(lead="+" + CLIENT, topic="Встреча", description="  Показ квартиры  ", next_step=None,
             deadline="  ", additional_info="Нужна парковка"),
        user_phone=AGENT,
    )
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://mock-crm") as client:
        data = (await client.get("/api/notes", auth=("viewer", VIEW))).json()
        note_text = data["notes"][0]["note"]
        assert note_text == ("Лид: +" + CLIENT + "\\n\\nТема: Встреча"
                             + "\\n\\nОписание: Показ квартиры"
                             + "\\n\\nДополнительная информация: Нужна парковка")
        page = await client.get("/notes", auth=("viewer", VIEW))
        assert "Дополнительная информация: Нужна парковка" in page.text
        assert "Следующий шаг:" not in page.text
        assert "Срок:" not in page.text
