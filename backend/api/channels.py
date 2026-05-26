"""渠道管理 API 端点 — 多用户隔离版本"""

import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update as sql_update, delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from backend.database import AsyncSessionLocal, get_db, get_db_session_factory
from backend.models.user_channel_config import UserChannelConfig
from backend.models.user import User as UserModel
from backend.modules.config.loader import config_loader
from backend.modules.channels.manager import ChannelManager
from backend.modules.external_agents.registry import ExternalAgentRegistry
from backend.modules.auth.dependencies import get_current_user_id, get_effective_user_id


router = APIRouter(prefix="/api/channels", tags=["channels"])


# ============================================================
# Request/Response Models
# ============================================================

class ChannelConfigUpdate(BaseModel):
    """渠道配置更新请求"""
    channel: str
    account_id: str = Field(default="default", description="机器人账号 ID")
    config: Dict[str, Any]
    is_enabled: bool = Field(default=False, description="是否启用该账号")


class ChannelTestRequest(BaseModel):
    """渠道测试请求"""
    channel: str
    account_id: str = Field(default="default")
    config: Optional[Dict[str, Any]] = None  # 可选的临时配置


class ChannelListResponse(BaseModel):
    """渠道列表响应项"""
    channel: str
    name: str
    enabled: bool
    accounts: List[Dict[str, Any]]


class UserChannelConfigCreate(BaseModel):
    """创建/更新用户渠道配置请求"""
    channel: str
    account_id: str = Field(default="default")
    config: Dict[str, Any]
    is_enabled: bool = False


class UserChannelConfigResponse(BaseModel):
    """用户渠道配置响应"""
    id: int
    channel: str
    account_id: str
    config: Dict[str, Any]
    is_enabled: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ============================================================
# Helper Functions
# ============================================================

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _mask_channel_secret(key: str, value: Any) -> Any:
    """掩码敏感字段"""
    if value is None:
        return value
    lowered = key.lower()
    if lowered in {"token", "secret", "app_secret", "client_secret", "bot_id"}:
        text = str(value)
        if not text:
            return ""
        if lowered == "bot_id":
            return text[:8] + "..."
        if lowered == "token":
            return text[:10] + "..."
        return "***"
    if lowered in {"app_id", "client_id"}:
        text = str(value)
        return text[:8] + "..." if text else ""
    return value


def _normalize_accounts_payload(config_dict: Dict[str, Any]) -> Dict[str, Any]:
    """标准化多机器人账号配置"""
    normalized = dict(config_dict)
    accounts = normalized.get("accounts", {}) or {}
    normalized["accounts"] = {
        str(account_id): {
            **dict(account_cfg),
            "account_id": str(account_id),
        }
        for account_id, account_cfg in accounts.items()
    }
    return normalized


def _validate_duplicate_accounts(channel_name: str, accounts: Dict[str, Any]) -> None:
    """校验多机器人配置中是否复用了同一物理机器人身份"""
    _CHANNEL_UNIQUE_ID_FIELDS: Dict[str, tuple] = {
        "telegram": ("token",),
        "discord": ("token",),
        "qq": ("app_id",),
        "wechat": ("login_bot_id",),
        "dingtalk": ("client_id",),
        "feishu": ("app_id",),
        "weibo": ("app_id",),
        "wecom": ("bot_id",),
    }

    unique_fields = _CHANNEL_UNIQUE_ID_FIELDS.get(channel_name)
    if not unique_fields:
        return

    seen: Dict[str, str] = {}
    for account_id, account_cfg in accounts.items():
        signature_parts = []
        for field in unique_fields:
            value = str(account_cfg.get(field) or "").strip()
            if value:
                signature_parts.append(f"{field}={value}")
        if not signature_parts:
            continue
        signature = "|".join(signature_parts)
        if signature in seen:
            raise ValueError(
                f"检测到重复机器人配置：账号 '{account_id}' 与 '{seen[signature]}' "
                f"使用相同的 {', '.join(unique_fields)}。同一个物理机器人不能重复配置为多个账号。"
            )
        seen[signature] = account_id


