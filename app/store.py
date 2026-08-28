import asyncio
import copy
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from .models import (
    AuthConfig,
    CheckResult,
    EmailConfig,
    Monitor,
    MonitorStatus,
    NotificationEvent,
    NotificationKind,
    NotificationRecipient,
)
from .schemas import (
    AuthConfigInput,
    AuthConfigPublic,
    EmailConfigInput,
    EmailConfigResponse,
    MonitorCreate,
    MonitorResponse,
    MonitorUpdate,
    RecipientCreate,
    RecipientResponse,
    RecipientUpdate,
)
from .utils import display_url, utc_now


class NotFoundError(Exception):
    def __init__(self, resource: str):
        self.resource = resource
        super().__init__(resource)


class AlreadyCheckingError(Exception):
    pass


class MonitorStore:
    """Single-process state store. Never hold its lock during network I/O."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._monitors: Dict[str, Monitor] = {}
        self._recipients: Dict[str, NotificationRecipient] = {}
        self._email_config: Optional[EmailConfig] = None
        self.scheduler_running = False

    @staticmethod
    def _new_auth(data: Optional[AuthConfigInput]) -> Optional[AuthConfig]:
        if data is None:
            return None
        return AuthConfig(
            login_url=str(data.login_url),
            login_method=data.login_method,
            login_payload=copy.deepcopy(data.login_payload),
            token_response_path=data.token_response_path,
            token_header_name=data.token_header_name,
            token_prefix=data.token_prefix,
        )

    @staticmethod
    def monitor_response(monitor: Monitor) -> MonitorResponse:
        auth = None
        if monitor.auth is not None:
            auth = AuthConfigPublic(
                type="JWT_LOGIN",
                login_url=monitor.auth.login_url,
                login_method=monitor.auth.login_method,
                token_response_path=monitor.auth.token_response_path,
                token_header_name=monitor.auth.token_header_name,
                token_prefix=monitor.auth.token_prefix,
                token_expires_at=monitor.auth.token_expires_at,
                auth_last_error=monitor.auth.auth_last_error,
            )
        return MonitorResponse(
            id=monitor.id,
            name=monitor.name,
            url=monitor.url,
            method=monitor.method,
            interval_seconds=monitor.interval_seconds,
            timeout_seconds=monitor.timeout_seconds,
            expected_status_codes=sorted(monitor.expected_status_codes),
            max_attempts=monitor.max_attempts,
            retry_delay_seconds=monitor.retry_delay_seconds,
            auth=auth,
            enabled=monitor.enabled,
            status=monitor.status,
            last_checked_at=monitor.last_checked_at,
            last_status_code=monitor.last_status_code,
            last_response_time_ms=monitor.last_response_time_ms,
            last_error=monitor.last_error,
            last_server_error_message=monitor.last_server_error_message,
            last_attempt_count=monitor.last_attempt_count,
            last_notification_error=monitor.last_notification_error,
            next_check_at=monitor.next_check_at,
            is_checking=monitor.is_checking,
        )

    @staticmethod
    def recipient_response(recipient: NotificationRecipient) -> RecipientResponse:
        return RecipientResponse(
            id=recipient.id,
            name=recipient.name,
            email=recipient.email,
            enabled=recipient.enabled,
            created_at=recipient.created_at,
            updated_at=recipient.updated_at,
        )

    async def create_monitor(self, data: MonitorCreate) -> MonitorResponse:
        now = utc_now()
        monitor = Monitor(
            id=str(uuid.uuid4()),
            name=data.name,
            url=str(data.url),
            method=data.method,
            interval_seconds=data.interval_seconds,
            timeout_seconds=data.timeout_seconds,
            expected_status_codes=set(data.expected_status_codes),
            max_attempts=data.max_attempts,
            retry_delay_seconds=data.retry_delay_seconds,
            auth=self._new_auth(data.auth),
            next_check_at=now,
        )
        async with self._lock:
            self._monitors[monitor.id] = monitor
            return self.monitor_response(monitor)

    async def list_monitors(self) -> List[MonitorResponse]:
        async with self._lock:
            return [self.monitor_response(monitor) for monitor in self._monitors.values()]

    async def get_monitor_response(self, monitor_id: str) -> MonitorResponse:
        async with self._lock:
            monitor = self._monitors.get(monitor_id)
            if monitor is None:
                raise NotFoundError("monitor")
            return self.monitor_response(monitor)

    async def update_monitor(self, monitor_id: str, data: MonitorUpdate) -> MonitorResponse:
        fields_set = data.model_fields_set
        async with self._lock:
            monitor = self._monitors.get(monitor_id)
            if monitor is None:
                raise NotFoundError("monitor")
            for field_name in (
                "name", "method", "interval_seconds", "timeout_seconds", "max_attempts",
                "retry_delay_seconds", "enabled",
            ):
                if field_name in fields_set:
                    setattr(monitor, field_name, getattr(data, field_name))
            if "url" in fields_set:
                monitor.url = str(data.url)
            if "expected_status_codes" in fields_set:
                monitor.expected_status_codes = set(data.expected_status_codes or [])
            if "auth" in fields_set:
                monitor.auth = self._new_auth(data.auth)
            if not monitor.enabled:
                monitor.is_checking = False
            monitor.next_check_at = utc_now()
            return self.monitor_response(monitor)

    async def delete_monitor(self, monitor_id: str) -> None:
        async with self._lock:
            if monitor_id not in self._monitors:
                raise NotFoundError("monitor")
            del self._monitors[monitor_id]

    async def claim_due_monitors(self) -> List[Monitor]:
        now = utc_now()
        claimed: List[Monitor] = []
        async with self._lock:
            for monitor in self._monitors.values():
                if monitor.enabled and not monitor.is_checking and monitor.next_check_at and monitor.next_check_at <= now:
                    monitor.is_checking = True
                    claimed.append(monitor)
        return claimed

    async def claim_monitor(self, monitor_id: str) -> Monitor:
        async with self._lock:
            monitor = self._monitors.get(monitor_id)
            if monitor is None:
                raise NotFoundError("monitor")
            if monitor.is_checking:
                raise AlreadyCheckingError()
            monitor.is_checking = True
            return monitor

    async def finish_check(self, monitor_id: str, result: CheckResult) -> Optional[NotificationEvent]:
        now = utc_now()
        async with self._lock:
            monitor = self._monitors.get(monitor_id)
            if monitor is None:
                return None
            previous_status = monitor.status
            monitor.is_checking = False
            monitor.last_checked_at = now
            monitor.last_status_code = result.status_code
            monitor.last_response_time_ms = result.response_time_ms
            monitor.last_error = result.error
            monitor.last_server_error_message = result.server_error_message
            monitor.last_attempt_count = result.attempt_count
            monitor.next_check_at = now + timedelta(seconds=monitor.interval_seconds)
            monitor.status = MonitorStatus.UP if result.success else MonitorStatus.DOWN

            event: Optional[NotificationEvent] = None
            if not result.success and previous_status != MonitorStatus.DOWN:
                monitor.alert_sent_for_current_outage = True
                event = self._notification_event(monitor, NotificationKind.DOWN)
            elif result.success and previous_status == MonitorStatus.DOWN:
                monitor.alert_sent_for_current_outage = False
                event = self._notification_event(monitor, NotificationKind.RECOVERED)
            return event

    @staticmethod
    def _notification_event(monitor: Monitor, kind: NotificationKind) -> NotificationEvent:
        return NotificationEvent(
            kind=kind,
            monitor_id=monitor.id,
            monitor_name=monitor.name,
            url=display_url(monitor.url),
            checked_at=monitor.last_checked_at or utc_now(),
            status_code=monitor.last_status_code,
            response_time_ms=monitor.last_response_time_ms,
            error=monitor.last_error,
            server_error_message=monitor.last_server_error_message,
        )

    async def record_notification_error(self, monitor_id: str, error: Optional[str]) -> None:
        async with self._lock:
            monitor = self._monitors.get(monitor_id)
            if monitor is not None:
                monitor.last_notification_error = error

    async def create_recipient(self, data: RecipientCreate) -> RecipientResponse:
        now = utc_now()
        recipient = NotificationRecipient(
            id=str(uuid.uuid4()),
            name=data.name,
            email=str(data.email),
            enabled=data.enabled,
            created_at=now,
            updated_at=now,
        )
        async with self._lock:
            self._recipients[recipient.id] = recipient
            return self.recipient_response(recipient)

    async def list_recipients(self) -> List[RecipientResponse]:
        async with self._lock:
            return [self.recipient_response(recipient) for recipient in self._recipients.values()]

    async def get_recipient_response(self, recipient_id: str) -> RecipientResponse:
        async with self._lock:
            recipient = self._recipients.get(recipient_id)
            if recipient is None:
                raise NotFoundError("recipient")
            return self.recipient_response(recipient)

    async def update_recipient(self, recipient_id: str, data: RecipientUpdate) -> RecipientResponse:
        fields_set = data.model_fields_set
        async with self._lock:
            recipient = self._recipients.get(recipient_id)
            if recipient is None:
                raise NotFoundError("recipient")
            for field_name in ("name", "email", "enabled"):
                if field_name in fields_set:
                    value = getattr(data, field_name)
                    setattr(recipient, field_name, str(value) if field_name == "email" and value is not None else value)
            recipient.updated_at = utc_now()
            return self.recipient_response(recipient)

    async def delete_recipient(self, recipient_id: str) -> None:
        async with self._lock:
            if recipient_id not in self._recipients:
                raise NotFoundError("recipient")
            del self._recipients[recipient_id]

    async def get_enabled_recipient_emails(self) -> List[str]:
        async with self._lock:
            return [recipient.email for recipient in self._recipients.values() if recipient.enabled]

    async def get_recipient_email(self, recipient_id: str) -> str:
        async with self._lock:
            recipient = self._recipients.get(recipient_id)
            if recipient is None:
                raise NotFoundError("recipient")
            return recipient.email

    async def set_email_config(self, data: EmailConfigInput) -> EmailConfigResponse:
        config = EmailConfig(
            smtp_host=data.smtp_host,
            smtp_port=data.smtp_port,
            username=data.username,
            password=data.password,
            use_starttls=data.use_starttls,
            from_address=str(data.from_address),
        )
        async with self._lock:
            self._email_config = config
            return self._email_config_response(config)

    async def get_email_config_response(self) -> EmailConfigResponse:
        async with self._lock:
            if self._email_config is None:
                raise NotFoundError("email_config")
            return self._email_config_response(self._email_config)

    async def get_email_config(self) -> Optional[EmailConfig]:
        async with self._lock:
            return copy.deepcopy(self._email_config)

    @staticmethod
    def _email_config_response(config: EmailConfig) -> EmailConfigResponse:
        return EmailConfigResponse(
            smtp_host=config.smtp_host,
            smtp_port=config.smtp_port,
            username=config.username,
            use_starttls=config.use_starttls,
            from_address=config.from_address,
            configured=config.configured,
            password_configured=bool(config.password),
        )

    async def summary(self) -> Tuple[int, int, int, int, bool]:
        async with self._lock:
            statuses = [monitor.status for monitor in self._monitors.values()]
            up = sum(status == MonitorStatus.UP for status in statuses)
            down = sum(status == MonitorStatus.DOWN for status in statuses)
            unknown = sum(status == MonitorStatus.UNKNOWN for status in statuses)
            return up, down, unknown, len(statuses), self.scheduler_running
