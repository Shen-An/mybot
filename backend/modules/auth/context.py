"""用户上下文传播 — ContextVars 用于非 HTTP 层（WebSocket、工具执行等）"""

import contextvars
from typing import Optional

# 当前用户 ID（由 middleware 或 WebSocket 认证设置）
current_user_id: contextvars.ContextVar[Optional[int]] = contextvars.ContextVar("current_user_id", default=None)

# 当前用户名
current_username: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("current_username", default=None)

# 当前用户角色
current_user_role: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("current_user_role", default=None)


def set_current_user_context(user_id: int, username: str, role: str = "user") -> None:
    """设置当前用户上下文（由 middleware 或 WebSocket 认证调用）"""
    current_user_id.set(user_id)
    current_username.set(username)
    current_user_role.set(role)


def clear_current_user_context() -> None:
    """清除当前用户上下文"""
    current_user_id.set(None)
    current_username.set(None)
    current_user_role.set(None)
