"""Authentication API endpoints — multi-user support."""

import asyncio
import json
import threading
import time
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import AsyncSessionLocal, get_db
from backend.models.setting import Setting
from backend.models.user import User
from backend.modules.auth.middleware import (
    AUTH_COOKIE_NAME,
    _is_local_request,
    clear_remote_setup_secret,
    request_has_valid_remote_setup_secret,
)
from backend.modules.auth.utils import (
    TOKEN_EXPIRY,
    create_auth_session,
    create_user,
    delete_user,
    get_user_by_id,
    get_user_by_username,
    hash_password,
    list_users,
    needs_password_rehash,
    revoke_all_auth_sessions,
    revoke_auth_session,
    update_user,
    validate_password,
    validate_username,
    verify_password,
    utc_now,
)
from backend.modules.auth.context import clear_current_user_context
from backend.utils.runtime_env import is_public_bind_host

router = APIRouter(prefix="/api/auth", tags=["auth"])

_AUTH_KEY_USERNAME = "auth.username"
_AUTH_KEY_PASSWORD_HASH = "auth.password_hash"

_RATE_LIMIT_WINDOW_SECONDS = 15 * 60
_RATE_LIMIT_MAX_ATTEMPTS = 5
_RATE_LIMIT_LOCKOUT_SECONDS = 15 * 60
_auth_attempt_lock = threading.Lock()
_auth_attempts: Dict[str, list[float]] = {}
_auth_lockouts: Dict[str, float] = {}


class LoginRequest(BaseModel):
    username: str
    password: str


class SetPasswordRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = Field(default="user", description="admin | operator | user")
    display_name: Optional[str] = None


class RegisterRequest(BaseModel):
    username: str
    password: str
    display_name: Optional[str] = None


class UpdateUserRequest(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None
    display_name: Optional[str] = None
    is_active: Optional[bool] = None


async def get_stored_credentials() -> Tuple[str, str]:
    """Load stored username and password hash from settings (legacy, for backward compatibility)."""
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Setting).where(Setting.key.in_([_AUTH_KEY_USERNAME, _AUTH_KEY_PASSWORD_HASH]))
            )
            settings = {s.key: s.value for s in result.scalars().all()}
            username = json.loads(settings.get(_AUTH_KEY_USERNAME, '""'))
            password_hash = json.loads(settings.get(_AUTH_KEY_PASSWORD_HASH, '""'))
            return username or "", password_hash or ""
    except Exception as exc:
        logger.warning(f"Failed to get stored credentials: {exc}")
        return "", ""


async def get_password_hash() -> str:
    """Get password hash for middleware authentication check."""
    _, password_hash = await get_stored_credentials()
    return password_hash


async def save_credentials(username: str, password_hash: str):
    """Save credentials to settings table (legacy, for backward compatibility during migration)."""
    async with AsyncSessionLocal() as session:
        for key, value in ((_AUTH_KEY_USERNAME, username), (_AUTH_KEY_PASSWORD_HASH, password_hash)):
            setting = Setting(key=key, value=json.dumps(value))
            await session.merge(setting)
        await session.commit()


def _client_ip(request: Request) -> str:
    return request.client.host if request.client and request.client.host else "unknown"


def _auth_rate_limit_key(action: str, request: Request, username: str = "") -> str:
    normalized_username = username.strip().lower()
    return f"{action}:{_client_ip(request)}:{normalized_username}"


def _prune_attempts(now: float) -> None:
    stale_before = now - _RATE_LIMIT_WINDOW_SECONDS

    expired_attempt_keys = []
    for key, attempts in _auth_attempts.items():
        filtered = [ts for ts in attempts if ts >= stale_before]
        if filtered:
            _auth_attempts[key] = filtered
        else:
            expired_attempt_keys.append(key)

    for key in expired_attempt_keys:
        _auth_attempts.pop(key, None)

    expired_lockouts = [key for key, until in _auth_lockouts.items() if until <= now]
    for key in expired_lockouts:
        _auth_lockouts.pop(key, None)


