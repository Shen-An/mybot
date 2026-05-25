"""Authentication helpers for password hashing and multi-user auth sessions."""

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from datetime import datetime, timezone
from typing import Optional, Tuple

from loguru import logger
from sqlalchemy import select

TOKEN_EXPIRY = 86400

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_KEY_LEN = 32
_USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.@-]{3,32}$")


def validate_password(password: str) -> Tuple[bool, str]:
    """Validate password strength."""
    if len(password) < 8:
        return False, "密码至少8位"

    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)

    if not (has_upper and has_lower and has_digit):
        return False, "密码必须同时包含大写字母、小写字母和数字"

    return True, ""


def validate_username(username: str) -> Tuple[bool, str]:
    """Validate administrator username format."""
    normalized = username.strip()
    if not _USERNAME_PATTERN.fullmatch(normalized):
        return False, "账号只能包含字母、数字、点、下划线、@ 和中划线，长度 3-32 位"

    return True, ""


def _b64encode(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"))


def _legacy_sha256_hash(password: str) -> str:
    salt = secrets.token_hex(16)
    hashed = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
    return f"{salt}:{hashed}"


def hash_password(password: str) -> str:
    """Hash password with scrypt."""
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_KEY_LEN,
    )
    return "$".join(
        [
            "scrypt",
            str(_SCRYPT_N),
            str(_SCRYPT_R),
            str(_SCRYPT_P),
            _b64encode(salt),
            _b64encode(derived),
        ]
    )


def verify_password(password: str, stored_hash: str) -> bool:
    """Check whether the password matches the stored hash."""
    if not stored_hash:
        return False

    if stored_hash.startswith("scrypt$"):
        parts = stored_hash.split("$")
        if len(parts) != 6:
            return False

        _, n_value, r_value, p_value, salt_b64, expected_b64 = parts
        try:
            derived = hashlib.scrypt(
                password.encode("utf-8"),
                salt=_b64decode(salt_b64),
                n=int(n_value),
                r=int(r_value),
                p=int(p_value),
                dklen=_SCRYPT_KEY_LEN,
            )
        except (ValueError, TypeError):
            return False

        return hmac.compare_digest(_b64encode(derived), expected_b64)

    # Backward compatibility for legacy SHA-256 hashes.
    if ":" in stored_hash:
        salt, expected_hash = stored_hash.split(":", 1)
        actual_hash = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
        return hmac.compare_digest(actual_hash, expected_hash)

    return False


def needs_password_rehash(stored_hash: str) -> bool:
    """Return whether the stored password hash should be upgraded."""
    return not stored_hash.startswith("scrypt$")


def _token_hash(token: str) -> str:
    """SHA256 hash a token for storage as primary key."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def utc_now():
    """返回带时区的UTC时间"""
    return datetime.now(timezone.utc)


def _utcnow_naive():
    """返回不带时区的UTC时间 — 用于与SQLite存储值比较"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ============================================================
# 新：基于 auth_sessions 表的会话管理（多用户）
# ============================================================

async def create_auth_session(user_id: int, db) -> str:
    """Create a new auth session for a user. Writes to auth_sessions table."""
    from backend.models.auth_session import AuthSession

    token = secrets.token_urlsafe(32)
    token_hash = _token_hash(token)
    expires_at = datetime.utcfromtimestamp(time.time() + TOKEN_EXPIRY)

    auth_session = AuthSession(
        token_hash=token_hash,
        user_id=user_id,
        created_at=utc_now(),
        expires_at=expires_at,
    )
    db.add(auth_session)
    await db.commit()

    await _cleanup_auth_sessions(db)
    logger.info(f"AUTH 会话已创建: user_id={user_id}")
    return token


async def validate_auth_session(token: str, db) -> Optional[int]:
    """Validate a session token and return the user_id when valid."""
    if not token:
        return None

    from backend.models.auth_session import AuthSession

    token_hash = _token_hash(token)
    result = await db.execute(select(AuthSession).where(AuthSession.token_hash == token_hash))
    session = result.scalar_one_or_none()

    if session is None:
        return None

    if _utcnow_naive() > session.expires_at:
        db.delete(session)
        await db.commit()
        return None

    return session.user_id