def _validate_external_coding_route_config(channel_name: str, accounts: Dict[str, Any], workspace: Path) -> None:
    """校验渠道账号的外部编程工具路由配置"""
    registry = ExternalAgentRegistry(workspace=workspace)

    for account_id, account_cfg in accounts.items():
        route_mode = str(account_cfg.get("routing_mode", "ai") or "ai").strip().lower()
        if route_mode not in {"ai", "direct"}:
            raise ValueError(
                f"{channel_name} 渠道账号 '{account_id}' 的路由模式无效: {route_mode}"
            )

        profile_name = str(account_cfg.get("external_coding_profile", "") or "").strip()
        if route_mode == "direct" and not profile_name:
            raise ValueError(
                f"{channel_name} 渠道账号 '{account_id}' 处于直通模式时，必须设置默认外部编程工具。"
            )

        if profile_name:
            try:
                registry.resolve_profile(profile_name)
            except Exception as exc:
                raise ValueError(
                    f"{channel_name} 渠道账号 '{account_id}' 的外部编程工具不可用: {exc}"
                ) from exc


async def _get_current_user_id(request: Request, db: AsyncSession = Depends(get_db)) -> int:
    """获取当前用户 ID（支持管理员模拟切换 -> 返回被模拟用户的 ID）"""
    return await get_effective_user_id(request, db)


async def _is_admin(request: Request, db: AsyncSession = Depends(get_db)) -> bool:
    """检查当前用户是否为管理员"""
    try:
        user_id = await get_current_user_id(request=request)
        user = await db.get(UserModel, user_id)
        return user is not None and user.role == "admin"
    except HTTPException:
        return False


async def _get_user_channel_configs(
    user_id: int,
    channel: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
) -> List[UserChannelConfig]:
    """获取指定用户的渠道配置"""
    stmt = select(UserChannelConfig).where(UserChannelConfig.user_id == user_id)
    if channel:
        stmt = stmt.where(UserChannelConfig.channel == channel)
    result = await db.execute(stmt.order_by(UserChannelConfig.channel, UserChannelConfig.account_id))
    return result.scalars().all()


