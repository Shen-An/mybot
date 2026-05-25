"""Remote access authentication middleware — multi-user support."""

from __future__ import annotations

import os
import secrets
import string
import time
from collections.abc import Awaitable, Callable, Iterable

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware

from backend.database import get_db_session_factory
from backend.modules.auth.context import set_current_user_context, clear_current_user_context
from backend.modules.auth.utils import validate_auth_session, get_user_by_id, get_user_by_username

AUTH_COOKIE_NAME = "CountBot_token"
SETUP_SECRET_HEADER_NAME = "x-setup-secret"
SETUP_SECRET_LENGTH = 8
SETUP_SECRET_ALPHABET = string.ascii_letters
SETUP_SECRET_TTL_MINUTES_ENV = "REMOTE_SETUP_SECRET_TTL_MINUTES"
SETUP_SECRET_TTL_MINUTES_MIN = 10
SETUP_SECRET_TTL_MINUTES_MAX = 120
SETUP_SECRET_TTL_MINUTES_DEFAULT = 30

_FORWARDED_HEADER_NAMES = {
    "x-forwarded-for",
    "x-real-ip",
    "forwarded",
}

_PUBLIC_PATH_PREFIXES = (
    "/api/auth/",
    "/api/health",
    "/api/system/health",
)

_PROTECTED_PATH_PREFIXES = (
    "/api/",
)

_LOCAL_ONLY_SETUP_PATHS = (
    "/api/auth/setup",
)


def get_remote_setup_secret(app) -> str:
    return getattr(app.state, "remote_setup_secret", "")


def get_remote_setup_secret_expires_at(app) -> float:
    return float(getattr(app.state, "remote_setup_secret_expires_at", 0.0) or 0.0)


def get_remote_setup_secret_ttl_minutes() -> int:
    raw_value = os.getenv(SETUP_SECRET_TTL_MINUTES_ENV, str(SETUP_SECRET_TTL_MINUTES_DEFAULT)).strip()
    try:
        ttl_minutes = int(raw_value)
    except ValueError:
        ttl_minutes = SETUP_SECRET_TTL_MINUTES_DEFAULT
    return max(SETUP_SECRET_TTL_MINUTES_MIN, min(SETUP_SECRET_TTL_MINUTES_MAX, ttl_minutes))


def is_remote_setup_secret_expired(app) -> bool:
    expires_at = get_remote_setup_secret_expires_at(app)
    return expires_at > 0 and time.time() >= expires_at


def ensure_remote_setup_secret(app) -> str:
    secret = get_remote_setup_secret(app)
    had_secret = bool(secret)
    expired = had_secret and is_remote_setup_secret_expired(app)
    if not secret or expired:
        secret = "".join(secrets.choice(SETUP_SECRET_ALPHABET) for _ in range(SETUP_SECRET_LENGTH))
        app.state.remote_setup_secret = secret
        app.state.remote_setup_secret_expires_at = time.time() + get_remote_setup_secret_ttl_minutes() * 60
        if expired:
            logger.info(
                f"Remote setup secret expired and was refreshed for another {get_remote_setup_secret_ttl_minutes()} minute(s): /setup/{secret}"
            )
    return secret


def clear_remote_setup_secret(app) -> None:
    app.state.remote_setup_secret = ""
    app.state.remote_setup_secret_expires_at = 0.0


def has_valid_remote_setup_secret(app, candidate: str | None) -> bool:
    if is_remote_setup_secret_expired(app):
        ensure_remote_setup_secret(app)
        return False
    secret = get_remote_setup_secret(app)
    provided = (candidate or "").strip()
    return bool(secret and provided and secrets.compare_digest(secret, provided))


def request_has_valid_remote_setup_secret(request: Request) -> bool:
    return has_valid_remote_setup_secret(
        request.app,
        request.headers.get(SETUP_SECRET_HEADER_NAME, ""),
    )


def _is_loopback_host(host: str | None) -> bool:
    if not host:
        return False
    normalized = host.strip().lower()
    return normalized in {"127.0.0.1", "::1", "localhost"}


def is_direct_local_client(client_ip: str | None, header_keys: Iterable[str]) -> bool:
    """Return True only for direct loopback requests without proxy headers."""
    if not _is_loopback_host(client_ip):
        return False

    normalized_headers = {key.lower() for key in header_keys}
    return not any(header in normalized_headers for header in _FORWARDED_HEADER_NAMES)


def _is_local_request(request: Request) -> bool:
    client_ip = request.client.host if request.client and request.client.host else None
    return is_direct_local_client(client_ip, request.headers.keys())


async def _get_default_local_user(db) -> object | None:
    """Return the first active admin user for local requests without a session."""
    try:
        from backend.models.user import User
        from sqlalchemy import select
        result = await db.execute(select(User).where(User.is_active == True).order_by(User.id).limit(1))  # noqa: E712
        return result.scalar_one_or_none()
    except Exception:
        return None


def _extract_token_from_request(request: Request) -> str | None:
    """Extract auth token from cookie or Bearer header."""
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    return token or None


class RemoteAuthMiddleware(BaseHTTPMiddleware):
    """Protect non-local HTTP requests with cookie or bearer-token auth — multi-user."""

    def __init__(
        self,
        app,
        get_password_hash_fn: Callable[[], Awaitable[str]],
    ) -> None:
        super().__init__(app)
        self._get_password_hash = get_password_hash_fn

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        if _is_local_request(request):
            # 本地请求：尝试从 cookie/header 恢复用户上下文
            local_token = _extract_token_from_request(request)

            try:
                db = get_db_session_factory()()
                try:
                    uid = None
                    if local_token:
                        uid = await validate_auth_session(local_token, db)

                    if uid:
                        u = await get_user_by_id(uid, db)
                    else:
                        # 无有效 token 时，使用首个 admin 作为默认本地用户
                        u = await _get_default_local_user(db)
                    if u and u.is_active:
                        request.state.user_id = u.id
                        request.state.user = u
                        set_current_user_context(u.id, u.username, u.role)
                finally:
                    await db.close()
            except Exception:
                pass

            return await call_next(request)

        if not any(path.startswith(prefix) for prefix in _PROTECTED_PATH_PREFIXES):
            return await call_next(request)

        if any(path.startswith(prefix) for prefix in _PUBLIC_PATH_PREFIXES):
            if (
                path in _LOCAL_ONLY_SETUP_PATHS
                and not _is_local_request(request)
                and not request_has_valid_remote_setup_secret(request)
            ):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "首次初始化只能在本机完成", "code": "SETUP_LOCAL_ONLY"},
                )
            return await call_next(request)

        password_hash = await self._get_password_hash()
        if not password_hash:
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication setup required", "code": "AUTH_SETUP_REQUIRED"},
            )

        token = _extract_token_from_request(request)

        if not token:
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required", "code": "AUTH_REQUIRED"},
            )

        # Validate session and get user_id
        db = get_db_session_factory()()
        try:
            user_id = await validate_auth_session(token, db)
            if user_id is None:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Authentication required", "code": "AUTH_REQUIRED"},
                )

            # Load full user object
            user = await get_user_by_id(user_id, db)
            if user is None or not user.is_active:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "User not found or deactivated", "code": "AUTH_REQUIRED"},
                )

            # Set user context on request.state for downstream handlers
            request.state.user_id = user.id
            request.state.user = user

            # Set contextvars for non-HTTP code paths
            set_current_user_context(user.id, user.username, user.role)

        finally:
            await db.close()

        return await call_next(request)
