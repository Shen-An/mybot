"""用户渠道配置模型 — 多用户隔离"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, Integer, String, JSON, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship

from backend.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UserChannelConfig(Base):
    """用户级别的渠道配置，实现多用户渠道配置隔离。"""

    __tablename__ = "user_channel_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    channel = Column(String(50), nullable=False, index=True)  # telegram, discord, qq, wechat, dingtalk, feishu, weibo, wecom, xiaozhi
    account_id = Column(String(100), nullable=False, default="default")  # 机器人账号 ID
    config_json = Column(JSON, nullable=False, default=dict)  # 渠道账号的完整配置
    is_enabled = Column(Integer, default=0)  # 是否启用（0=禁用，1=启用）
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    # 关联用户
    user = relationship("User", back_populates="channel_configs")

    __table_args__ = (
        Index("idx_user_channel_account", "user_id", "channel", "account_id", unique=True),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "channel": self.channel,
            "account_id": self.account_id,
            "config": self.config_json,
            "is_enabled": bool(self.is_enabled),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
