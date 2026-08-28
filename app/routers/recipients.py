from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from ..dependencies import get_store
from ..notifier import EmailNotifier
from ..schemas import ErrorResponse, MessageResponse, RecipientCreate, RecipientResponse, RecipientUpdate
from ..store import MonitorStore, NotFoundError


router = APIRouter(prefix="/recipients", tags=["수신자"])
NOT_FOUND = {404: {"model": ErrorResponse, "description": "수신자를 찾을 수 없습니다."}}


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail={"code": "RECIPIENT_NOT_FOUND", "message": "요청한 이메일 수신자를 찾을 수 없습니다."})


@router.post("", response_model=RecipientResponse, status_code=status.HTTP_201_CREATED, summary="이메일 수신자 등록", description="장애와 복구 이메일을 받을 수신자를 등록합니다. enabled가 false인 수신자는 알림에서 제외됩니다.")
async def create_recipient(data: RecipientCreate, store: MonitorStore = Depends(get_store)) -> RecipientResponse:
    return await store.create_recipient(data)


@router.get("", response_model=List[RecipientResponse], summary="이메일 수신자 목록", description="인메모리에 등록된 이메일 수신자 목록을 반환합니다.")
async def list_recipients(store: MonitorStore = Depends(get_store)) -> List[RecipientResponse]:
    return await store.list_recipients()


@router.get("/{recipient_id}", response_model=RecipientResponse, summary="이메일 수신자 상세", description="수신자 한 명의 설정을 조회합니다.", responses=NOT_FOUND)
async def get_recipient(recipient_id: str, store: MonitorStore = Depends(get_store)) -> RecipientResponse:
    try:
        return await store.get_recipient_response(recipient_id)
    except NotFoundError:
        raise _not_found()


@router.patch("/{recipient_id}", response_model=RecipientResponse, summary="이메일 수신자 수정", description="이름, 이메일 주소, 활성 여부 중 전달한 필드만 수정합니다.", responses=NOT_FOUND)
async def update_recipient(recipient_id: str, data: RecipientUpdate, store: MonitorStore = Depends(get_store)) -> RecipientResponse:
    try:
        return await store.update_recipient(recipient_id, data)
    except NotFoundError:
        raise _not_found()


@router.delete("/{recipient_id}", status_code=status.HTTP_204_NO_CONTENT, summary="이메일 수신자 삭제", description="수신자를 메모리에서 제거합니다. 이후 알림 발송 대상에서 제외됩니다.", responses=NOT_FOUND)
async def delete_recipient(recipient_id: str, store: MonitorStore = Depends(get_store)) -> None:
    try:
        await store.delete_recipient(recipient_id)
    except NotFoundError:
        raise _not_found()


@router.post("/{recipient_id}/test", response_model=MessageResponse, summary="개별 테스트 이메일 전송", description="해당 수신자 한 명에게 SMTP 테스트 이메일을 전송합니다.", responses={**NOT_FOUND, 503: {"model": ErrorResponse, "description": "SMTP 설정 또는 전송에 실패했습니다."}})
async def send_recipient_test(recipient_id: str, store: MonitorStore = Depends(get_store)) -> MessageResponse:
    try:
        recipient = await store.get_recipient_email(recipient_id)
    except NotFoundError:
        raise _not_found()
    notifier = EmailNotifier()
    error = await notifier.send_test(await store.get_email_config(), [recipient])
    if error:
        raise HTTPException(status_code=503, detail={"code": "SMTP_SEND_FAILED", "message": error})
    return MessageResponse(message="테스트 이메일을 전송했습니다.")
