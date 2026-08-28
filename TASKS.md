# 구현 작업 목록

상세 설계는 [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)를 기준으로 한다. 아래 작업은 위에서 아래 순서로 진행한다.

## 1. 프로젝트 기반

- [x] FastAPI 실행 진입점과 `lifespan` 골격 생성
- [x] 의존성 정의: FastAPI, Uvicorn, httpx, Pydantic, 이메일 검증 도구
- [x] `app/` 및 `tests/` 디렉터리 구조 생성
- [x] `GET /health` 구현

완료 기준: 서버가 실행되고 `GET /health`가 `200`을 반환한다.

## 2. 인메모리 모델과 스토어

- [x] `Monitor`, `AuthConfig`, `EmailConfig`, `NotificationRecipient` 모델 구현
- [x] 상태 값 `UNKNOWN`, `UP`, `DOWN` 정의
- [x] ID 기반 인메모리 `MonitorStore` 구현
- [x] 모니터/수신자/SMTP 설정을 위한 `asyncio.Lock` 적용
- [x] 서버 재시작 시 모든 데이터가 초기화되는지 확인

완료 기준: 외부 저장소 없이 객체 생성·조회·수정·삭제가 가능하다.

## 3. 모니터 CRUD API

- [x] `POST /monitors` 구현
- [x] `GET /monitors`, `GET /monitors/{monitor_id}` 구현
- [x] `PATCH /monitors/{monitor_id}` 구현
- [x] `DELETE /monitors/{monitor_id}` 구현
- [x] URL, HTTP 메서드, 주기, 타임아웃, 재시도 설정 유효성 검증

완료 기준: 잘못된 입력은 `422`, 존재하지 않는 ID는 `404`를 반환한다.

## 4. 이메일 수신자 CRUD API

- [x] `POST /recipients` 구현
- [x] `GET /recipients`, `GET /recipients/{recipient_id}` 구현
- [x] `PATCH /recipients/{recipient_id}` 구현
- [x] `DELETE /recipients/{recipient_id}` 구현
- [x] 이메일 주소 검증 및 `enabled` 상태 처리
- [ ] `pjh@literion.co.kr`를 테스트 수신자로 등록해 검증

완료 기준: 수신자를 관리할 수 있고 비활성 수신자는 알림 대상에서 제외된다.

## 5. HTTP 헬스 체크

- [x] 앱 수명 동안 재사용하는 `httpx.AsyncClient` 구성
- [x] 성공 코드와 실패 코드 판정 구현
- [x] 타임아웃, DNS, 연결, TLS 예외 처리
- [x] 오류 응답 본문에서 `detail`, `message`, `error` 추출
- [x] 오류 메시지 저장 길이(1,000자) 제한
- [x] 오류 메시지와 URL에 공통 민감정보 마스킹 적용
- [x] `POST /monitors/{monitor_id}/check` 구현

완료 기준: 정상, 4xx/5xx, 타임아웃, 연결 실패 결과가 모니터 상태에 정확히 기록된다.

## 6. JWT 로그인 인증

- [x] `auth: null` 및 `auth.type: JWT_LOGIN` 요청 검증
- [x] 로그인 API URL, 메서드, payload, 토큰 응답 경로 입력 지원
- [x] 점 표기법 토큰 경로 파싱 구현
- [x] JWT `exp`를 읽어 만료 전 토큰 갱신
- [x] 인증 헤더에 `Bearer` 토큰 추가
- [x] `401`/`403` 시 토큰 폐기, 로그인, 헬스 체크 1회 재실행
- [x] 인증 정보·토큰·Authorization/Cookie 헤더가 응답, 로그, 이메일에 노출되지 않도록 확인

완료 기준: 로그인 후 JWT가 필요한 테스트 서버의 헬스 체크가 성공한다.

## 7. 재시도와 스케줄러

- [x] 최초 요청 포함 최대 3회 시도 구현
- [x] 실패한 요청 사이 5초 비동기 대기 구현
- [x] 성공하면 남은 재시도 중단
- [x] 모든 시도가 실패할 때만 `DOWN` 확정
- [x] FastAPI lifespan에서 백그라운드 스케줄러 시작·종료
- [x] `next_check_at` 기반 대상별 점검 주기 적용
- [x] 동일 대상 중복 점검 방지