def _check_rate_limit(action: str, request: Request, username: str = "") -> Tuple[bool, int]:
    key = _auth_rate_limit_key(action, request, username)
    now = time.time()

    with _auth_attempt_lock:
        _prune_attempts(now)
        locked_until = _auth_lockouts.get(key)
        if locked_until and locked_until > now:
            return False, max(1, int(locked_until - now))

    return True, 0


def _record_auth_failure(action: str, request: Request, username: str = "") -> None:
    key = _auth_rate_limit_key(action, request, username)
    now = time.time()

    with _auth_attempt_lock:
        _prune_attempts(now)
        attempts = _auth_attempts.setdefault(key, [])
        attempts.append(now)
        if len(attempts) >= _RATE_LIMIT_MAX_ATTEMPTS:
            _auth_lockouts[key] = now + _RATE_LIMIT_LOCKOUT_SECONDS


def _clear_auth_failures(action: str, request: Request, username: str = "") -> None:
    key = _auth_rate_limit_key(action, request, username)
    with _auth_attempt_lock:
        _auth_attempts.pop(key, None)
        _auth_lockouts.pop(key, None)


def _set_auth_cookie(response: JSONResponse, token: str, request: Request) -> None:
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
        max_age=TOKEN_EXPIRY,
        path="/",
    )


# ============================================================
# Auth Status — 改造为返回当前用户信息
# ============================================================

@router.get("/status")
async def auth_status(request: Request, db: AsyncSession = Depends(get_db)):
    """Public auth bootstrap endpoint used by the login page."""
    is_local = _is_local_request(request)
    _, password_hash = await get_stored_credentials()
    auth_enabled = bool(password_hash)

    token = request.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

    from backend.modules.auth.utils import validate_auth_session
    authenticated = False
    user_id = None
    username = None
    role = None

    if token:
        user_id = await validate_auth_session(token, db)
        if user_id:
            user = await get_user_by_id(user_id, db)
            if user and user.is_active:
                authenticated = True
                username = user.username
                role = user.role

    bind_host = getattr(request.app.state, "bind_host", "127.0.0.1")
    remote_access_enabled = is_public_bind_host(bind_host)

    return {
        "is_local": is_local,
        "auth_enabled": auth_enabled,
        "authenticated": authenticated,
        "user_id": user_id,
        "username": username,
        "role": role,
        "remote_access_enabled": remote_access_enabled,
        "setup_allowed": not auth_enabled and (is_local or request_has_valid_remote_setup_secret(request)),
    }


# ============================================================
# Setup — 改造：创建第一个 admin 用户
# ============================================================

