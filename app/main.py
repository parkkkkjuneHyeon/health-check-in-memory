import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .checker import HealthChecker
from .notifier import EmailNotifier
from .routers import monitors, recipients, settings
from .schemas import HealthResponse, StatusSummary
from .scheduler import MonitorScheduler
from .store import MonitorStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = MonitorStore()
    client = httpx.AsyncClient()
    scheduler = MonitorScheduler(store, HealthChecker(client), EmailNotifier())
    task = asyncio.create_task(scheduler.run(), name="health-monitor-scheduler")
    app.state.store = store
    app.state.scheduler = scheduler
    try:
        yield
    finally:
        await scheduler.stop()
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        await client.aclose()


app = FastAPI(
    title="인메모리 서버 헬스 체크 API",
    version="0.1.0",
    description=(
        "private subnet에서 실행하는 단일 프로세스 HTTP 서버 모니터링 API입니다. "
        "모니터와 SMTP 설정, 수신자 목록은 재시작 시 모두 초기화됩니다. "
        "관리 API에는 로그인 payload, SMTP 비밀번호, JWT를 절대 반환하지 않습니다."
    ),
    openapi_tags=[
        {"name": "모니터", "description": "HTTP/JWT 헬스 체크 대상 관리 및 즉시 점검"},
        {"name": "수신자", "description": "장애·복구 이메일 수신자 관리"},
        {"name": "이메일 설정", "description": "인메모리 SMTP 발신 설정과 테스트 이메일"},
        {"name": "상태", "description": "모니터링 서버와 대상 요약 상태"},
    ],
    lifespan=lifespan,
)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.include_router(monitors.router)
app.include_router(recipients.router)
app.include_router(settings.router)


@app.get("/", include_in_schema=False)
async def dashboard() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get(
    "/status",
    response_model=StatusSummary,
    tags=["상태"],
    summary="모니터 상태 요약",
    description="UP, DOWN, UNKNOWN 모니터 수와 스케줄러 실행 여부를 반환합니다.",
)
async def get_status() -> StatusSummary:
    up, down, unknown, total, scheduler_running = await app.state.store.summary()
    return StatusSummary(up=up, down=down, unknown=unknown, total=total, scheduler_running=scheduler_running)


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["상태"],
    summary="모니터링 서버 생존 확인",
    description="이 FastAPI 프로세스가 HTTP 요청을 처리할 수 있음을 확인합니다. 개별 대상 서버의 상태를 의미하지는 않습니다.",
)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")
