"""Admin API 端点 — 管理面板后端"""

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from loguru import logger
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.message import Message
from backend.models.session import Session
from backend.models.setting import Setting
from backend.models.traffic_log import TrafficLog
from backend.models.user import User

router = APIRouter(prefix="/api/admin", tags=["admin"])

AUTH_COOKIE_NAME = "CountBot_token"


async def _require_admin(request: Request, db):
    """验证当前请求是管理员，返回 user 对象或 403 响应。"""
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        return None

    from backend.modules.auth.utils import get_user_by_id, validate_auth_session

    user_id = await validate_auth_session(token, db)
    if user_id is None:
        return None
    user = await get_user_by_id(user_id, db)
    if user and user.is_active and user.role == "admin":
        return user
    return None


# ============================================================
# 消息查询
# ============================================================


@router.get("/messages")
async def get_admin_messages(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user_id: Optional[int] = Query(None, description="筛选用户 ID"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """获取所有消息（分页，支持按用户筛选）— 仅管理员"""
    admin = await _require_admin(request, db)
    if admin is None:
        return JSONResponse(status_code=403, content={"detail": "需要管理员权限"})

    base_query = (
        select(
            Message.id,
            Message.session_id,
            Message.role,
            Message.content,
            Message.created_at,
            Session.user_id,
            User.username,
        )
        .join(Session, Message.session_id == Session.id)
        .join(User, Session.user_id == User.id)
    )

    count_query = select(func.count()).select_from(
        Message.__table__.join(Session).join(User)
    )

    if user_id is not None and user_id > 0:
        base_query = base_query.where(Session.user_id == user_id)
        count_query = count_query.where(Session.user_id == user_id)

    total = (await db.execute(count_query)).scalar() or 0

    rows = (
        await db.execute(
            base_query.order_by(Message.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()

    messages = []
    for row in rows:
        messages.append({
            "id": row.id,
            "session_id": row.session_id,
            "role": row.role,
            "content": row.content[:500] if row.content else "",
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "user_id": row.user_id,
            "username": row.username,
        })

    return {"total": total, "messages": messages, "limit": limit, "offset": offset}


# ============================================================
# 流量统计
# ============================================================


@router.get("/traffic")
async def get_admin_traffic(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user_id: Optional[int] = Query(None, description="筛选用户 ID"),
    days: int = Query(7, ge=1, le=365),
):
    """获取流量统计数据 — 仅管理员"""
    admin = await _require_admin(request, db)
    if admin is None:
        return JSONResponse(status_code=403, content={"detail": "需要管理员权限"})

    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    # 按用户汇总
    user_query = select(
        TrafficLog.user_id,
        func.sum(TrafficLog.upload_bytes).label("total_upload"),
        func.sum(TrafficLog.download_bytes).label("total_download"),
        func.sum(TrafficLog.request_count).label("total_requests"),
    ).where(TrafficLog.date >= since)

    if user_id is not None and user_id > 0:
        user_query = user_query.where(TrafficLog.user_id == user_id)

    user_rows = (
        await db.execute(
            user_query.group_by(TrafficLog.user_id).order_by(
                func.sum(TrafficLog.upload_bytes + TrafficLog.download_bytes).desc()
            )
        )
    ).all()

    by_user = []
    for row in user_rows:
        # 获取用户名
        u = await db.get(User, row.user_id)
        by_user.append({
            "user_id": row.user_id,
            "username": u.username if u else f"用户{row.user_id}",
            "upload_bytes": row.total_upload or 0,
            "download_bytes": row.total_download or 0,
            "total_bytes": (row.total_upload or 0) + (row.total_download or 0),
            "request_count": row.total_requests or 0,
        })

    # 按日汇总
    daily_query = select(
        TrafficLog.date,
        func.sum(TrafficLog.upload_bytes).label("upload_bytes"),
        func.sum(TrafficLog.download_bytes).label("download_bytes"),
        func.sum(TrafficLog.request_count).label("request_count"),
    ).where(TrafficLog.date >= since)

    if user_id is not None and user_id > 0:
        daily_query = daily_query.where(TrafficLog.user_id == user_id)

    daily_rows = (
        await db.execute(
            daily_query.group_by(TrafficLog.date).order_by(TrafficLog.date)
        )
    ).all()

    daily = []
    for row in daily_rows:
        daily.append({
            "date": row.date,
            "upload_bytes": row.upload_bytes or 0,
            "download_bytes": row.download_bytes or 0,
            "total_bytes": (row.upload_bytes or 0) + (row.download_bytes or 0),
            "request_count": row.request_count or 0,
        })

    # 总计
    totals = {
        "upload_bytes": sum(u["upload_bytes"] for u in by_user),
        "download_bytes": sum(u["download_bytes"] for u in by_user),
        "total_bytes": sum(u["total_bytes"] for u in by_user),
        "request_count": sum(u["request_count"] for u in by_user),
    }

    return {"totals": totals, "by_user": by_user, "daily": daily}


# ============================================================
# 用户统计
# ============================================================


@router.get("/users/count")
async def get_user_count(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """获取用户统计数据 — 仅管理员"""
    admin = await _require_admin(request, db)
    if admin is None:
        return JSONResponse(status_code=403, content={"detail": "需要管理员权限"})

    total = (await db.execute(select(func.count(User.id)))).scalar() or 0
    active = (
        await db.execute(
            select(func.count(User.id)).where(User.is_active == True)  # noqa: E712
        )
    ).scalar() or 0

    return {"total_users": total, "active_users": active}


# ============================================================
# 管理设置
# ============================================================


@router.get("/settings")
async def get_admin_settings(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """读取管理设置 — 仅管理员"""
    admin = await _require_admin(request, db)
    if admin is None:
        return JSONResponse(status_code=403, content={"detail": "需要管理员权限"})

    result = await db.execute(
        select(Setting).where(Setting.key == "admin.config")
    )
    setting = result.scalar_one_or_none()
    config = json.loads(setting.value) if setting else {}

    return {
        "max_users": config.get("max_users", 0),
    }


@router.post("/settings")
async def save_admin_settings(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """保存管理设置 — 仅管理员"""
    admin = await _require_admin(request, db)
    if admin is None:
        return JSONResponse(status_code=403, content={"detail": "需要管理员权限"})

    body = await request.json()
    max_users = int(body.get("max_users", 0))
    if max_users < 0:
        return JSONResponse(status_code=400, content={"detail": "max_users 不能小于 0"})

    config = {"max_users": max_users}

    result = await db.execute(
        select(Setting).where(Setting.key == "admin.config")
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.value = json.dumps(config)
    else:
        db.add(Setting(key="admin.config", value=json.dumps(config)))

    await db.commit()
    logger.info(f"Admin settings updated: max_users={max_users}")

    return {"success": True, "max_users": max_users}


# ============================================================
# 注册限制检查 — 供注册端点调用
# ============================================================


async def check_registration_allowed(db) -> tuple[bool, str]:
    """检查是否允许新用户注册。返回 (允许, 错误消息)。"""
    result = await db.execute(
        select(Setting).where(Setting.key == "admin.config")
    )
    setting = result.scalar_one_or_none()
    if not setting:
        return True, ""

    config = json.loads(setting.value)
    max_users = config.get("max_users", 0)
    if max_users <= 0:
        return True, ""

    current = (await db.execute(select(func.count(User.id)))).scalar() or 0
    if current >= max_users:
        return False, f"用户数量已达上限（{max_users}），请联系管理员"

    return True, ""
