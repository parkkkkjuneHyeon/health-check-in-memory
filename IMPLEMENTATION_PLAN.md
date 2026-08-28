# 인메모리 서버 헬스 체크 및 이메일 알림 서버 구현 기획서

## 1. 목표

FastAPI로 실행되는 단일 프로세스 서버를 만든다. 사용자가 등록한 HTTP 서버를 주기적으로 점검하고, 장애 또는 복구 상태가 발생했을 때 이메일을 전송한다.

초기 버전은 데이터베이스, 파일 저장소, 환경 변수에 의존하지 않는다. 모니터 대상, 점검 결과, SMTP 설정, 이메일 수신자 목록은 모두 서버 프로세스의 메모리에만 보관한다.

## 2. 범위

### 포함

- HTTP/HTTPS URL의 비동기 상태 점검
- 대상별 점검 주기, 타임아웃, 정상으로 간주할 HTTP 상태 코드 설정
- 로그인 후 JWT가 필요한 대상의 인증 및 헬스 체크
- 인메모리 모니터 대상 등록, 조회, 수정, 삭제
- 인메모리 이메일 수신자 등록, 조회, 수정, 삭제
- 장애 전환 시 장애 이메일 1회 발송
- 장애 상태에서 정상으로 복구될 때 복구 이메일 1회 발송
- 단건 즉시 점검 API
- 모니터링 서버 자신의 상태를 반환하는 API

### 제외

- DB, Redis, 파일 기반 영속성
- 서버 재시작 후 설정과 이력 복원
- 이 모니터링 서버 자체의 로그인/권한 관리, 다중 사용자 테넌시
- TCP 포트, CPU/메모리, DB 연결 등 HTTP 이외의 점검
- 이메일 외 Slack, Discord 등의 알림 채널
- 장기 이력 및 통계 대시보드
- 다중 컨테이너 간 인메모리 상태 동기화
- 이메일 발송 실패의 자동 재시도

## 3. 핵심 동작 원칙

1. 서버가 재시작되면 모든 등록 대상, 이메일 수신자, SMTP 설정은 초기화된다.
2. `2xx`와 `3xx` 응답은 기본적으로 정상으로 간주한다. 등록 시 정상 상태 코드 목록을 별도로 지정할 수 있다.
3. `5xx`, 요청 타임아웃, DNS/연결/TLS 오류는 장애로 간주한다.
4. `4xx`는 기본 정책상 장애로 처리한다. 정상 상태 코드 목록에 포함하면 정상 처리할 수 있다.
5. 처음 장애가 감지되는 순간에만 장애 이메일을 보낸다. 동일 장애가 지속되는 동안 매 점검마다 이메일을 보내지 않는다.
6. 장애 상태에서 정상으로 바뀌면 복구 이메일을 한 번 보낸다.
7. 최초 요청이 실패하면 5초 후 재시도한다. 최대 시도 횟수 안에서 한 번이라도 성공하면 정상으로 처리한다.
8. 한 모니터가 점검 중일 때는 해당 모니터의 중복 점검을 시작하지 않는다.
9. JWT 인증 대상은 헬스 체크 전에 유효한 토큰을 확보하고, `401` 또는 `403` 응답 시 토큰을 한 번 갱신한 후 같은 요청을 다시 시도한다.
10. 초기 버전은 private subnet 안에서만 실행하며, 관리 API의 별도 인증은 구현하지 않는다.

## 4. 구조

```text
FastAPI
  ├── MonitorStore                 # 메모리 내 모니터, 수신자, 이메일 설정 보관
  ├── Async Scheduler              # 다음 점검 시각이 지난 대상 탐색
  ├── HealthChecker (httpx)        # HTTP 요청 및 결과 판정
  ├── AlertService (SMTP)          # 장애/복구 이메일 발송
  └── API Router                   # 모니터 및 이메일 설정 관리 API
```

FastAPI의 `lifespan`에서 스케줄러 태스크를 시작하고, 종료 시 취소한다. 별도 큐나 작업 서버 없이 하나의 `asyncio` 백그라운드 태스크가 스토어를 순회한다.

## 5. Docker 실행

애플리케이션은 Docker 컨테이너 한 개로 실행한다. 데이터베이스나 볼륨은 사용하지 않는다.

