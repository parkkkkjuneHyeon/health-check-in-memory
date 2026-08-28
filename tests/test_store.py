import pytest

from app.schemas import AuthConfigInput, MonitorCreate, RecipientCreate
from app.store import MonitorStore


@pytest.mark.asyncio
async def test_monitor_response_excludes_login_payload_and_token():
    store = MonitorStore()
    monitor = await store.create_monitor(
        MonitorCreate(
            name="JWT API",
            url="https://api.example.internal/health",
            auth=AuthConfigInput(
                type="JWT_LOGIN",
                login_url="https://api.example.internal/login",
                login_payload={"username": "monitor", "password": "secret"},
                token_response_path="access_token",
            ),
        )
    )

    result = await store.get_monitor_response(monitor.id)
    dumped = result.model_dump()

    assert dumped["auth"]["login_url"] == "https://api.example.internal/login"
    assert "login_payload" not in dumped["auth"]
    assert "access_token" not in dumped["auth"]


@pytest.mark.asyncio
async def test_recipient_crud():
    store = MonitorStore()
    recipient = await store.create_recipient(
        RecipientCreate(name="운영", email="ops@example.internal")
    )

    assert (await store.get_enabled_recipient_emails()) == ["ops@example.internal"]
    await store.delete_recipient(recipient.id)
    assert await store.list_recipients() == []
