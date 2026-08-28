from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, field_validator

from .models import MonitorStatus


class AuthConfigInput(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {
        "type": "JWT_LOGIN",
        "login_url": "https://auth.example.internal/login",
        "login_method": "POST",
        "login_payload": {"username": "health-check-user", "password": "example-password"},
        "token_response_path": "data.access_token",
        "token_header_name": "Authorization",
        "token_prefix": "Bearer",
    }})

    type: Literal["JWT_LOGIN"] = Field(description="JWT 로그인 인증 방식")
    login_url: HttpUrl = Field(description="JWT를 발급하는 로그인 API URL")
    login_method: Literal["POST"] = Field(default="POST", description="로그인 API HTTP 메서드")
    login_payload: Dict[str, Any] = Field(
        description="로그인 API로 전송할 JSON 본문. 민감한 값은 조회 응답에서 제외됩니다.",
        json_schema_extra={"writeOnly": True},
    )
    token_response_path: str = Field(
        min_length=1,
        description="로그인 응답 JSON에서 토큰을 찾는 경로. 점 표기법 지원: data.access_token",
    )
    token_header_name: str = Field(default="Authorization", min_length=1, description="헬스 체크에 넣을 토큰 헤더 이름")
    token_prefix: str = Field(default="Bearer", description="토큰 앞에 붙일 접두어")


class AuthConfigPublic(BaseModel):
    type: Literal["JWT_LOGIN"] = Field(description="사용 중인 인증 방식")
    login_url: str = Field(description="JWT 로그인 API URL")
    login_method: str = Field(description="로그인 API HTTP 메서드")
    token_response_path: str = Field(description="로그인 응답에서 JWT를 읽는 JSON 경로")
    token_header_name: str = Field(description="JWT를 넣는 헬스 체크 요청 헤더 이름")
    token_prefix: str = Field(description="JWT 앞에 붙이는 헤더 값 접두어")
    token_expires_at: Optional[datetime] = Field(default=None, description="JWT exp에서 읽은 만료 시각. exp가 없으면 null")
    auth_last_error: Optional[str] = Field(default=None, description="최근 JWT 로그인 또는 토큰 추출 실패 사유")


class MonitorCreate(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {
        "name": "주문 API",
        "url": "https://api.example.internal/health",
        "method": "GET",
        "interval_seconds": 30,
        "timeout_seconds": 5,
        "expected_status_codes": [200],
        "max_attempts": 3,
        "retry_delay_seconds": 5,
        "auth": None,
    }})

    name: str = Field(min_length=1, max_length=100, description="모니터에서 표시할 서버 이름")
    url: HttpUrl = Field(description="점검할 HTTP 또는 HTTPS URL")
    method: Literal["GET", "HEAD"] = Field(default="GET", description="헬스 체크 요청 메서드")
    interval_seconds: int = Field(default=30, ge=5, le=86400, description="점검 완료 후 다음 점검까지의 초 단위 간격")
    timeout_seconds: float = Field(default=5.0, gt=0, le=120, description="요청 한 번의 최대 대기 시간(초)")
    expected_status_codes: List[int] = Field(default_factory=lambda: list(range(200, 400)), min_length=1, description="정상으로 처리할 HTTP 상태 코드 목록")
    max_attempts: int = Field(default=3, ge=1, le=5, description="최초 요청을 포함한 최대 점검 시도 횟수")
    retry_delay_seconds: int = Field(default=5, ge=1, le=300, description="실패한 점검 시도 사이의 대기 시간(초)")
    auth: Optional[AuthConfigInput] = Field(default=None, description="JWT 로그인이 필요한 대상의 인증 설정. 인증이 없으면 null")

    @field_validator("expected_status_codes")
    @classmethod
    def validate_status_codes(cls, value: List[int]) -> List[int]:
        if any(code < 100 or code > 599 for code in value):
            raise ValueError("HTTP 상태 코드는 100~599 범위여야 합니다.")
        return sorted(set(value))


class MonitorUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100, description="변경할 모니터 표시 이름")
    url: Optional[HttpUrl] = Field(default=None, description="변경할 헬스 체크 URL")
    method: Optional[Literal["GET", "HEAD"]] = Field(default=None, description="변경할 헬스 체크 HTTP 메서드")
    interval_seconds: Optional[int] = Field(default=None, ge=5, le=86400, description="점검 완료 후 다음 점검까지의 초 단위 간격")
    timeout_seconds: Optional[float] = Field(default=None, gt=0, le=120, description="요청 1회의 최대 대기 시간(초)")
    expected_status_codes: Optional[List[int]] = Field(default=None, min_length=1, description="정상으로 취급할 HTTP 상태 코드 목록")
    max_attempts: Optional[int] = Field(default=None, ge=1, le=5, description="최초 요청을 포함한 최대 시도 횟수")
    retry_delay_seconds: Optional[int] = Field(default=None, ge=1, le=300, description="재시도 사이 대기 시간(초)")
    enabled: Optional[bool] = Field(default=None, description="false면 스케줄러의 정기 점검을 중지")
    auth: Optional[AuthConfigInput] = Field(default=None, description="인증 설정. null을 명시하면 인증을 제거합니다.")

    @field_validator("expected_status_codes")
    @classmethod
    def validate_optional_status_codes(cls, value: Optional[List[int]]) -> Optional[List[int]]:
        if value is not None and any(code < 100 or code > 599 for code in value):
            raise ValueError("HTTP 상태 코드는 100~599 범위여야 합니다.")
        return sorted(set(value)) if value else value