```text
호스트 포트 8000 ──> Docker 컨테이너 ──> FastAPI/Uvicorn (포트 8000)
```

- `Dockerfile`은 Python 슬림 이미지에 의존성을 설치하고 애플리케이션을 실행한다.
- `.dockerignore`에는 가상환경, 캐시, 테스트 산출물, Git 메타데이터를 제외한다.
- `docker-compose.yml`은 `8000:8000` 포트를 노출하고 `docker compose up --build`로 실행할 수 있게 한다.
- Uvicorn은 `--workers 1`로 실행한다. 워커가 둘 이상이면 워커마다 별도의 메모리 스토어와 스케줄러가 생겨 중복 점검·중복 이메일이 발생한다.
- 컨테이너 재시작 또는 재생성 시 모니터, 수신자, SMTP 설정, JWT는 모두 사라진다. 이는 초기 버전의 의도된 동작이다.
- SMTP 연결이 필요하므로 컨테이너가 외부 SMTP 서버로 나가는 네트워크 연결을 허용해야 한다.
- SMTP 비밀번호나 JWT를 이미지와 `docker-compose.yml`에 포함하지 않는다. 서버 실행 후 관리 API를 통해 메모리에만 설정한다.
- 컨테이너는 public subnet에 배치하지 않고 public IP를 할당하지 않는다. 보안 그룹/방화벽에서도 필요한 private network의 접근만 허용한다.

## 6. 인메모리 모델

내부 저장은 목록 대신 ID를 키로 하는 딕셔너리로 관리한다. 모니터는 `dict[str, Monitor]`, 이메일 수신자는 `dict[str, NotificationRecipient]` 형태이며, API에서는 이를 배열로 반환한다. ID로 조회·수정·삭제할 때 안전하고 단순하기 때문이다.

### Monitor

```text
id: str                           # UUID
name: str                         # 사람이 알아볼 대상 이름
url: str
method: str = "GET"
interval_seconds: int             # 예: 30, 최소 5
timeout_seconds: float            # 예: 5.0
expected_status_codes: set[int]   # 기본값: 200~399
max_attempts: int = 3             # 최초 요청 포함, 허용 범위 1~5
retry_delay_seconds: int = 5      # 실패한 요청 사이의 대기 시간
auth: AuthConfig | null           # 인증이 없는 대상은 null
enabled: bool = true

status: UNKNOWN | UP | DOWN
last_checked_at: datetime | null
last_status_code: int | null
last_response_time_ms: float | null
last_error: str | null
last_server_error_message: str | null # HTTP 오류 응답 본문에서 추출한 메시지
last_attempt_count: int | null    # 마지막 점검에서 실제 실행한 요청 횟수
next_check_at: datetime
is_checking: bool = false
alert_sent_for_current_outage: bool = false
```

### AuthConfig

JWT 인증이 필요한 대상은 모니터 생성/수정 요청에 인증 정보를 포함한다. 일반 API는 `auth: null`로 등록한다.

```text
type: NONE | JWT_LOGIN
login_url: str                    # JWT_LOGIN일 때만 필요
login_method: str = "POST"
login_payload: dict               # 예: {"username": "...", "password": "..."}
token_response_path: str          # 예: "access_token" 또는 "data.accessToken"
token_header_name: str = "Authorization"
token_prefix: str = "Bearer"

# 런타임 전용 값: API 응답으로 반환하지 않음
access_token: str | null
token_expires_at: datetime | null
auth_last_error: str | null
```

`login_payload`와 `access_token`은 메모리에만 보관하되, 조회 API의 응답에서는 마스킹하거나 아예 제외한다. `token_response_path`는 로그인 응답 JSON의 중첩 필드도 읽을 수 있도록 점(`.`) 표기법을 지원한다.

### EmailConfig

```text
smtp_host: str
smtp_port: int
username: str | null
password: str | null              # 메모리에만 보관, API 응답에서는 절대 반환하지 않음
use_starttls: bool
from_address: str
configured: bool
```

`EmailConfig`는 설정 API 요청으로 메모리에 넣는다. 비밀번호가 필요한 SMTP를 사용할 경우 이 API는 외부에 무방비로 공개하면 안 된다. 초기 버전도 신뢰 가능한 사설 네트워크에서만 실행하거나, 최소한 관리 API에 인증을 추가한 뒤 인터넷에 공개한다.