@router.post("/setup")
async def setup_password(data: SetPasswordRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Allow first-time password bootstrap — creates the first admin user."""
    if not _is_local_request(request) and not request_has_valid_remote_setup_secret(request):
        return JSONResponse(
            status_code=403,
            content={"detail": "首次初始化只能在本机完成", "code": "SETUP_LOCAL_ONLY"},
        )

    allowed, retry_after = _check_rate_limit("setup", request, data.username)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={"detail": f"尝试过于频繁，请 {retry_after} 秒后再试", "code": "RATE_LIMITED"},
        )

    # Check if users table already has an admin
    result = await db.execute(select(User).where(User.role == "admin"))
    existing_admins = result.scalars().all()
    if existing_admins:
        return JSONResponse(
            status_code=409,
            content={"detail": "管理员已存在，请使用登录接口或通过管理员添加新用户", "code": "ADMIN_ALREADY_EXISTS"},
        )

    valid_username, username_msg = validate_username(data.username)
    if not valid_username:
        _record_auth_failure("setup", request, data.username)
        return JSONResponse(status_code=400, content={"detail": username_msg})

    valid, msg = validate_password(data.password)
    if not valid:
        _record_auth_failure("setup", request, data.username)
        return JSONResponse(status_code=400, content={"detail": msg})

    # Check if username already exists
    existing_user = await get_user_by_username(data.username.strip(), db)
    if existing_user:
        _record_auth_failure("setup", request, data.username)
        return JSONResponse(status_code=400, content={"detail": "用户名已存在"})

    hashed = hash_password(data.password)
    user_id = await create_user(data.username.strip(), hashed, role="admin", display_name=data.username.strip(), db=db)

    # Save legacy credentials for backward compatibility during transition
    await save_credentials(data.username.strip(), hashed)

    clear_remote_setup_secret(request.app)
    _clear_auth_failures("setup", request, data.username)
    logger.info(f"Created first admin user: username={data.username.strip()}, id={user_id}")

    token = await create_auth_session(user_id, db)
    response = JSONResponse(
        content={
            "success": True,
            "message": "管理员创建成功",
            "token": token,
            "user_id": user_id,
            "username": data.username.strip(),
            "role": "admin",
        }
    )
    _set_auth_cookie(response, token, request)
    return response


# ============================================================
# Login — 改造：从 users 表验证
# ============================================================

@router.post("/login")
async def login(data: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Authenticate a user and issue a cookie-backed session."""
    allowed, retry_after = _check_rate_limit("login", request, data.username)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={"detail": f"尝试过于频繁，请 {retry_after} 秒后再试", "code": "RATE_LIMITED"},
        )

    normalized_username = data.username.strip()
    valid_username, _ = validate_username(normalized_username)
    if not valid_username:
        _record_auth_failure("login", request, normalized_username)
        return JSONResponse(status_code=401, content={"detail": "用户名或密码错误"})

    user = await get_user_by_username(normalized_username, db)
    if user is None:
        _record_auth_failure("login", request, normalized_username)
        return JSONResponse(status_code=401, content={"detail": "用户名或密码错误"})

    if not user.is_active:
        _record_auth_failure("login", request, normalized_username)
        return JSONResponse(status_code=403, content={"detail": "账号已被禁用"})

    if not verify_password(data.password, user.password_hash):
        _record_auth_failure("login", request, normalized_username)
        return JSONResponse(status_code=401, content={"detail": "用户名或密码错误"})

    # Rehash if needed
    if needs_password_rehash(user.password_hash):
        new_hash = hash_password(data.password)
        update_user(user.id, password_hash=new_hash, db=db)

    _clear_auth_failures("login", request, normalized_username)

    # Update last_login_at
    from sqlalchemy import update as sql_update
    from backend.models.user import User as UserModel
    await db.execute(
        sql_update(UserModel).where(UserModel.id == user.id).values(last_login_at=utc_now())
    )
    await db.commit()

    token = await create_auth_session(user.id, db)

    # 启动该用户的渠道实例（异步，不阻塞登录）
    channel_manager = getattr(request.app.state, "channel_manager", None)
    if channel_manager is not None:
        asyncio.ensure_future(channel_manager.start_user_channels(user.id))

    response = JSONResponse(
        content={
            "success": True,
            "message": "登录成功",
            "token": token,
            "user_id": user.id,
            "username": user.username,
            "role": user.role,
            "display_name": user.display_name,
        }
    )
    _set_auth_cookie(response, token, request)
    return response


# ============================================================
# Register — 公开注册：普通用户自行注册
# ============================================================

