"""用户级配置包装器 — 基于全局 ConfigLoader 添加用户隔离"""

import json
from typing import Any, Optional

from loguru import logger
from sqlalchemy import select, update, delete

from backend.database import AsyncSessionLocal
from backend.models.setting import Setting


USER_CONFIG_PREFIX = "user"
GLOBAL_CONFIG_PREFIX = "config"


async def get_user_config(user_id: int, key: str, default: Any = None) -> Any:
    """获取用户级配置值

    用户配置存储在 settings 表，key 格式为: user.{user_id}.config.{key_path}
    如果用户配置不存在，回退到全局配置 config.{key_path}
    """
    user_key = f"{USER_CONFIG_PREFIX}.{user_id}.config.{key}"
    global_key = f"{GLOBAL_CONFIG_PREFIX}.{key}"

    async with AsyncSessionLocal() as session:
        # 先尝试用户配置
        result = await session.execute(select(Setting).where(Setting.key == user_key))
        setting = result.scalar_one_or_none()
        if setting:
            try:
                return json.loads(setting.value)
            except (json.JSONDecodeError, TypeError):
                pass

        # 回退到全局配置
        result = await session.execute(select(Setting).where(Setting.key == global_key))
        setting = result.scalar_one_or_none()
        if setting:
            try:
                return json.loads(setting.value)
            except (json.JSONDecodeError, TypeError):
                pass

        return default


async def set_user_config(user_id: int, key: str, value: Any) -> None:
    """设置用户级配置值"""
    user_key = f"{USER_CONFIG_PREFIX}.{user_id}.config.{key}"

    async with AsyncSessionLocal() as session:
        setting = Setting(key=user_key, value=json.dumps(value))
        await session.merge(setting)
        await session.commit()
        logger.info(f"User config set: user_id={user_id}, key={key}")


async def delete_user_config(user_id: int, key: Optional[str] = None) -> int:
    """删除用户级配置（可选删除整个用户的所有配置）"""
    async with AsyncSessionLocal() as session:
        if key:
            user_key = f"{USER_CONFIG_PREFIX}.{user_id}.config.{key}"
            result = await session.execute(delete(Setting).where(Setting.key == user_key))
        else:
            pattern = f"{USER_CONFIG_PREFIX}.{user_id}.config.%"
            result = await session.execute(delete(Setting).where(Setting.key.like(pattern)))
        await session.commit()
        return result.rowcount


async def get_all_user_config(user_id: int) -> dict:
    """获取用户的所有配置"""
    async with AsyncSessionLocal() as session:
        pattern = f"{USER_CONFIG_PREFIX}.{user_id}.config.%"
        result = await session.execute(select(Setting).where(Setting.key.like(pattern)))
        settings = result.scalars().all()

        config = {}
        for setting in settings:
            key_path = setting.key.replace(f"{USER_CONFIG_PREFIX}.{user_id}.config.", "")
            try:
                value = json.loads(setting.value)
            except (json.JSONDecodeError, TypeError):
                value = setting.value
            _set_nested_value(config, key_path, value)

        return config


def _set_nested_value(data: dict, key_path: str, value: Any) -> None:
    keys = key_path.split(".")
    current = data
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value