async def _get_user_channel_config(
    user_id: int,
    channel: str,
    account_id: str,
    db: AsyncSession = Depends(get_db)
) -> Optional[UserChannelConfig]:
    """获取指定用户的单个渠道配置"""
    stmt = select(UserChannelConfig).where(
        UserChannelConfig.user_id == user_id,
        UserChannelConfig.channel == channel,
        UserChannelConfig.account_id == account_id
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# ============================================================
# Channel Manager (全局，用于连接测试和运行)
# ============================================================

_channel_manager: Optional[ChannelManager] = None


def set_channel_manager(manager: ChannelManager):
    global _channel_manager
    _channel_manager = manager


def get_channel_manager() -> ChannelManager:
    if _channel_manager is None:
        raise HTTPException(status_code=500, detail="Channel manager not initialized")
    return _channel_manager


# ============================================================
# Public API: List all channels (aggregated from all users)
# ============================================================

@router.get("/list")
async def list_channels(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """获取所有渠道列表（聚合所有用户的配置）"""
    try:
        current_user_id = await _get_current_user_id(request, db)
        is_admin_user = await _is_admin(request, db)

        # 获取当前用户的所有渠道配置
        user_configs = await _get_user_channel_configs(current_user_id, db=db)

        # 管理员可以查看所有用户的配置
        if is_admin_user:
            all_configs_result = await db.execute(select(UserChannelConfig))
            all_configs = all_configs_result.scalars().all()
        else:
            all_configs = user_configs

        # 按渠道聚合
        channels_by_name: Dict[str, List[UserChannelConfig]] = {}
        for cfg in all_configs:
            if cfg.channel not in channels_by_name:
                channels_by_name[cfg.channel] = []
            channels_by_name[cfg.channel].append(cfg)

        # 构建响应
        channel_names = {
            "telegram": "Telegram",
            "discord": "Discord",
            "qq": "QQ",
            "wechat": "微信",
            "dingtalk": "钉钉",
            "feishu": "飞书",
            "weibo": "微博",
            "wecom": "企业微信",
            "xiaozhi": "小智AI",
        }

        available_channels = {}
        for channel_name, display_name in channel_names.items():
            configs = channels_by_name.get(channel_name, [])
            accounts = []
            for cfg in configs:
                # 掩码敏感信息
                masked_config = {k: _mask_channel_secret(k, v) for k, v in cfg.config_json.items()}
                accounts.append({
                    "account_id": cfg.account_id,
                    "is_enabled": cfg.is_enabled,
                    "config": masked_config,
                })

            enabled = any(acc["is_enabled"] for acc in accounts)

            available_channels[channel_name] = {
                "name": display_name,
                "description": f"{display_name} 消息平台",
                "icon": channel_name,
                "enabled": enabled,
                "configured": len(accounts) > 0,
                "accounts": accounts,
            }

        return {
            "success": True,
            "channels": available_channels,
            "current_user_id": current_user_id,
            "is_admin": is_admin_user,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing channels: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# User-scoped API: Get my channel configs
# ============================================================

@router.get("/my/configs")
async def get_my_channel_configs(
    request: Request,
    channel: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """获取当前用户的渠道配置"""
    try:
        current_user_id = await _get_current_user_id(request, db)
        configs = await _get_user_channel_configs(current_user_id, channel=channel, db=db)

        return {
            "success": True,
            "user_id": current_user_id,
            "configs": [cfg.to_dict() for cfg in configs],
        }

    except Exception as e:
        logger.error(f"Error getting user channel configs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/my/{channel}/config")
async def get_my_channel_config(
    request: Request,
    channel: str,
    account_id: str = "default",
    db: AsyncSession = Depends(get_db)
):
    """获取当前用户的指定渠道配置"""
    try:
        current_user_id = await _get_current_user_id(request, db)
        config = await _get_user_channel_config(current_user_id, channel, account_id, db=db)

        if config is None:
            # 返回空配置模板
            return {
                "success": True,
                "channel": channel,
                "account_id": account_id,
                "config": {},
                "is_enabled": False,
                "exists": False,
            }

        return {
            "success": True,
            "channel": channel,
            "account_id": config.account_id,
            "config": config.config_json,
            "is_enabled": config.is_enabled,
            "exists": True,
            "id": config.id,
        }

    except Exception as e:
        logger.error(f"Error getting user channel config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# User-scoped API: Create/Update my channel config
# ============================================================

@router.post("/my/config")
async def save_my_channel_config(
    data: UserChannelConfigCreate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """保存当前用户的渠道配置（创建或更新）"""
    try:
        current_user_id = await _get_current_user_id(request, db)

        # 验证 channel
        valid_channels = ["telegram", "discord", "qq", "wechat", "dingtalk", "feishu", "weibo", "wecom", "xiaozhi"]
        if data.channel not in valid_channels:
            raise HTTPException(status_code=400, detail=f"不支持的渠道: {data.channel}")

        # 标准化配置
        config_dict = _normalize_accounts_payload(data.config)

        # 校验重复账号
        accounts = config_dict.get("accounts", {}) or {data.account_id: config_dict}
        _validate_duplicate_accounts(data.channel, accounts)

        # 校验外部编程工具路由
        workspace = Path(config_loader.config.workspace.path).resolve()
        workspace.mkdir(parents=True, exist_ok=True)
        _validate_external_coding_route_config(data.channel, accounts, workspace)

        # 查找或创建配置记录
        existing = await _get_user_channel_config(current_user_id, data.channel, data.account_id, db=db)

        if existing:
            # 更新
            existing.config_json = config_dict
            existing.is_enabled = 1 if data.is_enabled else 0
            existing.updated_at = utc_now()
            db.add(existing)
            logger.info(f"Updated channel config: user_id={current_user_id}, channel={data.channel}, account={data.account_id}")
            result_id = existing.id
        else:
            # 创建
            new_config = UserChannelConfig(
                user_id=current_user_id,
                channel=data.channel,
                account_id=data.account_id,
                config_json=config_dict,
                is_enabled=1 if data.is_enabled else 0,
            )
            db.add(new_config)
            logger.info(f"Created channel config: user_id={current_user_id}, channel={data.channel}, account={data.account_id}")
            result_id = new_config.id

        await db.commit()

        # 热更新渠道管理器
        await _restart_channel_manager_if_needed(request)

        return {
            "success": True,
            "message": "保存成功",
            "config_id": result_id,
        }

    except HTTPException:
        raise
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        await db.rollback()
        logger.error(f"Error saving channel config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# User-scoped API: Delete my channel config
# ============================================================

@router.delete("/my/{channel}/config/{account_id}")
async def delete_my_channel_config(
    request: Request,
    channel: str,
    account_id: str,
    db: AsyncSession = Depends(get_db)
):
    """删除当前用户的指定渠道配置"""
    try:
        current_user_id = await _get_current_user_id(request, db)

        config = await _get_user_channel_config(current_user_id, channel, account_id, db=db)
        if config is None:
            raise HTTPException(status_code=404, detail="配置不存在")

        await db.execute(
            sql_delete(UserChannelConfig).where(
                UserChannelConfig.id == config.id
            )
        )
        await db.commit()

        logger.info(f"Deleted channel config: user_id={current_user_id}, channel={channel}, account={account_id}")

        # 热更新渠道管理器
        await _restart_channel_manager_if_needed(request)

        return {
            "success": True,
            "message": "删除成功",
        }

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting channel config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Admin API: Manage any user's channel configs
# ============================================================

@router.get("/admin/users/{user_id}/configs")
async def get_user_configs(
    user_id: int,
    request: Request,
    channel: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """管理员：获取指定用户的渠道配置"""
    try:
        admin = await _require_admin(request, db)

        # 验证用户存在
        user = await db.get(UserModel, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="用户不存在")

        configs = await _get_user_channel_configs(user_id, channel=channel, db=db)

        return {
            "success": True,
            "user_id": user_id,
            "username": user.username,
            "configs": [cfg.to_dict() for cfg in configs],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user configs (admin): {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/users/{user_id}/config")
async def save_user_config(
    user_id: int,
    data: UserChannelConfigCreate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """管理员：保存指定用户的渠道配置"""
    try:
        admin = await _require_admin(request, db)

        # 验证用户存在
        user = await db.get(UserModel, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="用户不存在")

        # 验证 channel
        valid_channels = ["telegram", "discord", "qq", "wechat", "dingtalk", "feishu", "weibo", "wecom", "xiaozhi"]
        if data.channel not in valid_channels:
            raise HTTPException(status_code=400, detail=f"不支持的渠道: {data.channel}")

        # 标准化配置
        config_dict = _normalize_accounts_payload(data.config)
        accounts = config_dict.get("accounts", {}) or {data.account_id: config_dict}
        _validate_duplicate_accounts(data.channel, accounts)

        workspace = Path(config_loader.config.workspace.path).resolve()
        workspace.mkdir(parents=True, exist_ok=True)
        _validate_external_coding_route_config(data.channel, accounts, workspace)

        existing = await _get_user_channel_config(user_id, data.channel, data.account_id, db=db)

        if existing:
            existing.config_json = config_dict
            existing.is_enabled = 1 if data.is_enabled else 0
            existing.updated_at = utc_now()
            db.add(existing)
            result_id = existing.id
        else:
            new_config = UserChannelConfig(
                user_id=user_id,
                channel=data.channel,
                account_id=data.account_id,
                config_json=config_dict,
                is_enabled=1 if data.is_enabled else 0,
            )
            db.add(new_config)
            result_id = new_config.id

        await db.commit()
        await _restart_channel_manager_if_needed(request)

        return {
            "success": True,
            "message": "保存成功",
            "config_id": result_id,
        }

    except HTTPException:
        raise
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        await db.rollback()
        logger.error(f"Error saving user config (admin): {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/admin/users/{user_id}/config/{channel}/{account_id}")
async def delete_user_config(
    user_id: int,
    channel: str,
    account_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """管理员：删除指定用户的渠道配置"""
    try:
        admin = await _require_admin(request, db)

        config = await _get_user_channel_config(user_id, channel, account_id, db=db)
        if config is None:
            raise HTTPException(status_code=404, detail="配置不存在")

        await db.execute(sql_delete(UserChannelConfig).where(UserChannelConfig.id == config.id))
        await db.commit()

        await _restart_channel_manager_if_needed(request)

        return {"success": True, "message": "删除成功"}

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting user config (admin): {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _require_admin(request: Request, db: AsyncSession) -> UserModel:
    """要求管理员权限"""
    user_id = await get_current_user_id(request=request)
    user = await db.get(UserModel, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required")
    return user


# ============================================================
# Channel Test (uses user's config)
# ============================================================

async def _test_channel_connection(channel_name: str, config_dict: Dict[str, Any], user_id: int, request: Request) -> Dict[str, Any]:
    """测试渠道连接 — 创建临时实例进行测试。"""
    from backend.modules.channels.manager import _CHANNEL_REGISTRY, _CHANNEL_CONFIG_CLASSES, _lazy_load_config_classes
    _lazy_load_config_classes()

    if channel_name not in _CHANNEL_REGISTRY:
        return {"success": False, "message": f"未知渠道: {channel_name}"}

    module_path, class_name = _CHANNEL_REGISTRY[channel_name]
    config_class = _CHANNEL_CONFIG_CLASSES.get(channel_name)
    if not config_class:
        return {"success": False, "message": f"配置类未找到: {channel_name}"}

    try:
        module = __import__(module_path, fromlist=[class_name])
        cls = getattr(module, class_name)
    except ImportError as e:
        return {"success": False, "message": f"渠道模块不可用: {e}"}

    try:
        config_obj = config_class.model_validate(config_dict)
    except Exception as e:
        return {"success": False, "message": f"配置无效: {e}"}

    try:
        channel = cls(config_obj)
        return await channel.test_connection()
    except Exception as e:
        logger.error(f"Error testing {channel_name}: {e}")
        return {"success": False, "message": f"测试失败: {e}"}


@router.post("/test")
async def test_channel(
    data: ChannelTestRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """测试渠道连接（使用当前用户的配置）"""
    try:
        current_user_id = await _get_current_user_id(request, db)

        # 优先使用临时配置，否则使用用户保存的配置
        if data.config:
            # 临时配置测试
            temp_config = data.config
        else:
            # 从用户配置加载
            config_record = await _get_user_channel_config(current_user_id, data.channel, data.account_id, db=db)
            if config_record is None:
                return {
                    "success": False,
                    "message": "该渠道尚未配置，请先保存配置后再测试",
                }
            temp_config = config_record.config_json

        # 标准化配置
        temp_config = _normalize_accounts_payload(temp_config)

        # 选择要测试的账号
        accounts = temp_config.get("accounts", {}) or {}
        target_account_id = str(data.account_id or "default")
        if target_account_id in accounts:
            # 合并账号级配置到顶层
            account_cfg = accounts[target_account_id]
            merged_config = {**temp_config, **account_cfg, "account_id": target_account_id}
            temp_config = merged_config

        # 测试连接
        result = await _test_channel_connection(data.channel, temp_config, current_user_id, request)

        # 翻译消息
        translated_message = _translate_test_message(result.get("message", ""))
        result["message"] = translated_message

        return {
            "success": result.get("success", False),
            "message": translated_message,
            "data": result.get("bot_info", {}),
        }

    except Exception as e:
        logger.error(f"Error testing channel: {e}")
        return {
            "success": False,
            "message": f"测试失败: {str(e)}",
        }


def _translate_test_message(message: str) -> str:
    """翻译渠道测试消息"""
    translations = {
        "App ID or Secret not configured": "App ID 或 Secret 未配置",
        "Invalid App ID format": "App ID 格式无效",
        "Invalid Secret format": "Secret 格式无效",
        "Configuration format validated successfully": "配置格式验证通过",
        "Feishu credentials verified successfully": "飞书凭据验证成功",
        "QQ credentials verified successfully": "QQ 凭据验证成功",
        "WeCom credentials verified successfully": "企业微信凭据验证成功",
        "Configuration validated successfully. Enable the channel to test the actual connection.": "配置验证通过。启用渠道后将进行实际连接测试。",
    }

    translated = translations.get(message, message)

    # 动态翻译
    if message.startswith("Connected to @"):
        bot_username = message[len("Connected to @"):]
        translated = f"已连接到 @{bot_username}"
    elif message.startswith("Connection failed:"):
        translated = f"连接失败: {message[len('Connection failed:'):]}"

    return translated


# ============================================================
# WeChat QR Login
# ============================================================

class WeChatLoginStartRequest(BaseModel):
    account_id: str = "default"
    config: Dict[str, Any] = {}


@router.post("/wechat/login/start")
async def wechat_login_start(data: WeChatLoginStartRequest, request: Request):
    """开始微信扫码登录，返回二维码 URL 和 session_key。"""
    try:
        from backend.modules.channels.wechat import start_wechat_qr_login

        account_id = str(data.account_id or "default")
        config_snapshot = dict(data.config or {})

        result = await start_wechat_qr_login(
            account_id=account_id,
            base_url="",
            config_snapshot=config_snapshot,
        )

        return {
            "success": True,
            "qrcode_url": result.get("qrcode_url", ""),
            "session_key": result.get("session_key", ""),
            "account_id": account_id,
        }
    except Exception as e:
        logger.error(f"Error starting WeChat login: {e}")
        return {"success": False, "message": f"启动登录失败: {e}"}


@router.post("/wechat/login/poll")
async def wechat_login_poll(data: Dict[str, Any] = {}):
    """轮询微信扫码登录状态。"""
    try:
        from backend.modules.channels.wechat import poll_wechat_qr_login

        session_key = str(data.get("session_key", ""))
        if not session_key:
            return {"success": False, "status": "expired", "message": "session_key 不能为空"}

        result = await poll_wechat_qr_login(session_key)
        return result
    except Exception as e:
        logger.error(f"Error polling WeChat login: {e}")
        return {"success": False, "status": "error", "message": f"轮询失败: {e}"}


# ============================================================
# Channel Manager Reload (admin only)
# ============================================================

async def _restart_channel_manager_if_needed(fastapi_request: Request):
    """热更新渠道管理器 — 从 UserChannelConfig 重新加载所有用户的渠道配置。"""
    await _restart_channel_manager(fastapi_request)


async def _restart_channel_manager(fastapi_request: Request) -> Optional[ChannelManager]:
    """重启渠道管理器 — 从 UserChannelConfig 加载配置。

    流程：先初始化新管理器 → 成功后停止旧管理器并切换。
    这样即使新管理器初始化失败，旧管理器仍在运行（服务不中断）。
    """
    app_state = fastapi_request.app.state
    message_queue = getattr(app_state, "message_queue", None)

    if message_queue is None:
        logger.warning("Skip channel manager reload: message_queue missing")
        return getattr(app_state, "channel_manager", None)

    # 1. 先创建并初始化新管理器
    manager = ChannelManager(message_queue, db_session_factory=get_db_session_factory())
    try:
        await manager.async_init()
    except Exception as e:
        logger.error(f"Failed to initialize new channel manager: {e}")
        return getattr(app_state, "channel_manager", None)

    # 2. 新管理器就绪，停止旧管理器和旧后台任务
    old_manager = getattr(app_state, "channel_manager", None)
    if old_manager is not None:
        try:
            await old_manager.stop_all()
        except Exception as e:
            logger.error(f"Error stopping old channel manager: {e}")

    old_task = getattr(app_state, "channel_manager_task", None)
    if old_task is not None:
        try:
            await asyncio.wait_for(old_task, timeout=5)
        except asyncio.TimeoutError:
            old_task.cancel()
        except asyncio.CancelledError:
            pass

    # 3. 切换到新管理器
    app_state.channel_manager = manager
    set_channel_manager(manager)

    message_handler = getattr(app_state, "message_handler", None)
    if message_handler is not None:
        message_handler.set_channel_manager(manager)

    cron_executor = getattr(app_state, "cron_executor", None)
    if cron_executor is not None:
        cron_executor.channel_manager = manager

    # 4. 启动新的渠道管理器（start_all 会启动出站调度器和所有已启用的渠道）
    task = asyncio.create_task(manager.start_all())
    app_state.channel_manager_task = task
    app_state.background_tasks.append(task)

    logger.info(f"Reloaded channel manager with {len(manager.channels)} channel instance(s)")
    return manager


# ============================================================
# Status
# ============================================================

@router.get("/status")
async def get_channels_status(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """获取当前用户的渠道运行状态（用户隔离）。"""
    try:
        current_user_id = await _get_current_user_id(request, db)
        manager = get_channel_manager()
        status_data = manager.get_status(user_id=current_user_id)

        return {
            "success": True,
            "status": status_data,
            "running": any(s["running"] for s in status_data.values()),
        }

    except Exception as e:
        logger.error(f"Error getting channels status: {e}")
        return {
            "success": False,
            "status": {},
            "running": False,
            "error": str(e),
        }