@router.post("/register")
async def register(data: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Public user registration — creates a regular user account."""
    allowed, retry_after = _check_rate_limit("register", request, data.username)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={"detail": f"注册过于频繁，请 {retry_after} 秒后再试", "code": "RATE_LIMITED"},
        )

    normalized_username = data.username.strip()
    valid_username, username_msg = validate_username(normalized_username)
    if not valid_username:
        _record_auth_failure("register", request, data.username)
        return JSONResponse(status_code=400, content={"detail": username_msg})

    valid, pwd_msg = validate_password(data.password)
    if not valid:
        _record_auth_failure("register", request, data.username)
        return JSONResponse(status_code=400, content={"detail": pwd_msg})

    # Check if username already exists
    existing = await get_user_by_username(normalized_username, db)
    if existing:
        _record_auth_failure("register", request, data.username)
        return JSONResponse(status_code=400, content={"detail": "用户名已存在"})

    hashed = hash_password(data.password)
    user_id = await create_user(
        normalized_username, hashed,
        role="user",
        display_name=data.display_name or normalized_username,
        db=db,
    )

    _clear_auth_failures("register", request, data.username)
    logger.info(f"Registered new user: username={normalized_username}, id={user_id}")

    token = await create_auth_session(user_id, db)
    response = JSONResponse(
        content={
            "success": True,
            "message": "注册成功",
            "token": token,
            "user_id": user_id,
            "username": normalized_username,
            "role": "user",
            "display_name": data.display_name or normalized_username,
        }
    )
    _set_auth_cookie(response, token, request)
    return response


# ============================================================
# Logout
# ============================================================

@router.post("/logout")
async def logout(request: Request, db: AsyncSession = Depends(get_db)):
    token = request.cookies.get(AUTH_COOKIE_NAME)
    user_id = None
    if token:
        from backend.modules.auth.utils import validate_auth_session
        user_id = await validate_auth_session(token, db)
        await revoke_auth_session(token, db)

    # 停止当前用户的渠道实例
    if user_id is not None:
        channel_manager = getattr(request.app.state, "channel_manager", None)
        if channel_manager is not None:
            await channel_manager.stop_user_channels(user_id)

    clear_current_user_context()
    response = JSONResponse(content={"success": True})
    response.delete_cookie(AUTH_COOKIE_NAME, path="/")
    return response


# ============================================================
# Me — 返回当前用户完整资料
# ============================================================

@router.get("/me")
async def get_current_user_info(request: Request, db: AsyncSession = Depends(get_db)):
    """Return current user's full profile."""
    from backend.modules.auth.utils import get_user_by_id

    # Get user from request.state (set by middleware)
    user = getattr(request.state, "user", None)
    if user is None:
        return JSONResponse(status_code=401, content={"detail": "未登录", "code": "NOT_AUTHENTICATED"})

    return {
        "user_id": user.id,
        "username": user.username,
        "role": user.role,
        "display_name": user.display_name,
        "avatar": getattr(user, "avatar", None),
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login_at": user.last_login_at.isoformat() if getattr(user, "last_login_at", None) else None,
    }


# ============================================================
# Change Password — 改造：按当前用户验证
# ============================================================

@router.post("/change-password")
async def change_password(data: ChangePasswordRequest, request: Request, db: AsyncSession = Depends(get_db)):
    from backend.modules.auth.utils import get_user_by_id

    # Get user from request.state (set by middleware)
    current_user = getattr(request.state, "user", None)
    if current_user is None:
        return _auth_required_response()

    allowed, retry_after = _check_rate_limit("change-password", request, current_user.username)
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={"detail": f"尝试过于频繁，请 {retry_after} 秒后再试", "code": "RATE_LIMITED"},
        )

    if not verify_password(data.old_password, current_user.password_hash):
        _record_auth_failure("change-password", request, current_user.username)
        return JSONResponse(status_code=401, content={"detail": "旧密码错误"})

    valid, msg = validate_password(data.new_password)
    if not valid:
        _record_auth_failure("change-password", request, current_user.username)
        return JSONResponse(status_code=400, content={"detail": msg})

    new_hash = hash_password(data.new_password)
    await update_user(current_user.id, password_hash=new_hash, db=db)

    # Revoke all sessions for this user
    await revoke_all_auth_sessions(db, user_id=current_user.id)

    _clear_auth_failures("change-password", request, current_user.username)
    logger.info(f"Password changed for user: id={current_user.id}, username={current_user.username}")

    return {"success": True, "message": "密码修改成功，请重新登录"}


def _auth_required_response() -> JSONResponse:
    return JSONResponse(status_code=401, content={"detail": "请先登录", "code": "AUTH_REQUIRED"})


# ============================================================
# User Management APIs (admin only)
# ============================================================

AUTH_COOKIE_NAME = "CountBot_token"


