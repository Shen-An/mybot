"""认证会话模型 — 替代 settings 表中的会话存储"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


def utc_now():
    """返回带时区的UTC时间"""
    return datetime.now(timezone.utc)


class AuthSession(Base):
    """认证会话表 — 存储用户登录令牌"""

    __tablename__ = "auth_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)  # SHA256(token)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # 反向关系
    user: Mapped["User"] = relationship("User", back_populates="auth_sessions")