### NotificationRecipient

```text
id: str                           # UUID
name: str | null                  # 수신자 식별용 이름
email: EmailStr
enabled: bool = true
created_at: datetime
updated_at: datetime
```

초기 구현 검증 시 `pjh@literion.co.kr`를 수신자로 등록한다. 장애 또는 복구 이벤트가 발생하면 `enabled == true`인 모든 수신자에게 이메일을 보낸다.

## 7. 스케줄링과 상태 전이

스케줄러는 짧은 간격(예: 1초)으로 실행한다. 매 실행마다 `enabled == true`, `is_checking == false`, `next_check_at <= 현재 시각`인 모니터만 골라 `asyncio.gather()`로 비동기 병렬 점검한다. 초기 버전은 소규모 대상 사용을 전제로 전역 동시성 제한을 두지 않으며, 대상 수가 늘면 `asyncio.Semaphore` 제한을 추가한다.

```text
UNKNOWN ── 정상 결과 ──> UP
UNKNOWN ── 실패 결과 ──> DOWN (장애 메일)
UP      ── 실패 결과 ──> DOWN (장애 메일)
DOWN    ── 실패 결과 ──> DOWN (메일 없음)
DOWN    ── 정상 결과 ──> UP   (복구 메일)
```

각 점검은 최초 요청을 포함해 기본 최대 3회까지 실행한다. 요청이 실패하면 해당 모니터 작업 안에서 5초 동안 `asyncio.sleep()`으로 대기한 뒤 재시도한다. 이 대기는 다른 모니터 점검을 막지 않는다. 한 번이라도 정상 응답이 오면 즉시 재시도를 멈추고 `UP`으로 처리하며, 모든 시도가 실패했을 때만 `DOWN`으로 상태 전이와 장애 알림을 수행한다.

점검이 끝나면 결과와 `next_check_at = 현재 시각 + interval_seconds`를 저장한다. 알림 발송 실패는 점검 실패와 별개로 기록한다. 즉, 대상 서버가 정상이라도 SMTP 전송 실패 때문에 대상 상태를 `DOWN`으로 바꾸지 않는다. 초기 버전에서는 이메일 발송 실패를 자동 재시도하지 않으며, 필요해질 때 별도의 재시도 정책을 추가한다.

HTTP 오류 응답을 받은 경우에는 응답 본문에서 서버 오류 메시지도 추출한다. JSON 본문이면 `detail`, `message`, `error` 순서로 값을 찾고, 해당 필드가 없거나 일반 텍스트 응답이면 본문 텍스트를 사용한다. 연결 실패나 타임아웃처럼 응답이 없는 경우에는 `last_server_error_message`를 비우고 `last_error`에 클라이언트 측 예외 사유를 기록한다.

응답 본문에는 민감한 값이 포함될 수 있으므로 최대 1,000자까지만 저장하고 이메일에는 최대 500자까지만 포함한다. 저장·로그·이메일에 반영하기 전 `password`, `passwd`, `secret`, `token`, `authorization`, `cookie`, `api_key` 같은 키의 값은 마스킹한다. URL은 사용자 정보와 query string을 제거한 형태로만 로그와 이메일에 표시한다.

### JWT 인증 점검 흐름

1. `auth.type`이 `JWT_LOGIN`이고 토큰이 없거나 JWT의 `exp` 시각이 임박했으면 로그인 API를 호출한다.
2. 로그인 응답에서 `token_response_path`로 토큰을 읽고, JWT payload의 `exp`를 검증 없이 디코딩해 메모리의 만료 시각으로 사용한다. `exp`가 없으면 다음 정기 점검 전까지 토큰을 재사용한다.
3. 헬스 체크 요청에는 설정한 헤더 이름과 접두어로 토큰을 추가한다. 기본 헤더는 `Authorization: Bearer <token>`이다.
4. 헬스 체크가 `401` 또는 `403`이면 기존 토큰을 폐기하고 로그인 API를 한 번 더 호출한 뒤, 같은 헬스 체크 요청을 한 번만 다시 실행한다.
5. 로그인 실패, 토큰 추출 실패, 갱신 후에도 `401`/`403`인 경우에는 점검 실패로 기록하고 재시도 정책을 적용한다. 로그인 응답 본문은 저장하지 않고 상태 코드와 일반화한 인증 실패 사유만 남긴다.