async def _get_current_user_from_request(request: Request, db):
    """从请求中提取并验证当前用户。
    由于 RemoteAuthMiddleware 对 /api/auth/* 路径跳过认证，
    用户管理端点需要自己从 cookie/header 恢复用户。
    """
    from backend.modules.auth.utils import get_user_by_id, validate_auth_session

    token = request.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        return None
    user_id = await validate_auth_session(token, db)
    if user_id is None:
        return None
    user = await get_user_by_id(user_id, db)
    return user if user and user.is_active else None


@router.post("/users")
async def create_new_user(data: CreateUserRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Create a new user — admin only."""

    try:
        admin = await _get_current_user_from_request(request, db)
        if admin is None or admin.role != "admin":
            return JSONResponse(status_code=403, content={"detail": "需要管理员权限", "code": "ADMIN_REQUIRED"})
    except HTTPException:
        return JSONResponse(status_code=403, content={"detail": "需要管理员权限", "code": "ADMIN_REQUIRED"})

    # Validate role
    if data.role not in ("admin", "operator", "user"):
        return JSONResponse(status_code=400, content={"detail": "角色必须是 admin、operator 或 user"})

    # Validate username
    valid_username, username_msg = validate_username(data.username)
    if not valid_username:
        return JSONResponse(status_code=400, content={"detail": username_msg})

    # Check duplicate
    existing = await get_user_by_username(data.username.strip(), db)
    if existing:
        return JSONResponse(status_code=400, content={"detail": "用户名已存在"})

    # Validate password
    valid, msg = validate_password(data.password)
    if not valid:
        return JSONResponse(status_code=400, content={"detail": msg})

    hashed = hash_password(data.password)
    user_id = create_user(
        data.username.strip(), hashed,
        role=data.role,
        display_name=data.display_name or data.username.strip(),
        db=db,
    )

    return {
        "success": True,
        "user_id": user_id,
        "username": data.username.strip(),
        "role": data.role,
    }


@router.get("/users")
async def list_all_users(request: Request, db: AsyncSession = Depends(get_db)):
    """List all users — admin or operator only."""

    try:
        current_user = await _get_current_user_from_request(request, db)
        if current_user is None or current_user.role not in ("admin", "operator"):
            return JSONResponse(status_code=403, content={"detail": "需要管理员或操作员权限", "code": "ADMIN_OR_OPERATOR_REQUIRED"})
    except HTTPException:
        return JSONResponse(status_code=403, content={"detail": "需要管理员或操作员权限", "code": "ADMIN_OR_OPERATOR_REQUIRED"})

    users = await list_users(db)
    return [
        {
            "id": u.id,
            "username": u.username,
            "role": u.role,
            "display_name": u.display_name,
            "avatar": u.avatar,
            "is_active": u.is_active,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
        }
        for u in users
    ]


@router.put("/users/{user_id}")
async def update_existing_user(user_id: int, data: UpdateUserRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Update a user — admin only."""

    try:
        admin = await _get_current_user_from_request(request, db)
        if admin is None or admin.role != "admin":
            return JSONResponse(status_code=403, content={"detail": "需要管理员权限", "code": "ADMIN_REQUIRED"})
    except HTTPException:
        return JSONResponse(status_code=403, content={"detail": "需要管理员权限", "code": "ADMIN_REQUIRED"})

    # Cannot modify the last admin's role to non-admin
    if data.role is not None and data.role != "admin":
        target = await get_user_by_id(user_id, db)
        if target and target.role == "admin":
            result = await db.execute(select(UserModel).where(UserModel.role == "admin"))
            admins = result.scalars().all()
            if len(admins) <= 1:
                return JSONResponse(status_code=400, content={"detail": "不能将最后一个管理员降级"})

    success = update_user(user_id, username=data.username, role=data.role,
                          display_name=data.display_name, is_active=data.is_active, db=db)
    if not success:
        return JSONResponse(status_code=404, content={"detail": "用户不存在"})

    return {"success": True, "user_id": user_id}


@router.delete("/users/{user_id}")
async def delete_existing_user(user_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """Delete a user — admin only."""

    try:
        admin = await _get_current_user_from_request(request, db)
        if admin is None or admin.role != "admin":
            return JSONResponse(status_code=403, content={"detail": "需要管理员权限", "code": "ADMIN_REQUIRED"})
    except HTTPException:
        return JSONResponse(status_code=403, content={"detail": "需要管理员权限", "code": "ADMIN_REQUIRED"})

    # Cannot delete yourself
    if user_id == admin.id:
        return JSONResponse(status_code=400, content={"detail": "不能删除自己"})

    success = delete_user(user_id, db)
    if not success:
        return JSONResponse(status_code=404, content={"detail": "用户不存在或无法删除"})

    return {"success": True, "user_id": user_id}


# ============================================================
# User Switch (sudo mode) — admin only
# ============================================================

@router.post("/switch")
async def switch_user(target_user_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """Switch to another user's context (sudo mode) — admin only."""

    try:
        admin = getattr(request.state, "user", None)
        if admin is None or admin.role != "admin":
            return JSONResponse(status_code=403, content={"detail": "需要管理员权限", "code": "ADMIN_REQUIRED"})
    except HTTPException:
        return JSONResponse(status_code=403, content={"detail": "需要管理员权限", "code": "ADMIN_REQUIRED"})

    target = await get_user_by_id(target_user_id, db)
    if target is None:
        return JSONResponse(status_code=404, content={"detail": "用户不存在"})
    if not target.is_active:
        return JSONResponse(status_code=400, content={"detail": "目标用户已被禁用"})
    if target.id == admin.id:
        return JSONResponse(status_code=400, content={"detail": "已经是该用户"})

    # Create a switch token (separate from normal auth token)
    import secrets
    switch_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(switch_token.encode("utf-8")).hexdigest()

    # Store switch info in settings for now (could be a separate table)
    switch_payload = json.dumps({
        "original_user_id": admin.id,
        "target_user_id": target_user_id,
        "created_at": time.time(),
    })
    switch_key = f"auth.switch.{token_hash}"
    setting = Setting(key=switch_key, value=switch_payload, updated_at=utc_now())
    db.add(setting)
    db.commit()

    logger.info(f"User switch: admin={admin.id} -> target={target_user_id}")

    response = JSONResponse(
        content={
            "success": True,
            "message": f"已切换至用户: {target.username}",
            "switch_token": switch_token,
            "target_user_id": target_user_id,
            "target_username": target.username,
            "target_role": target.role,
        }
    )
    # Set a special switch cookie
    response.set_cookie(
        key="CountBot_switch_token",
        value=switch_token,
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
        max_age=TOKEN_EXPIRY,
        path="/",
    )
    return response


@router.delete("/switch")
async def exit_switch(request: Request, db: AsyncSession = Depends(get_db)):
    """Exit user switch and return to original admin."""
    switch_token = request.cookies.get("CountBot_switch_token")
    if not switch_token:
        return JSONResponse(status_code=400, content={"detail": "没有活动的用户切换"})

    token_hash = hashlib.sha256(switch_token.encode("utf-8")).hexdigest()
    switch_key = f"auth.switch.{token_hash}"
    result = await db.execute(select(Setting).where(Setting.key == switch_key))
    switch_row = result.scalar_one_or_none()

    if switch_row is None:
        return JSONResponse(status_code=400, content={"detail": "用户切换已过期"})

    switch_data = json.loads(switch_row.value)
    original_user_id = switch_data["original_user_id"]

    # Delete switch record
    db.delete(switch_row)
    await db.commit()

    # Create new session for original user
    original_user = await get_user_by_id(original_user_id, db)
    if original_user:
        token = await create_auth_session(original_user.id, db)
        response = JSONResponse(content={"success": True, "message": "已返回管理员身份"})
        response.set_cookie(
            key=AUTH_COOKIE_NAME,
            value=token,
            httponly=True,
            samesite="strict",
            secure=request.url.scheme == "https",
            max_age=TOKEN_EXPIRY,
            path="/",
        )
        response.delete_cookie("CountBot_switch_token", path="/")
        return response

    return JSONResponse(status_code=400, content={"detail": "无法恢复原用户"})


# Import User model for type hints
from backend.models.user import User as UserModel
import hashlib
