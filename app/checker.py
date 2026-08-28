import asyncio
import time
from typing import Any, Dict, Optional

import httpx

from .models import CheckResult, Monitor
from .utils import extract_error_message, get_nested_value, jwt_expiration, sanitize_text, token_needs_refresh


class HealthChecker:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def check(self, monitor: Monitor) -> CheckResult:
        last_result: Optional[CheckResult] = None
        for attempt in range(1, monitor.max_attempts + 1):
            result = await self._check_once(monitor)
            result.attempt_count = attempt
            if result.success:
                return result
            last_result = result
            if attempt < monitor.max_attempts:
                await asyncio.sleep(monitor.retry_delay_seconds)
        return last_result or CheckResult(
            success=False,
            status_code=None,
            response_time_ms=None,
            error="점검 결과를 생성하지 못했습니다.",
            server_error_message=None,
            attempt_count=monitor.max_attempts,
        )

    async def _check_once(self, monitor: Monitor) -> CheckResult:
        try:
            headers = await self._auth_headers(monitor, force_refresh=False)
            response, elapsed_ms = await self._request_health(monitor, headers)
            if response.status_code in (401, 403) and monitor.auth is not None:
                headers = await self._auth_headers(monitor, force_refresh=True)
                response, elapsed_ms = await self._request_health(monitor, headers)
            if response.status_code in monitor.expected_status_codes:
                return CheckResult(True, response.status_code, elapsed_ms, None, None, 1)
            return CheckResult(
                success=False,
                status_code=response.status_code,
                response_time_ms=elapsed_ms,
                error="Unexpected status code: {}".format(response.status_code),
                server_error_message=extract_error_message(
                    response.content, response.headers.get("content-type", "")
                ),
                attempt_count=1,
            )
        except httpx.TimeoutException:
            return CheckResult(False, None, None, "Request timed out", None, 1)
        except httpx.RequestError as exc:
            return CheckResult(False, None, None, sanitize_text("Request failed: {}".format(str(exc))), None, 1)
        except AuthenticationError as exc:
            return CheckResult(False, exc.status_code, None, sanitize_text(str(exc)), None, 1)
        except Exception as exc:
            return CheckResult(False, None, None, "Unexpected check error: {}".format(type(exc).__name__), None, 1)

    async def _request_health(self, monitor: Monitor, headers: Dict[str, str]):
        start = time.perf_counter()
        response = await self._client.request(
            monitor.method,
            monitor.url,
            headers=headers,
            timeout=monitor.timeout_seconds,
        )
        return response, round((time.perf_counter() - start) * 1000, 2)

    async def _auth_headers(self, monitor: Monitor, force_refresh: bool) -> Dict[str, str]:
        if monitor.auth is None:
            return {}
        auth = monitor.auth
        if force_refresh:
            auth.access_token = None
            auth.token_expires_at = None
        if auth.access_token is None or token_needs_refresh(auth.token_expires_at):
            await self._login(monitor)
        if not auth.access_token:
            raise AuthenticationError("JWT token is not available")
        value = "{} {}".format(auth.token_prefix, auth.access_token).strip()
        return {auth.token_header_name: value}

    async def _login(self, monitor: Monitor) -> None:
        if monitor.auth is None:
            return
        auth = monitor.auth
        try:
            response = await self._client.request(
                auth.login_method,
                auth.login_url,
                json=auth.login_payload,
                timeout=monitor.timeout_seconds,
            )
        except httpx.RequestError as exc:
            auth.auth_last_error = "Login request failed"
            raise AuthenticationError("Login request failed: {}".format(str(exc)))
        if response.status_code < 200 or response.status_code >= 300:
            auth.auth_last_error = "Login API returned HTTP {}".format(response.status_code)
            raise AuthenticationError(auth.auth_last_error, response.status_code)
        try:
            payload: Any = response.json()
        except ValueError:
            auth.auth_last_error = "Login API did not return JSON"
            raise AuthenticationError(auth.auth_last_error, response.status_code)
        token = get_nested_value(payload, auth.token_response_path) if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token:
            auth.auth_last_error = "JWT token was not found in login response"
            raise AuthenticationError(auth.auth_last_error, response.status_code)
        auth.access_token = token
        auth.token_expires_at = jwt_expiration(token)
        auth.auth_last_error = None


class AuthenticationError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        self.status_code = status_code
        super().__init__(message)