완료 기준: 한 대상의 재시도 대기가 다른 대상의 점검을 지연시키지 않는다.

## 8. 이메일 발송과 상태 알림

- [x] `PUT /email-config`, `GET /email-config` 구현
- [x] SMTP 비밀번호가 응답에 절대 포함되지 않도록 처리
- [x] `POST /email-config/test` 및 `POST /recipients/{recipient_id}/test` 구현
- [x] 장애 전환 시 활성 수신자 전체에 장애 메일 발송
- [x] 복구 전환 시 활성 수신자 전체에 복구 메일 발송
- [x] 지속 장애에서 중복 알림 방지
- [x] 이메일 발송 실패를 모니터 장애와 분리해 기록
- [x] 이메일 발송 실패는 초기 버전에서 자동 재시도하지 않도록 확인

완료 기준: 최초 장애와 복구에서 각 1회만 이메일이 발송된다.

## 9. 상태 조회와 테스트

- [x] `GET /status`에 UP/DOWN/UNKNOWN 집계 반환
- [x] 모니터 CRUD 테스트 작성
- [x] 수신자 CRUD 테스트 작성
- [x] HTTP 성공/실패 및 오류 메시지 추출 테스트 작성
- [x] JWT 로그인/토큰 갱신 테스트 작성
- [x] 재시도 및 중복 알림 방지 테스트 작성
- [x] SMTP 발송을 모킹한 통합 테스트 작성

완료 기준: 전체 테스트가 통과하고, 기획서의 완료 기준을 모두 만족한다.

## 10. Swagger / OpenAPI 문서

- [x] OpenAPI 앱 제목, 버전, 상세 설명 및 private subnet 운영 제약 작성
- [x] `모니터`, `수신자`, `이메일 설정`, `상태` 태그 정의
- [x] 모든 엔드포인트에 한국어 `summary`와 상세 `description` 작성
- [x] 모든 요청 모델에 필드 설명, 기본값, 범위, 유효한 예시 추가
- [x] 모든 성공 응답과 `404`/`409`/`422`/`500`/`503` 오류 응답 예시 추가
- [x] 도메인 오류 코드와 공통 오류 응답 형식 구현
- [x] 비밀번호와 JWT를 `writeOnly`로 표시하고, 조회 응답/예시에 노출되지 않는지 확인
- [x] Swagger 예시에 실제 이메일 주소, 계정, 토큰, 민감 URL query가 없는지 확인
- [x] `/docs`, `/redoc`, `/openapi.json`을 컨테이너 실행 환경에서 확인

완료 기준: Swagger UI만 보고 모든 API의 목적, 입력값, 성공 응답, 오류 처리 방식을 이해하고 테스트 호출할 수 있다.

## 11. Docker 실행 환경

- [x] Python 슬림 이미지를 사용하는 `Dockerfile` 작성
- [x] `.dockerignore` 작성
- [x] 단일 컨테이너 실행용 `docker-compose.yml` 작성
- [x] Uvicorn이 반드시 `--workers 1`로 실행되도록 설정
- [ ] 컨테이너를 private subnet에만 배포하고 public IP/공개 인바운드 규칙을 사용하지 않도록 배포 설정 확인
- [x] `docker compose up --build`로 이미지 빌드 및 컨테이너 실행 확인
- [x] 호스트에서 `GET /health` 호출 확인
- [ ] 컨테이너 재시작 후 인메모리 데이터 초기화 확인

완료 기준: `docker compose up --build`만으로 서버를 실행할 수 있고, 중복 스케줄러 없이 단일 메모리 스토어가 동작한다.

## 12. 관리 대시보드

- [x] FastAPI 정적 파일 제공과 `/` 관리 화면 라우팅
- [x] 상태 요약과 모니터 목록 자동 새로고침
- [x] 모니터 등록·수정·삭제·활성화·즉시 점검 UI
- [x] 이메일 수신자 CRUD UI
- [x] SMTP 설정 저장 및 테스트 이메일 발송 UI
- [x] Swagger 링크와 모바일 대응 화면 구성

완료 기준: 관리 화면만으로 SMTP 설정, 수신자 등록, 모니터 관리와 즉시 점검을 수행할 수 있다.
