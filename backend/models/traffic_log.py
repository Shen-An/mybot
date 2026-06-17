"""流量日志模型 — 记录每个用户每天的上传/下载流量"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


def utc_now():
    return datetime.now(timezone.utc)


class TrafficLog(Base):
    """用户每日流量统计"""

    __tablename__ = "traffic_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    upload_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    download_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        UniqueConstraint("user_id", "date", name="uq_traffic_user_date"),
    )
