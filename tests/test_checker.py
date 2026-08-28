import httpx
import pytest

from app.checker import HealthChecker
from app.models import AuthConfig, Monitor


def monitor(**overrides):
    data = {
        "id": "monitor-1",
        "name": "Test API",
        "url": "https://api.example.internal/health",
        "method": "GET",
        "interval_seconds": 30,
        "timeout_seconds": 1,
        "expected_status_codes": {200},
        "max_attempts": 2,
        "retry_delay_seconds": 0,
    }
    data.update(overrides)
    return Monitor(**data)


@pytest.mark.asyncio
async def test_error_message_is_extracted_and_sensitive_value_is_masked():
    async def handler(request):
        return httpx.Response(503, json={"detail": "password=very-secret is invalid"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await HealthChecker(client).check(monitor(max_attempts=1))

    assert result.success is False
    assert result.status_code == 503
    assert result.server_error_message == "password=*** is invalid"


@pytest.mark.asyncio
async def test_jwt_login_is_used_for_health_check():
    received_auth = []

    async def handler(request):
        if request.url.path == "/login":
            return httpx.Response(200, json={"data": {"access_token": "not-a-jwt"}})
        received_auth.append(request.headers.get("authorization"))
        return httpx.Response(200)

    auth = AuthConfig(
        login_url="https://api.example.internal/login",
        login_method="POST",
        login_payload={"username": "monitor", "password": "secret"},
        token_response_path="data.access_token",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await HealthChecker(client).check(monitor(auth=auth, max_attempts=1))

    assert result.success is True
    assert received_auth == ["Bearer not-a-jwt"]


@pytest.mark.asyncio
async def test_failed_request_is_retried_before_down_is_confirmed():
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(503 if calls == 1 else 200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await HealthChecker(client).check(monitor())

    assert result.success is True
    assert result.attempt_count == 2
    assert calls == 2
