import asyncio
import smtplib
from email.message import EmailMessage
from typing import Iterable, Optional, Tuple
from zoneinfo import ZoneInfo

from .models import EmailConfig, NotificationEvent, NotificationKind
from .utils import MAX_EMAIL_ERROR_LENGTH, sanitize_text


class EmailNotifier:
    async def send_event(
        self,
        config: Optional[EmailConfig],
        recipients: Iterable[str],
        event: NotificationEvent,
    ) -> Optional[str]:
        recipient_list = list(recipients)
        if config is None:
            return "SMTP email config is not set"
        if not recipient_list:
            return "No enabled email recipients are configured"
        try:
            await asyncio.to_thread(self._send, config, recipient_list, self._event_message(config, event))
            return None
        except (OSError, smtplib.SMTPException) as exc:
            return sanitize_text("SMTP send failed: {}".format(str(exc)), MAX_EMAIL_ERROR_LENGTH)

    async def send_test(
        self, config: Optional[EmailConfig], recipients: Iterable[str]
    ) -> Optional[str]:
        recipient_list = list(recipients)
        if config is None:
            return "SMTP email config is not set"
        if not recipient_list:
            return "No enabled email recipients are configured"
        message = EmailMessage()
        message["Subject"] = "[TEST] Health Check 이메일 발송 테스트"
        message["From"] = config.from_address
        message["To"] = ", ".join(recipient_list)
        message.set_content("헬스 체크 서버의 SMTP 발송 테스트 이메일입니다.")
        try:
            await asyncio.to_thread(self._send, config, recipient_list, message)
            return None
        except (OSError, smtplib.SMTPException) as exc:
            return sanitize_text("SMTP send failed: {}".format(str(exc)), MAX_EMAIL_ERROR_LENGTH)

    @staticmethod
    def _event_message(config: EmailConfig, event: NotificationEvent) -> EmailMessage:
        prefix = "DOWN" if event.kind == NotificationKind.DOWN else "RECOVERED"
        message = EmailMessage()
        message["Subject"] = "[{}] {}".format(prefix, event.monitor_name)
        message["From"] = config.from_address
        body_lines = [
            "대상: {}".format(event.url),
            "시각(KST): {}".format(event.checked_at.astimezone(ZoneInfo("Asia/Seoul")).isoformat()),
        ]
        if event.status_code is not None:
            body_lines.append("HTTP 상태 코드: {}".format(event.status_code))
        if event.error:
            body_lines.append("오류: {}".format(sanitize_text(event.error, MAX_EMAIL_ERROR_LENGTH)))
        if event.server_error_message:
            body_lines.append("서버 메시지: {}".format(sanitize_text(event.server_error_message, MAX_EMAIL_ERROR_LENGTH)))
        if event.response_time_ms is not None:
            body_lines.append("응답 시간: {} ms".format(event.response_time_ms))
        message.set_content("\n".join(body_lines))
        return message

    @staticmethod
    def _send(config: EmailConfig, recipients: Iterable[str], message: EmailMessage) -> None:
        recipient_list = list(recipients)
        if "To" not in message:
            message["To"] = ", ".join(recipient_list)
        with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=15) as server:
            if config.use_starttls:
                server.starttls()
            if config.username:
                server.login(config.username, config.password or "")
            server.send_message(message, from_addr=config.from_address, to_addrs=recipient_list)