## 8. API 초안

| 메서드 | 경로 | 설명 |
| --- | --- | --- |
| `POST` | `/monitors` | 모니터 대상 등록 |
| `GET` | `/monitors` | 모니터 대상 및 최신 상태 목록 |
| `GET` | `/monitors/{monitor_id}` | 대상 상세 상태 |
| `PATCH` | `/monitors/{monitor_id}` | 이름, URL, 주기, 타임아웃, 재시도 설정, 활성 여부 등 변경 |
| `DELETE` | `/monitors/{monitor_id}` | 대상 삭제 |
| `POST` | `/monitors/{monitor_id}/check` | 즉시 1회 점검 |
| `PUT` | `/email-config` | 인메모리 SMTP 발신 설정 교체 |
| `GET` | `/email-config` | 비밀번호를 제외한 이메일 설정 조회 |
| `POST` | `/email-config/test` | 활성 수신자 전체에 테스트 이메일 전송 |
| `POST` | `/recipients` | 이메일 수신자 등록 |
| `GET` | `/recipients` | 이메일 수신자 목록 |
| `GET` | `/recipients/{recipient_id}` | 이메일 수신자 상세 |
| `PATCH` | `/recipients/{recipient_id}` | 수신자 이름, 이메일, 활성 여부 변경 |
| `DELETE` | `/recipients/{recipient_id}` | 이메일 수신자 삭제 |
| `POST` | `/recipients/{recipient_id}/test` | 해당 수신자에게만 테스트 이메일 전송 |
| `GET` | `/status` | UP/DOWN/UNKNOWN 수 요약 |
| `GET` | `/health` | 이 FastAPI 프로세스의 생존 상태 |

### `POST /monitors` 요청 예시

```json
{
  "name": "주문 API",
  "url": "https://api.example.com/health",
  "method": "GET",
  "interval_seconds": 30,
  "timeout_seconds": 5,
  "max_attempts": 3,
  "retry_delay_seconds": 5,
  "expected_status_codes": [200],
  "auth": {
    "type": "JWT_LOGIN",
    "login_url": "https://api.example.com/auth/login",
    "login_method": "POST",
    "login_payload": {
      "username": "health-check-user",
      "password": "secret"
    },
    "token_response_path": "access_token",
    "token_header_name": "Authorization",
    "token_prefix": "Bearer"
  }
}
```

### `POST /recipients` 요청 예시

```json
{
  "name": "테스트 수신자",
  "email": "pjh@literion.co.kr",
  "enabled": true
}
```

### 응답 상태 예시

```json
{
  "id": "a1b2c3d4",
  "name": "주문 API",
  "url": "https://api.example.com/health",
  "enabled": true,
  "status": "DOWN",
  "last_checked_at": "2026-08-28T14:05:12+09:00",
  "last_status_code": 503,
  "last_response_time_ms": 1254.3,
  "last_error": "Unexpected status code: 503",
  "last_server_error_message": "Database connection pool exhausted",
  "last_attempt_count": 3
}
```

## 9. 이메일 내용

장애와 복구 이메일에는 대상 이름, URL, 감지 시각(KST), HTTP 상태 코드 또는 오류 사유, 응답 시간을 포함한다.

```text
제목: [DOWN] 주문 API 점검 실패

대상: https://api.example.com/health
시각: 2026-08-28 14:05:12 KST
결과: HTTP 503 Service Unavailable
서버 메시지: Database connection pool exhausted
응답 시간: 1254.3 ms
```

메일 전송은 요청 처리 흐름을 막지 않도록 별도 비동기 작업으로 실행한다. SMTP 라이브러리가 동기 방식이면 `asyncio.to_thread()`로 감싼다. 이벤트가 발생한 순간 활성 수신자 목록의 스냅샷을 만들고, 그 목록을 대상으로 발송하므로 수신자 CRUD가 진행 중이어도 현재 발송 작업이 흔들리지 않는다.

## 10. Swagger / OpenAPI 문서

FastAPI의 자동 OpenAPI 문서를 활성화해 다음 경로를 제공한다.

```text
GET /docs         # Swagger UI: 브라우저에서 API 호출 가능
GET /redoc        # 읽기 중심 API 문서
GET /openapi.json # OpenAPI 3 명세 JSON
```

