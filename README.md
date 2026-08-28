# 인메모리 서버 헬스 체크

FastAPI 기반 HTTP/JWT 헬스 체크 서버입니다. 등록한 대상의 상태를 주기적으로 확인하고 장애·복구 시 SMTP 이메일을 보냅니다. 모든 설정은 메모리에만 저장되므로 컨테이너나 서버가 재시작되면 초기화됩니다.

## 실행

이 서비스는 private subnet에서만 실행하는 것을 전제로 합니다.

```bash
docker compose up --build
```

- 관리 대시보드: `http://<internal-host>:8000/`
- Swagger UI: `http://<internal-host>:8000/docs`
- ReDoc: `http://<internal-host>:8000/redoc`
- 상태 확인: `http://<internal-host>:8000/health`

Uvicorn은 인메모리 스토어와 중복 스케줄러를 방지하기 위해 단일 워커로 실행됩니다.

## 관리 대시보드

관리 대시보드에서는 별도 API 도구 없이 아래 기능을 사용할 수 있습니다.

- UP/DOWN/UNKNOWN 상태 요약과 15초 자동 새로고침
- 모니터 등록·수정·삭제·정기 점검 중지·즉시 점검
- 최근 HTTP 상태, 응답 시간, 서버 오류 메시지 확인
- 이메일 수신자 등록·활성화·삭제
- SMTP 설정 저장 및 테스트 이메일 발송

JWT 로그인 payload와 SMTP 비밀번호는 화면에 다시 표시하지 않습니다. Swagger는 고급 API 설정·호출 확인에 사용할 수 있습니다.

## 초기 설정 순서

1. `PUT /email-config`로 SMTP 발신 설정을 저장합니다.
2. `POST /recipients`로 이메일 수신자를 등록합니다.
3. `POST /email-config/test`로 테스트 메일을 확인합니다.
4. `POST /monitors`로 헬스 체크 대상을 등록합니다.

JWT가 필요한 대상은 `auth.login_url`, `auth.login_payload`, `auth.token_response_path`를 함께 입력합니다. 로그인 payload와 SMTP 비밀번호, JWT는 조회 응답·로그·이메일에 포함하지 않습니다.

초기에 가상환경을 만든다면 
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt

이미 가상 환경이 있다면 
source .venv/bin/activate