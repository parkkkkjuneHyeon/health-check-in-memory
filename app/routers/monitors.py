from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from ..dependencies import get_scheduler, get_store
from ..schemas import ErrorResponse, MonitorCreate, MonitorResponse, MonitorUpdate
from ..scheduler import MonitorScheduler
from ..store import AlreadyCheckingError, MonitorStore, NotFoundError


router = APIRouter(prefix="/monitors", tags=["모니터"])

NOT_FOUND = {404: {"model": ErrorResponse, "description": "모니터를 찾을 수 없습니다."}}


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail={"code": "MONITOR_NOT_FOUND", "message": "요청한 모니터를 찾을 수 없습니다."})


@router.post(
    "",
    response_model=MonitorResponse,
    status_code=status.HTTP_201_CREATED,
    summary="모니터 대상 등록",
    description="HTTP/HTTPS 헬스 체크 대상을 메모리에 등록합니다. 등록 직후 스케줄러가 첫 점검을 수행합니다.",
    responses={422: {"description": "URL, 주기, 타임아웃 또는 상태 코드 입력이 올바르지 않습니다."}},
)
async def create_monitor(data: MonitorCreate, store: MonitorStore = Depends(get_store)) -> MonitorResponse:
    return await store.create_monitor(data)


@router.get(
    "",
    response_model=List[MonitorResponse],
    summary="모니터 목록 조회",
    description="등록된 모든 모니터와 마지막 점검 결과를 반환합니다. 로그인 payload와 JWT는 포함하지 않습니다.",
)
async def list_monitors(store: MonitorStore = Depends(get_store)) -> List[MonitorResponse]:
    return await store.list_monitors()


@router.get(
    "/{monitor_id}",
    response_model=MonitorResponse,
    summary="모니터 상세 조회",
    description="모니터 설정과 최신 상태를 조회합니다. 인증 설정은 민감값을 제외한 정보만 반환합니다.",
    responses=NOT_FOUND,
)
async def get_monitor(monitor_id: str, store: MonitorStore = Depends(get_store)) -> MonitorResponse:
    try:
        return await store.get_monitor_response(monitor_id)
    except NotFoundError:
        raise _not_found()


@router.patch(
    "/{monitor_id}",
    response_model=MonitorResponse,
    summary="모니터 설정 변경",
    description="전달한 필드만 변경합니다. auth에 null을 명시하면 JWT 인증을 제거하며, 인증 설정을 바꾸면 기존 JWT는 폐기됩니다.",
    responses=NOT_FOUND,
)
async def update_monitor(monitor_id: str, data: MonitorUpdate, store: MonitorStore = Depends(get_store)) -> MonitorResponse:
    try:
        return await store.update_monitor(monitor_id, data)
    except NotFoundError:
        raise _not_found()


@router.delete(
    "/{monitor_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="모니터 삭제",
    description="모니터를 메모리에서 제거합니다. 진행 중인 점검이 끝나더라도 삭제된 대상의 결과는 저장하지 않습니다.",
    responses=NOT_FOUND,
)
async def delete_monitor(monitor_id: str, store: MonitorStore = Depends(get_store)) -> None:
    try:
        await store.delete_monitor(monitor_id)
    except NotFoundError:
        raise _not_found()


@router.post(
    "/{monitor_id}/check",
    response_model=MonitorResponse,
    summary="모니터 즉시 점검",
    description="해당 대상을 즉시 점검하고 최종 결과를 반환합니다. 실패 시 대상 설정의 재시도 횟수와 대기 시간을 적용합니다.",
    responses={
        **NOT_FOUND,
        409: {"model": ErrorResponse, "description": "이미 동일 모니터의 점검이 진행 중입니다."},
    },
)
async def check_monitor_now(
    monitor_id: str,
    scheduler: MonitorScheduler = Depends(get_scheduler),
) -> MonitorResponse:
    try:
        return await scheduler.check_now(monitor_id)
    except NotFoundError:
        raise _not_found()
    except AlreadyCheckingError:
        raise HTTPException(status_code=409, detail={"code": "MONITOR_ALREADY_CHECKING", "message": "이미 해당 모니터를 점검 중입니다."})
