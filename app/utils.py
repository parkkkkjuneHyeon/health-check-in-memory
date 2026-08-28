import base64
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from urllib.parse import urlsplit, urlunsplit


MAX_STORED_ERROR_LENGTH = 1000
MAX_EMAIL_ERROR_LENGTH = 500
_SENSITIVE_KEY_PATTERN = re.compile(
    r"(?i)(password|passwd|secret|token|authorization|cookie|api[_-]?key)"
)
_SENSITIVE_PAIR_PATTERN = re.compile(
    r"(?i)((?:[\"']?(?:password|passwd|secret|token|authorization|cookie|api[_-]?key)[\"']?)\s*[=:]\s*[\"']?)([^\s,;}&\"']+)"
)
_URL_CREDENTIAL_PATTERN = re.compile(r"//[^/@\s:]+:[^/@\s]+@")
_URL_QUERY_PATTERN = re.compile(r"(https?://[^\s?#]+)\?[^\s]+")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def sanitize_text(value: Optional[str], limit: int = MAX_STORED_ERROR_LENGTH) -> Optional[str]:
    if not value:
        return None
    masked = _SENSITIVE_PAIR_PATTERN.sub(r"\1***", str(value))
    masked = _URL_CREDENTIAL_PATTERN.sub("//***:***@", masked)
    masked = _URL_QUERY_PATTERN.sub(r"\1", masked)
    return masked[:limit]


def sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "***" if _SENSITIVE_KEY_PATTERN.search(str(key)) else sanitize_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize_value(item) for item in value]
    if isinstance(value, str):
        return sanitize_text(value)
    return value


def display_url(url: str) -> str:
    """Return a URL safe to place in logs and emails."""
    parsed = urlsplit(url)
    hostname = parsed.hostname or ""
    netloc = hostname
    if parsed.port:
        netloc = "{}:{}".format(hostname, parsed.port)
    return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))


def extract_error_message(content: bytes, content_type: str) -> Optional[str]:
    if not content:
        return None
    text = content.decode("utf-8", errors="replace")
    if "json" in content_type.lower():
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return sanitize_text(text)
        if isinstance(payload, dict):
            for key in ("detail", "message", "error"):
                if key in payload:
                    value = payload[key]
                    if isinstance(value, (dict, list)):
                        value = json.dumps(sanitize_value(value), ensure_ascii=False)
                    return sanitize_text(str(value))
            return sanitize_text(json.dumps(sanitize_value(payload), ensure_ascii=False))
    return sanitize_text(text)


def get_nested_value(payload: Dict[str, Any], path: str) -> Optional[Any]:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def jwt_expiration(token: str) -> Optional[datetime]:
    """Read exp only for cache timing; signature validation belongs to the target server."""
    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        encoded_payload = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(encoded_payload.encode("ascii")))
        exp = payload.get("exp")
        if exp is None:
            return None
        return datetime.fromtimestamp(float(exp), tz=timezone.utc)
    except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def token_needs_refresh(expires_at: Optional[datetime]) -> bool:
    if expires_at is None:
        return False
    return utc_now() + timedelta(seconds=30) >= expires_at
