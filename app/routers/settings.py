from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_store
from ..notifier import EmailNotifier
from ..schemas import EmailConfigInput, EmailConfigResponse, ErrorResponse, MessageResponse
from ..store import MonitorStore, NotFoundError


router = APIRouter(prefix="/email-config", tags=["이메일 설정"])


@router.put(
    "",
    response_model=EmailConfigResponse,
    summary="SMTP 발신 설정 저장",
    description="SMTP 서버와 발신자 설정을 메모리에 교체 저장합니다. password는 write-only이며 조회 응답에 포함되지 않습니다.",
)
async def set_email_config(data: EmailConfigInput, store: MonitorStore = Depends(get_store)) -> EmailConfigResponse:
    return await store.set_email_config(data)


@router.get(
    "",
    response_model=EmailConfigResponse,
    summary="SMTP 발신 설정 조회",
    description="현재 메모리의 SMTP 발신 설정을 조회합니다. 비밀번호는 절대 반환하지 않습니다.",
    responses={404: {"model": ErrorResponse, "description": "SMTP 설정이 없습니다."}},
)
async def get_email_config(store: MonitorStore = Depends(get_store)) -> EmailConfigResponse:
    try:
        return await store.get_email_config_response()
    except NotFoundError:
        raise HTTPException(status_code=404, detail={"code": "EMAIL_CONFIG_NOT_SET", "message": "SMTP 이메일 설정이 없습니다."})


@router.post(
    "/test",
    response_model=MessageResponse,
    summary="활성 수신자 전체 테스트 이메일 전송",
    description="현재 SMTP 설정으로 enabled=true인 모든 수신자에게 테스트 이메일을 전송합니다.",
    responses={503: {"model": ErrorResponse, "description": "SMTP 설정, 활성 수신자 또는 전송에 실패했습니다."}},
)
async def send_all_test(store: MonitorStore = Depends(get_store)) -> MessageResponse:
    notifier = EmailNotifier()
    error = await notifier.send_test(
        await store.get_email_config(), await store.get_enabled_recipient_emails()
    )
    if error:
        raise HTTPException(status_code=503, detail={"code": "SMTP_SEND_FAILED", "message": error})
    return MessageResponse(message="활성 수신자에게 테스트 이메일을 전송했습니다.")
