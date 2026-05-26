"""CurrentUser 依赖注入 — 多用户认证上下文"""

import hashlib
import json
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.modules.auth.utils import validate_auth_session


async def get_current_user_id(request: Request) -> int:
    """从 request.state 获取当前用户 ID（由 middleware 设置）"""
    user_id = getattr(request.state, "user_id", None)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return user_id


async def get_effective_user_id(request: Request, db: AsyncSession = Depends(get_db)) -> int:
    """获取有效用户 ID（支持管理员模拟切换）。

    当管理员使用 CountBot_switch_token 模拟其他用户时，返回被模拟用户的 ID。
    否则返回当前认证用户的 ID（与 get_current_user_id 一致）。
    """
    real_user_id = await get_current_user_id(request)

    switch_token = request.cookies.get("CountBot_switch_token")
    if not switch_token:
        return real_user_id

    try:
        token_hash = hashlib.sha256(switch_token.encode("utf-8")).hexdigest()
        switch_key = f"auth.switch.{token_hash}"

        from backend.models.setting import Setting

        result = await db.execute(select(Setting).where(Setting.key == switch_key))
        setting = result.scalar_one_or_none()
        if setting is None:
            return real_user_id

        switch_data = json.loads(setting.value)
        target_user_id = switch_data.get("target_user_id")
        if target_user_id is None:
            return real_user_id

        return int(target_user_id)
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        return real_user_id


async def get_current_user(user_id: int = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    """获取当前用户完整对象"""
    from backend.models.user import User

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is deactivated")

    return user


async def get_current_active_user(current_user = Depends(get_current_user)):
    """确保用户已激活"""
    return current_user


async def get_current_admin_user(current_user = Depends(get_current_active_user)):
    """确保用户是 admin"""
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required")
    return current_user


async def get_current_admin_or_operator_user(current_user = Depends(get_current_active_user)):
    """确保用户是 admin 或 operator"""
    if current_user.role not in ("admin", "operator"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin or operator privileges required")
    return current_user


# 兼容旧代码：对于尚未改造的端点，提供 validate_session 的异步版本
async def get_current_user_from_token(request: Request, db: AsyncSession = Depends(get_db)) -> int:
    """从 cookie/header 中的 token 验证用户 ID（用于尚未改造 request.state 的端点）"""
    from backend.modules.auth.middleware import _extract_token_from_request

    token = _extract_token_from_request(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    user_id = await validate_auth_session(token, db)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    return user_id
