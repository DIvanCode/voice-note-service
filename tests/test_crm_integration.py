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


@pytest.mark.asyncio
async def test_save_and_view_requires_separate_password(app):
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://mock-crm") as client:
        payload = {"key": KEY, "note": "Тема: Встреча\n\nДоговорились о просмотре", "user_phone": AGENT, "client_phone": CLIENT}
        saved = await client.post("/client/add-note", json=payload)
        assert saved.status_code == 201
        assert saved.json()["client_id"] == 789
        assert saved.json()["agent"]["id"] == 123
        assert (await client.get("/api/notes")).status_code == 401
        assert (await client.get("/notes", auth=("viewer", "bad"))).status_code == 401
        notes = await client.get("/api/notes", auth=("viewer", VIEW))
        assert notes.status_code == 200
        assert notes.json()["notes"][0]["type"] == "public"
        assert "Договорились" in notes.json()["notes"][0]["note"]
        assert notes.headers["Cache-Control"] == "no-store"


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
        notes = await client.get("/api/notes", auth=("viewer", VIEW))
        assert notes.json()["notes"] == []


@pytest.mark.asyncio
async def test_dashboard_escapes_html(app):
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://mock-crm") as client:
        response = await client.post("/client/add-note", json={"key": KEY, "note": "<script>alert(1)</script>", "user_phone": AGENT, "client_phone": CLIENT})
        assert response.status_code == 201
        page = await client.get("/notes", auth=("viewer", VIEW))
        assert "&lt;script&gt;" in page.text
        assert "<script>" not in page.text


@pytest.mark.asyncio
async def test_bot_sends_contract_and_accepts_successful_500():
    calls = []
    def handler(request):
        calls.append(request)
        assert request.url.path == "/client/add-note"
        assert request.headers["content-type"] == "application/json"
        data = __import__("json").loads(request.content)
        assert data == {"key": KEY, "note": "Тема: Встреча\n\nТекст", "user_phone": AGENT, "client_phone": CLIENT}
        return httpx.Response(500, json={"status": "success", "agent": {"id": 123, "company_id": 456, "full_name": "Тестовый Агент"}, "client_id": 789, "message": "Заметка добавлена!"})
    service = CRMService("http://mock-crm:8000/client/add-note", KEY, transport=httpx.MockTransport(handler))
    await service.create_note(Note(note="Текст", phone="+" + CLIENT, topic="Встреча"), user_phone=AGENT)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_errors_are_safe_and_no_retries():
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(500, json={"status": "error", "error_code": "internal_server_error", "message": "secret private note"})
    service = CRMService("http://mock-crm:8000/client/add-note", KEY, transport=httpx.MockTransport(handler))
    with pytest.raises(CRMError) as exc_info:
        await service.create_note(Note(note="Текст", phone=CLIENT, topic="Встреча"), user_phone=AGENT)
    assert exc_info.value.code == "unknown_result"
    assert "secret" not in str(exc_info.value)
    assert "Проверьте CRM" in exc_info.value.user_message
    assert len(requests) == 1


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
    # This transport exercises the actual HTTP handlers without a network port.
    service = CRMService("http://mock-crm:8000/client/add-note", KEY, transport=ASGITransport(app=app))
    await service.create_note(Note(note="Обсудили цену", topic="Сделка", phone=CLIENT), user_phone=AGENT)
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://mock-crm") as client:
        response = await client.get("/api/notes", auth=("viewer", VIEW))
    assert len(response.json()["notes"]) == 1


@pytest.mark.asyncio
async def test_synthetic_extractor_identity_never_reaches_real_crm():
    requests = []
    service = CRMService(
        "https://your-crm.example/client/add-note",
        KEY,
        transport=httpx.MockTransport(lambda request: requests.append(request) or httpx.Response(201)),
    )
    with pytest.raises(CRMError) as exc:
        await service.create_note(
            Note(note="text", topic="Тест", phone="+" + CLIENT, full_name="Тестовый Клиент"),
            user_phone=AGENT,
        )
    assert exc.value.code == "test_data"
    assert requests == []


@pytest.mark.asyncio
async def test_transport_errors_are_uncertain_and_not_retried():
    calls = []
    def broken(request):
        calls.append(request)
        raise httpx.ReadTimeout("sensitive upstream exception")
    service = CRMService(
        "http://mock-crm:8000/client/add-note", KEY,
        transport=httpx.MockTransport(broken),
    )
    with pytest.raises(CRMError) as exc:
        await service.create_note(Note(note="text", topic="Тест", phone=CLIENT), user_phone=AGENT)
    assert exc.value.code == "unknown_result"
    assert "sensitive" not in str(exc.value)
    assert len(calls) == 1

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "client_phone,client_name",
    [
        ("79990000000", "Тестовый Клиент"),
        ("+7 (999) 000-00-00", "Иван Иванов"),  # only the name edited
        ("79990000000", None),
        ("+79990000000", "Другой клиент"),
    ],
)
async def test_placeholder_phone_never_reaches_real_crm_after_name_edit(client_phone, client_name):
    requests = []
    def handler(request):
        requests.append(request)
        raise AssertionError("Synthetic number must not be sent to production")

    service = CRMService(
        "https://your-crm.example/client/add-note",
        KEY,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(CRMError) as exc:
        await service.create_note(
            Note(note="Обсудили просмотр", topic="Встреча", phone=client_phone, full_name=client_name),
            user_phone=AGENT,
        )
    assert exc.value.code == "test_data"
    assert "телефон" in exc.value.user_message
    assert requests == []


@pytest.mark.asyncio
async def test_non_placeholder_phone_can_be_sent_to_real_crm():
    sent = []
    def handler(request):
        sent.append(__import__("json").loads(request.content))
        return httpx.Response(
            201,
            json={
                "status": "success",
                "agent": {"id": 123, "company_id": 456, "full_name": "Тестовый Агент"},
                "client_id": 790,
                "message": "Заметка добавлена!",
            },
        )

    service = CRMService(
        "https://your-crm.example/client/add-note",
        KEY,
        transport=httpx.MockTransport(handler),
    )
    await service.create_note(
        Note(note="Обсудили просмотр", topic="Встреча", full_name="Иван Иванов", phone="+79997654321"),
        user_phone=AGENT,
    )
    assert len(sent) == 1
    assert sent[0]["client_phone"] == "79997654321"