class MonitorResponse(BaseModel):
    id: str = Field(description="서버가 생성한 모니터 UUID")
    name: str = Field(description="모니터 표시 이름")
    url: str = Field(description="원본 헬스 체크 URL. 이메일·로그에는 민감 query를 제외한 URL만 사용")
    method: str = Field(description="헬스 체크 HTTP 메서드")
    interval_seconds: int = Field(description="점검 완료 후 다음 점검까지의 초 단위 간격")
    timeout_seconds: float = Field(description="요청 1회의 최대 대기 시간(초)")
    expected_status_codes: List[int] = Field(description="정상으로 처리할 HTTP 상태 코드 목록")
    max_attempts: int = Field(description="최초 요청을 포함한 최대 시도 횟수")
    retry_delay_seconds: int = Field(description="실패한 시도 사이 대기 시간(초)")
    auth: Optional[AuthConfigPublic] = Field(default=None, description="민감값을 제외한 JWT 인증 설정")
    enabled: bool = Field(description="정기 점검 활성 여부")
    status: MonitorStatus = Field(description="UNKNOWN(미점검), UP(정상), DOWN(장애) 중 현재 상태")
    last_checked_at: Optional[datetime] = Field(default=None, description="최근 점검이 끝난 UTC 시각")
    last_status_code: Optional[int] = Field(default=None, description="최근 HTTP 응답 상태 코드. 연결 실패면 null")
    last_response_time_ms: Optional[float] = Field(default=None, description="최근 HTTP 응답 시간(ms). 응답이 없으면 null")
    last_error: Optional[str] = Field(default=None, description="클라이언트 또는 상태 코드 기준 오류 사유")
    last_server_error_message: Optional[str] = Field(default=None, description="오류 HTTP 응답 본문에서 추출·마스킹한 서버 메시지")
    last_attempt_count: Optional[int] = Field(default=None, description="최근 점검에서 실제 실행한 요청 수")
    last_notification_error: Optional[str] = Field(default=None, description="최근 이메일 발송 실패 사유. SMTP 실패는 대상 상태를 바꾸지 않음")
    next_check_at: Optional[datetime] = Field(default=None, description="다음 정기 점검 예정 UTC 시각")
    is_checking: bool = Field(description="현재 이 모니터의 점검 작업 진행 여부")


class RecipientCreate(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {"name": "운영 담당자", "email": "ops@example.internal", "enabled": True}})
    name: Optional[str] = Field(default=None, max_length=100, description="수신자 식별용 이름")
    email: EmailStr = Field(description="장애와 복구 이메일을 받을 주소")
    enabled: bool = Field(default=True, description="false면 알림 대상에서 제외")


class RecipientUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=100, description="변경할 수신자 표시 이름")
    email: Optional[EmailStr] = Field(default=None, description="변경할 수신 이메일 주소")
    enabled: Optional[bool] = Field(default=None, description="false면 장애·복구 알림에서 제외")


class RecipientResponse(BaseModel):
    id: str = Field(description="서버가 생성한 수신자 UUID")
    name: Optional[str] = Field(description="수신자 표시 이름")
    email: EmailStr = Field(description="이메일 수신 주소")
    enabled: bool = Field(description="알림 발송 대상 포함 여부")
    created_at: datetime = Field(description="등록 UTC 시각")
    updated_at: datetime = Field(description="최근 수정 UTC 시각")


class EmailConfigInput(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {
        "smtp_host": "smtp.example.internal",
        "smtp_port": 587,
        "username": "monitor@example.internal",
        "password": "example-password",
        "use_starttls": True,
        "from_address": "monitor@example.internal",
    }})
    smtp_host: str = Field(min_length=1, description="SMTP 서버 호스트")
    smtp_port: int = Field(ge=1, le=65535, description="SMTP 서버 포트")
    username: Optional[str] = Field(default=None, description="SMTP 사용자명")
    password: Optional[str] = Field(default=None, json_schema_extra={"writeOnly": True}, description="SMTP 비밀번호. 조회 응답에는 포함되지 않습니다.")
    use_starttls: bool = Field(default=True, description="STARTTLS 사용 여부")
    from_address: EmailStr = Field(description="발신자 이메일 주소")


class EmailConfigResponse(BaseModel):
    smtp_host: str = Field(description="SMTP 서버 호스트")
    smtp_port: int = Field(description="SMTP 서버 포트")
    username: Optional[str] = Field(description="SMTP 사용자명")
    use_starttls: bool = Field(description="STARTTLS 사용 여부")
    from_address: EmailStr = Field(description="SMTP 발신자 주소")
    configured: bool = Field(description="SMTP 설정이 메모리에 존재하는지")
    password_configured: bool = Field(description="비밀번호가 설정되었는지 여부. 비밀번호 원문은 반환하지 않음")


class StatusSummary(BaseModel):
    up: int = Field(description="UP 상태 모니터 수")
    down: int = Field(description="DOWN 상태 모니터 수")
    unknown: int = Field(description="아직 점검되지 않은 모니터 수")
    total: int = Field(description="전체 등록 모니터 수")
    scheduler_running: bool = Field(description="백그라운드 스케줄러 실행 여부")


class HealthResponse(BaseModel):
    status: Literal["ok"]


class MessageResponse(BaseModel):
    message: str


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    detail: ErrorDetail
