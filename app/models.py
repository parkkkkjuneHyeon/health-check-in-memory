from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class MonitorStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    UP = "UP"
    DOWN = "DOWN"


class AuthType(str, Enum):
    JWT_LOGIN = "JWT_LOGIN"


@dataclass
class AuthConfig:
    login_url: str
    login_method: str
    login_payload: Dict[str, Any]
    token_response_path: str
    token_header_name: str = "Authorization"
    token_prefix: str = "Bearer"
    access_token: Optional[str] = None
    token_expires_at: Optional[datetime] = None
    auth_last_error: Optional[str] = None


@dataclass
class Monitor:
    id: str
    name: str
    url: str
    method: str
    interval_seconds: int
    timeout_seconds: float
    expected_status_codes: Set[int]
    max_attempts: int
    retry_delay_seconds: int
    auth: Optional[AuthConfig] = None
    enabled: bool = True
    status: MonitorStatus = MonitorStatus.UNKNOWN
    last_checked_at: Optional[datetime] = None
    last_status_code: Optional[int] = None
    last_response_time_ms: Optional[float] = None
    last_error: Optional[str] = None
    last_server_error_message: Optional[str] = None
    last_attempt_count: Optional[int] = None
    last_notification_error: Optional[str] = None
    next_check_at: Optional[datetime] = None
    is_checking: bool = False
    alert_sent_for_current_outage: bool = False


@dataclass
class EmailConfig:
    smtp_host: str
    smtp_port: int
    username: Optional[str]
    password: Optional[str]
    use_starttls: bool
    from_address: str
    configured: bool = True


@dataclass
class NotificationRecipient:
    id: str
    name: Optional[str]
    email: str
    enabled: bool
    created_at: datetime
    updated_at: datetime


class NotificationKind(str, Enum):
    DOWN = "DOWN"
    RECOVERED = "RECOVERED"


@dataclass
class NotificationEvent:
    kind: NotificationKind
    monitor_id: str
    monitor_name: str
    url: str
    checked_at: datetime
    status_code: Optional[int]
    response_time_ms: Optional[float]
    error: Optional[str]
    server_error_message: Optional[str]


@dataclass
class CheckResult:
    success: bool
    status_code: Optional[int]
    response_time_ms: Optional[float]
    error: Optional[str]
    server_error_message: Optional[str]
    attempt_count: int