### 문서 작성 기준

- 앱의 제목, 버전, 설명, private subnet 전용이라는 운영 제약을 OpenAPI 메타데이터에 작성한다.
- `모니터`, `수신자`, `이메일 설정`, `상태` 태그로 API를 분류한다.
- 모든 엔드포인트에 한국어 `summary`, 상세 `description`, 요청/응답 예시를 작성한다.
- 각 입력 필드에 의미, 기본값, 허용 범위, 예시를 작성한다. 예: `interval_seconds`는 기본값 30초, 최소값 5초이다.
- 각 엔드포인트에 성공 응답과 예상 오류 응답(`404`, `409`, `422`, `500`, `503`)의 의미와 본문 예시를 작성한다.
- Pydantic 모델의 필수/선택 필드, 형식, 최소/최대값, 열거형을 스키마에 노출한다.
- 이메일·로그인 비밀번호와 JWT는 `writeOnly` 필드로 표시하고, 어떤 응답 예시에도 실제 값을 넣지 않는다.
- `GET /email-config`와 모니터 조회 응답에는 비밀번호, 로그인 payload, access token을 아예 포함하지 않는다.
- Swagger 예시의 URL·이메일·계정 값은 테스트용 가짜 값만 사용한다. 실제 수신자 주소는 예시에 넣지 않는다.

### 엔드포인트별 문서 내용

| 태그 | 경로 | Swagger에 반드시 설명할 내용 |
| --- | --- | --- |
| 모니터 | `POST /monitors` | 주기, 타임아웃, 정상 코드, 재시도, JWT 인증 설정 및 생성 후 첫 점검 시점 |
| 모니터 | `GET /monitors`, `GET /monitors/{id}` | 상태 값 의미와 최근 점검 결과 필드 |
| 모니터 | `PATCH /monitors/{id}` | 변경 가능한 필드, 인증 설정 변경 시 JWT 폐기, `null`로 인증 해제하는 방법 |
| 모니터 | `DELETE /monitors/{id}` | 점검 중 삭제했을 때 결과를 저장하지 않는 동작 |
| 모니터 | `POST /monitors/{id}/check` | 즉시 점검, 재시도 포함 여부, 응답이 완료될 때까지의 동작 |
| 수신자 | `/recipients` 계열 | `enabled`의 의미와 삭제/비활성화 차이 |
| 이메일 설정 | `/email-config` 계열 | SMTP 발신 설정, 비밀번호 write-only 처리, 전체/개별 테스트 메일의 수신 대상 |
| 상태 | `GET /status`, `GET /health` | 집계 기준과 모니터링 서버 생존 여부의 의미 |

### 공통 오류 형식

도메인 오류는 아래 형식으로 통일해 Swagger 응답 예시에 포함한다. Pydantic 입력 검증 오류(`422`)는 FastAPI 표준 형식을 유지한다.

```json
{
  "detail": {
    "code": "MONITOR_NOT_FOUND",
    "message": "요청한 모니터를 찾을 수 없습니다."
  }
}
```

오류 코드 예시는 `MONITOR_NOT_FOUND`, `RECIPIENT_NOT_FOUND`, `EMAIL_CONFIG_NOT_SET`, `MONITOR_ALREADY_CHECKING`, `SMTP_SEND_FAILED`를 사용한다. 오류 응답에도 비밀번호, JWT, Authorization/Cookie 헤더, 원본 query string을 포함하지 않는다.

## 11. 동시성 및 오류 처리

- `MonitorStore` 변경은 `asyncio.Lock`으로 보호한다.
- HTTP 요청은 `httpx.AsyncClient`를 앱 수명 동안 재사용한다.
- 삭제된 모니터의 점검 결과가 다시 저장되지 않도록, 결과 저장 전 ID 존재 여부를 확인한다.
- URL, 점검 주기, 타임아웃, HTTP 메서드는 Pydantic 검증으로 제한한다.
- 로그인 요청의 payload, JWT, SMTP 비밀번호는 API 응답·애플리케이션 로그·이메일 본문에 포함하지 않는다.
- `Authorization`, `Cookie`, `Set-Cookie` 헤더와 비밀번호·토큰·API 키 성격의 요청/응답 값은 마스킹 처리한다.
- 오류 메시지와 URL을 이메일에 넣기 전에 공통 민감정보 마스킹 함수를 적용한다.
- 인증 설정을 변경하면 기존 JWT를 즉시 폐기해 다음 점검에서 새로 로그인한다.
- 외부 URL을 허용하면 내부망 주소를 호출하는 SSRF 위험이 생길 수 있다. 사내 전용 도구가 아니라면 허용 호스트/네트워크 제한 정책을 추가한다.

