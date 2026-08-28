from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.models import EmailConfig, NotificationEvent, NotificationKind
from app.notifier import EmailNotifier


@pytest.mark.asyncio
async def test_test_email_sends_to_all_requested_recipients_without_exposing_password():
    config = EmailConfig(
        smtp_host="smtp.example.internal",
        smtp_port=587,
        username="monitor",
        password="secret",
        use_starttls=True,
        from_address="monitor@example.internal",
    )
    with patch.object(EmailNotifier, "_send") as send:
        error = await EmailNotifier().send_test(config, ["ops@example.internal"])

    assert error is None
    args = send.call_args.args
    assert args[1] == ["ops@example.internal"]
    assert "secret" not in args[2].as_string()


@pytest.mark.asyncio
async def test_notification_uses_safe_url_without_query_string():
    config = EmailConfig("smtp.example.internal", 587, None, None, True, "monitor@example.internal")
    event = NotificationEvent(
        kind=NotificationKind.DOWN,
        monitor_id="monitor-1",
        monitor_name="API",
        url="https://api.example.internal/health",
        checked_at=datetime.now(timezone.utc),
        status_code=503,
        response_time_ms=10.0,
        error="password=secret",
        server_error_message=None,
    )
    with patch.object(EmailNotifier, "_send") as send:
        error = await EmailNotifier().send_event(config, ["ops@example.internal"], event)

    assert error is None
    assert "password=***" in send.call_args.args[2].get_content()