async def revoke_auth_session(token: str, db) -> bool:
    """Revoke a single auth session."""
    if not token:
        return False

    from backend.models.auth_session import AuthSession

    token_hash = _token_hash(token)
    result = await db.execute(select(AuthSession).where(AuthSession.token_hash == token_hash))
    session = result.scalar_one_or_none()

    if session is None:
        return False

    await db.delete(session)
    await db.commit()
    return True


async def revoke_all_auth_sessions(db, user_id: Optional[int] = None) -> int:
    """Revoke all sessions, or all sessions owned by one user."""
    from backend.models.auth_session import AuthSession

    removed = 0
    now = _utcnow_naive()

    query = select(AuthSession)
    if user_id is not None:
        query = query.where(AuthSession.user_id == user_id)

    result = await db.execute(query)
    for session in result.scalars().all():
        if now > session.expires_at:
            db.delete(session)
            removed += 1
            continue
        db.delete(session)
        removed += 1

    if removed:
        await db.commit()

    return removed


async def _cleanup_auth_sessions(db) -> None:
    """Remove expired auth sessions and legacy settings entries."""
    from backend.models.auth_session import AuthSession
    from backend.models.setting import Setting

    now = _utcnow_naive()
    result = await db.execute(select(AuthSession).where(AuthSession.expires_at < now))
    for session in result.scalars().all():
        await db.delete(session)

    # Also clean up legacy settings table for auth.session.* keys
    legacy_result = await db.execute(select(Setting).where(Setting.key.like("auth.session.%")))
    for setting in legacy_result.scalars().all():
        db.delete(setting)

    await db.commit()


# ============================================================
# 新：用户 CRUD 操作
# ============================================================

async def get_user_by_username(username: str, db):
    """Get user by username."""
    from backend.models.user import User
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def get_user_by_id(user_id: int, db):
    """Get user by ID."""
    from backend.models.user import User
    return await db.get(User, user_id)


async def create_user(username: str, password_hash: str, role: str = "user", display_name: Optional[str] = None, db=None) -> int:
    """Create a new user. Returns user_id."""
    from backend.models.user import User

    user = User(
        username=username,
        password_hash=password_hash,
        role=role,
        display_name=display_name or username,
        is_active=True,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info(f"Created user: username={username}, id={user.id}, role={role}")
    return user.id


async def update_user(user_id: int, username: Optional[str] = None, password_hash: Optional[str] = None,
                role: Optional[str] = None, display_name: Optional[str] = None,
                is_active: Optional[bool] = None, db=None) -> bool:
    """Update user fields. Returns True if updated."""
    from backend.models.user import User

    user = await db.get(User, user_id)
    if user is None:
        return False

    if username is not None:
        user.username = username
    if password_hash is not None:
        user.password_hash = password_hash
    if role is not None:
        user.role = role
    if display_name is not None:
        user.display_name = display_name
    if is_active is not None:
        user.is_active = is_active
    user.updated_at = utc_now()

    await db.commit()
    logger.info(f"Updated user: id={user_id}")
    return True


async def delete_user(user_id: int, db) -> bool:
    """Delete a user. Returns True if deleted."""
    from backend.models.user import User

    user = await db.get(User, user_id)
    if user is None:
        return False

    # Cannot delete the last admin
    if user.role == "admin":
        result = await db.execute(select(User).where(User.role == "admin"))
        admins = result.scalars().all()
        if len(admins) <= 1:
            logger.warning(f"Cannot delete the last admin user: id={user_id}")
            return False

    await db.delete(user)
    await db.commit()
    logger.info(f"Deleted user: id={user_id}")
    return True


async def list_users(db):
    """List all users."""
    from backend.models.user import User
    result = await db.execute(select(User).order_by(User.id))
    return result.scalars().all()