## 12. 파일 구성

```text
app/
  main.py              # 앱 생성, lifespan, 라우터 연결
  schemas.py           # Pydantic 요청/응답 모델
  models.py            # Monitor, AuthConfig, EmailConfig, NotificationRecipient 내부 모델
  store.py              # MonitorStore 및 동시성 제어
  checker.py            # httpx 기반 HTTP 점검
  scheduler.py          # 백그라운드 주기 점검 루프
  notifier.py           # SMTP 이메일 전송 및 템플릿
  routers/
    monitors.py         # 모니터 관리 API
    settings.py         # SMTP 설정 API
    recipients.py       # 이메일 수신자 CRUD API
Dockerfile              # 단일 컨테이너 이미지 정의
docker-compose.yml      # 로컬 컨테이너 실행 정의
.dockerignore           # 이미지에서 제외할 파일
tests/
  test_checker.py
  test_scheduler.py
  test_api.py
```

## 13. 구현 순서

1. FastAPI 프로젝트 골격과 Pydantic 모델을 만든다.
2. `MonitorStore` 및 모니터/이메일 수신자 CRUD API를 구현한다.
3. `httpx` 기반 단건 점검과 `POST /monitors/{id}/check`를 구현한다.
4. JWT 로그인, 토큰 추출/보관, 만료 갱신, 401/403 재인증 로직을 구현한다.
5. FastAPI lifespan 기반 스케줄러를 연결한다.
6. 상태 전이와 장애/복구 알림 중복 방지 로직을 구현한다.
7. SMTP 설정 API와 테스트 이메일 API를 구현한다.
8. 모의 HTTP 서버와 SMTP 모킹으로 단위/통합 테스트를 작성한다.
9. OpenAPI 메타데이터, 태그, 상세 설명, 요청/응답/오류 예시를 작성하고 Swagger UI에서 검증한다.
10. Dockerfile, docker-compose.yml, .dockerignore를 작성하고 단일 워커 컨테이너 실행을 검증한다.

## 14. 완료 기준

- API로 등록한 대상이 설정한 주기에 맞춰 실제로 점검된다.
- 최초 요청이 실패하더라도 5초 간격의 재시도 중 한 번이 성공하면 장애 메일을 보내지 않는다.
- 모든 허용 시도가 실패했을 때만 장애로 확정하고 이메일을 한 번 발송한다.
- JWT가 필요한 대상은 로그인 응답의 토큰으로 헬스 체크를 호출하고, 토큰 만료 또는 `401`/`403`일 때 자동으로 한 번 갱신한다.
- 인증 정보와 JWT는 어떠한 조회 응답, 로그, 이메일에도 노출되지 않는다.
- 정상/장애/복구 상태와 최근 결과가 조회된다.
- 첫 장애에서만 이메일이 한 번 발송되고, 지속 장애에서는 추가 발송되지 않는다.
- 복구 시 복구 이메일이 한 번 발송된다.
- 모니터, 이메일 수신자, 이메일 설정은 재시작 시 사라진다.
- 이메일 수신자는 API로 등록·조회·수정·삭제할 수 있고, 활성 수신자에게만 알림이 발송된다.
- 잘못된 URL 및 비정상적인 주기/타임아웃 값은 `422`로 거절된다.
- `/docs`에서 모든 API의 한국어 설명, 입력 제약, 성공/오류 응답 예시를 확인하고 호출할 수 있다.
- Swagger 문서 및 OpenAPI JSON에 비밀번호, JWT, 실제 수신자 이메일, Authorization/Cookie 값이 노출되지 않는다.
- `docker compose up --build` 후 호스트의 `GET /health`가 정상 응답한다.
- 컨테이너는 단일 워커로 실행되며, 재시작 후 인메모리 데이터가 초기화된다.
