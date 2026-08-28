import httpx
import pytest

from app.checker import HealthChecker
from app.notifier import EmailNotifier
from app.scheduler import MonitorScheduler
from app.schemas import MonitorCreate
from app.store import MonitorStore


@pytest.mark.asyncio
async def test_down_then_recovery_changes_state_and_notifies_once_per_event():
    responses = [503, 200, 200]

    async def handler(request):
        return httpx.Response(responses.pop(0), json={"detail": "temporary outage"})

    store = MonitorStore()
    created = await store.create_monitor(
        MonitorCreate(
            name="API",
            url="https://api.example.internal/health",
            max_attempts=1,
        )
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        scheduler = MonitorScheduler(store, HealthChecker(client), EmailNotifier())
        down = await scheduler.check_now(created.id)
        recovered = await scheduler.check_now(created.id)
        stable = await scheduler.check_now(created.id)

    assert down.status.value == "DOWN"
    assert down.last_server_error_message == "temporary outage"
    assert recovered.status.value == "UP"
    assert stable.status.value == "UP"
