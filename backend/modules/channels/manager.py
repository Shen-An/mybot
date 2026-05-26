"""频道管理器模块 — 多用户隔离版本

负责从 UserChannelConfig 表加载所有用户的渠道配置，
为每个已启用的渠道创建实例，并标记所属 user_id。
所有频道在独立的监督任务中运行，异常退出后自动重连（指数退避）。
"""

import asyncio
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
from sqlalchemy import select

from backend.database import AsyncSessionLocal
from backend.models.user_channel_config import UserChannelConfig
from backend.modules.channels.base import BaseChannel, InboundMessage, OutboundMessage
from backend.modules.messaging.enterprise_queue import EnterpriseMessageQueue

# 频道注册表：name -> (module_path, class_name)
_CHANNEL_REGISTRY: Dict[str, Tuple[str, str]] = {
    "telegram": ("backend.modules.channels.telegram", "TelegramChannel"),
    "qq": ("backend.modules.channels.qq", "QQChannel"),
    "wechat": ("backend.modules.channels.wechat", "WeChatChannel"),
    "dingtalk": ("backend.modules.channels.dingtalk", "DingTalkChannel"),
    "feishu": ("backend.modules.channels.feishu", "FeishuChannel"),
    "weibo": ("backend.modules.channels.weibo", "WeiboChannel"),
    "wecom": ("backend.modules.channels.wecom", "WeComChannel"),
    "xiaozhi": ("backend.modules.channels.xiaozhi", "XiaozhiChannel"),
}

# 渠道 Pydantic 配置类注册表 — 用于从 UserChannelConfig JSON 重建配置对象
_CHANNEL_CONFIG_CLASSES: Dict[str, Any] = {}

def _lazy_load_config_classes():
    if _CHANNEL_CONFIG_CLASSES:
        return
    from backend.modules.config.schema import (
        TelegramConfig, QQConfig, WeChatConfig, DingTalkConfig,
        FeishuConfig, WeiboConfig, WeComConfig, XiaozhiConfig,
    )
    _CHANNEL_CONFIG_CLASSES.update({
        "telegram": TelegramConfig,
        "qq": QQConfig,
        "wechat": WeChatConfig,
        "dingtalk": DingTalkConfig,
        "feishu": FeishuConfig,
        "weibo": WeiboConfig,
        "wecom": WeComConfig,
        "xiaozhi": XiaozhiConfig,
    })


class ChannelManager:
    """频道管理器 — 多用户隔离

    职责：
    - 从 UserChannelConfig 表加载所有用户已启用的渠道配置
    - 为每个渠道实例标记所属 user_id
    - 统一启动 / 停止所有频道
    - 将出站消息路由到对应频道（按 channel + account_id + user_id）
    - 监督频道运行状态，异常退出时自动重连
    """

    def __init__(self, bus: EnterpriseMessageQueue, db_session_factory=None):
        self.bus = bus
        self.db_session_factory = db_session_factory or AsyncSessionLocal
        self.channels: Dict[str, BaseChannel] = {}
        self._channels_by_type: Dict[str, List[str]] = {}
        self._channel_tasks: Dict[str, asyncio.Task] = {}
        self._dispatch_task: Optional[asyncio.Task] = None
        self._running = False
        # NOTE: initialization is async — call await manager.async_init() after construction

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------

    async def async_init(self) -> None:
        """异步初始化：从 UserChannelConfig 表加载配置并创建渠道实例。

        必须在构造后、start_all() 之前调用。
        """
        _lazy_load_config_classes()

        try:
            async with self.db_session_factory() as session:
                result = await session.execute(
                    select(UserChannelConfig).where(UserChannelConfig.is_enabled == 1)
                )
                configs = result.scalars().all()
        except Exception as e:
            logger.error(f"Failed to load channel configs from UserChannelConfig: {e}")
            logger.warning("No channels will be initialized")
            return

        if not configs:
            logger.info("No enabled channel configs found in UserChannelConfig")
            return

        # 按 channel 分组，以便去重检测
        from collections import defaultdict
        configs_by_channel: Dict[str, List[UserChannelConfig]] = defaultdict(list)
        for cfg in configs:
            configs_by_channel[cfg.channel].append(cfg)

        for channel_name, channel_configs in configs_by_channel.items():
            if channel_name not in _CHANNEL_REGISTRY:
                logger.warning(f"Unknown channel type: {channel_name}, skipping")
                continue
            if channel_name not in _CHANNEL_CONFIG_CLASSES:
                logger.warning(f"No config class for channel: {channel_name}, skipping")
                continue

            module_path, class_name = _CHANNEL_REGISTRY[channel_name]
            config_class = _CHANNEL_CONFIG_CLASSES[channel_name]

            try:
                module = __import__(module_path, fromlist=[class_name])
                cls = getattr(module, class_name)
            except ImportError as e:
                logger.warning(f"{channel_name} channel module not available: {e}")
                continue
            except Exception as e:
                logger.error(f"Failed to load {channel_name} channel class: {e}")
                continue

            # 去重检测：防止同一个物理机器人被多个用户配置
            unique_field_map = {
                "telegram": ("token",),
                "qq": ("app_id",),
                "wechat": ("login_bot_id",),
                "dingtalk": ("client_id",),
                "feishu": ("app_id",),
                "weibo": ("app_id",),
                "wecom": ("bot_id",),
            }
            seen_signatures: Dict[str, int] = {}  # signature -> first_user_id

            for user_cfg in channel_configs:
                config_dict = dict(user_cfg.config_json or {})
                config_dict["account_id"] = user_cfg.account_id

                # 如果 account_id 不是 default 且在 accounts 中有子配置，合并
                accounts = config_dict.get("accounts", {}) or {}
                if user_cfg.account_id != "default" and user_cfg.account_id in accounts:
                    sub_config = dict(accounts[user_cfg.account_id])
                    # 合并子配置到顶层（不覆盖顶层已设置的值）
                    for k, v in sub_config.items():
                        if k not in ("account_id", "accounts", "enabled") and not config_dict.get(k):
                            config_dict[k] = v

                try:
                    config_obj = config_class.model_validate(config_dict)
                except Exception as e:
                    logger.warning(f"Invalid config for {channel_name}:{user_cfg.account_id} (user #{user_cfg.user_id}): {e}")
                    continue

                # 物理机器人去重
                fields = unique_field_map.get(channel_name)
                if fields:
                    sig_parts = []
                    for field in fields:
                        val = str(getattr(config_obj, field, "") or "").strip()
                        if val:
                            sig_parts.append(f"{field}={val}")
                    if sig_parts:
                        sig = "|".join(sig_parts)
                        if sig in seen_signatures:
                            logger.warning(
                                f"Skipping {channel_name}:{user_cfg.account_id} (user #{user_cfg.user_id}): "
                                f"same credentials already used by user #{seen_signatures[sig]}"
                            )
                            continue
                        seen_signatures[sig] = user_cfg.user_id

                try:
                    channel = cls(config_obj)
                except Exception as e:
                    logger.error(f"Failed to create {channel_name} channel instance for user #{user_cfg.user_id}: {e}")
                    continue

                channel._user_id = user_cfg.user_id
                channel._user_channel_config_id = user_cfg.id

                # 构建实例键：channel:account_id:user_id
                instance_key = self._build_instance_key(channel_name, user_cfg.account_id, user_cfg.user_id)
                self.channels[instance_key] = channel
                self._channels_by_type.setdefault(channel_name, []).append(instance_key)

                setattr(channel, "_instance_key", instance_key)
                setattr(channel, "_account_id", user_cfg.account_id)
                logger.debug(
                    f"{class_name} initialized for user #{user_cfg.user_id}, "
                    f"channel={channel_name}, account={user_cfg.account_id}"
                )

        logger.info(
            f"Initialized {len(self.channels)} channel instance(s) "
            f"for {len(configs)} user config(s): {list(self.channels.keys())}"
        )

        for channel in self.channels.values():
            channel.set_message_callback(self._on_inbound_message)

    @staticmethod
    def _build_instance_key(channel_name: str, account_id: str, user_id: int) -> str:
        """构建实例键：channel:account_id:user_id"""
        return f"{channel_name}:{account_id}:{user_id}"

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # 启动 / 停止
    # ------------------------------------------------------------------

    async def start_dispatch(self) -> None:
        """仅启动出站消息调度器（不启动任何渠道）。

        在服务器启动时调用：渠道实例会按需在用户登录时启动。
        """
        self._running = True
        self._dispatch_task = asyncio.create_task(self._dispatch_outbound())
        logger.info("Outbound dispatcher started (no channels)")

    async def start_all(self) -> None:
        """启动所有频道和出站消息调度器（全量重启用）。"""
        self._running = True
        self._dispatch_task = asyncio.create_task(self._dispatch_outbound())
        tasks = [self._dispatch_task]

        if not self.channels:
            logger.info("No channels to start, outbound dispatcher running")
            await asyncio.gather(*tasks, return_exceptions=True)
            return

        self._channel_tasks = {}
        for name, channel in self.channels.items():
            task = asyncio.create_task(self._start_channel_supervised(name, channel))
            tasks.append(task)
            self._channel_tasks[name] = task
        await asyncio.gather(*tasks, return_exceptions=True)

    async def start_user_channels(self, user_id: int) -> int:
        """启动指定用户的所有已启用渠道。"""
        count = 0
        for key, channel in self.channels.items():
            if getattr(channel, '_user_id', None) == user_id:
                if key not in self._channel_tasks:
                    task = asyncio.create_task(
                        self._start_channel_supervised(key, channel)
                    )
                    self._channel_tasks[key] = task
                    count += 1
        if count:
            logger.info(f"Started {count} channel(s) for user #{user_id}")
        return count

    async def stop_all(self) -> None:
        """停止所有频道。"""
        logger.info("Stopping all channels...")
        self._running = False
        for name, channel in self.channels.items():
            try:
                # Cancel supervision task if tracked
                task = self._channel_tasks.pop(name, None)
                if task and not task.done():
                    task.cancel()
                await channel.stop()
                logger.info(f"Stopped {name} channel")
            except Exception as e:
                logger.error(f"Error stopping {name}: {e}")
        # Cancel the dispatch task
        if self._dispatch_task and not self._dispatch_task.done():
            self._dispatch_task.cancel()

    async def stop_user_channels(self, user_id: int) -> int:
        """停止指定用户的所有频道实例。返回停止的频道数。"""
        keys_to_remove = []
        for key, channel in self.channels.items():
            if getattr(channel, '_user_id', None) == user_id:
                keys_to_remove.append(key)

        for key in keys_to_remove:
            channel = self.channels[key]
            try:
                task = self._channel_tasks.pop(key, None)
                if task and not task.done():
                    task.cancel()
                await channel.stop()
            except Exception as e:
                logger.error(f"Error stopping channel {key}: {e}")

        if keys_to_remove:
            logger.info(f"Stopped {len(keys_to_remove)} channel(s) for user #{user_id}")
        return len(keys_to_remove)

    # ------------------------------------------------------------------
    # 频道监督
    # ------------------------------------------------------------------

    async def _start_channel_supervised(self, name: str, channel: BaseChannel) -> None:
        """在监督循环中启动频道。

        频道异常退出后自动重连，使用指数退避（5s -> 10s -> ... -> 300s）。
        如果频道成功运行超过 60 秒后才断开，退避时间重置。
        """
        initial_backoff = 5
        max_backoff = 300
        backoff = initial_backoff

        while self._running:
            start_time = asyncio.get_event_loop().time()
            try:
                logger.info(f"Starting {name} channel...")
                await channel.start()
                if self._running and channel.is_running:
                    logger.info(f"Channel {name} is running in background mode")
                    while self._running and channel.is_running:
                        await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Channel {name} error: {e}")

            if not self._running:
                break

            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > 60:
                backoff = initial_backoff

            logger.warning(f"Channel {name} exited, restarting in {backoff}s...")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)

    # ------------------------------------------------------------------
    # 消息路由
    # ------------------------------------------------------------------

    async def _on_inbound_message(self, msg: InboundMessage) -> None:
        """入站消息回调：注入 user_id 后转发到消息总线。"""
        # 查找该渠道实例所属的用户
        instance_key = msg.metadata.get("instance_key")
        if instance_key:
            ch = self.channels.get(instance_key)
            if ch and getattr(ch, '_user_id', None) is not None:
                msg.metadata["user_id"] = ch._user_id
        logger.debug(f"Inbound from {msg.channel}: {msg.content[:50]}...")
        await self.bus.publish_inbound(msg)

    async def _dispatch_outbound(self) -> None:
        """出站消息调度：从总线消费消息并路由到对应频道。"""
        logger.debug("Outbound dispatcher started")
        while self._running:
            try:
                msg = await asyncio.wait_for(self.bus.consume_outbound(), timeout=1.0)
                channel = self._resolve_outbound_channel(msg)
                if channel:
                    try:
                        await channel.send(msg)
                        logger.debug(
                            f"Sent via {getattr(channel, 'instance_key', msg.channel)} to {msg.chat_id}"
                        )
                    except Exception as e:
                        logger.error(f"Failed to send via {msg.channel}: {e}")
                else:
                    logger.warning(f"Unknown channel: {msg.channel}")
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    async def send_message(self, msg: OutboundMessage) -> None:
        """发送消息到指定频道（通过消息总线）。"""
        await self.bus.publish_outbound(msg)

    def _resolve_outbound_channel(self, msg: OutboundMessage) -> Optional[BaseChannel]:
        """根据 channel + account_id + user_id 解析具体机器人实例。"""
        metadata = msg.metadata or {}
        account_id = str(metadata.get("account_id") or "").strip()
        user_id = metadata.get("user_id")

        if account_id and user_id is not None:
            instance_key = self._build_instance_key(msg.channel, account_id, user_id)
            channel = self.channels.get(instance_key)
            if channel:
                return channel

        # 回退：遍历查找匹配 channel 的第一个实例
        for ch in self.channels.values():
            ch_type = getattr(ch, "_instance_key", "").split(":")[0]
            if ch_type == msg.channel:
                if user_id is None or getattr(ch, '_user_id', None) == user_id:
                    if not account_id or getattr(ch, '_account_id', None) == account_id:
                        return ch
        return None

    def get_channel(self, name: str, account_id: Optional[str] = None, user_id: Optional[int] = None) -> Optional[BaseChannel]:
        """按名称和用户获取频道实例。"""
        if account_id and user_id is not None:
            return self.channels.get(self._build_instance_key(name, account_id, user_id))
        for ch in self.channels.values():
            ch_type = getattr(ch, "_instance_key", "").split(":")[0]
            if ch_type == name:
                if user_id is None or getattr(ch, '_user_id', None) == user_id:
                    if account_id is None or getattr(ch, '_account_id', None) == account_id:
                        return ch
        return None

    async def test_channel(self, name: str, account_id: Optional[str] = None, user_id: Optional[int] = None) -> Dict[str, Any]:
        """测试指定频道的连接。支持按用户和账号测试。"""
        if name not in _CHANNEL_REGISTRY:
            return {"success": False, "message": f"Unknown channel: {name}"}

        # 已初始化的频道直接测试
        channel = self.get_channel(name, account_id=account_id, user_id=user_id)
        if channel:
            try:
                return await channel.test_connection()
            except Exception as e:
                logger.error(f"Error testing {name}: {e}")
                return {"success": False, "message": f"Test failed: {e}"}

        # 未初始化则从 UserChannelConfig 加载用户配置测试
        _lazy_load_config_classes()
        try:
            module_path, class_name = _CHANNEL_REGISTRY[name]
            module = __import__(module_path, fromlist=[class_name])
            cls = getattr(module, class_name)
            config_class = _CHANNEL_CONFIG_CLASSES.get(name)
            if not config_class:
                return {"success": False, "message": f"Config class not found for {name}"}

            async def _load_test_config():
                async with self.db_session_factory() as session:
                    from sqlalchemy import select
                    stmt = select(UserChannelConfig).where(
                        UserChannelConfig.channel == name,
                        UserChannelConfig.account_id == (account_id or "default"),
                    )
                    if user_id is not None:
                        stmt = stmt.where(UserChannelConfig.user_id == user_id)
                    result = await session.execute(stmt)
                    return result.scalar_one_or_none()

            loop = asyncio.new_event_loop()
            try:
                record = loop.run_until_complete(_load_test_config())
            finally:
                loop.close()

            if record is None:
                return {
                    "success": False,
                    "message": f"Configuration for {name}:{account_id or 'default'} not found",
                }

            config_dict = dict(record.config_json or {})
            config_dict["account_id"] = record.account_id
            config_obj = config_class.model_validate(config_dict)
            return await cls(config_obj).test_connection()

        except ImportError as e:
            return {"success": False, "message": f"Channel module not available: {e}"}
        except Exception as e:
            logger.error(f"Error testing {name}: {e}")
            return {"success": False, "message": f"Test failed: {e}"}

    def get_status(self, user_id: Optional[int] = None) -> Dict[str, Any]:
        """获取所有频道的运行状态。可按 user_id 过滤。"""
        grouped: Dict[str, Any] = {}
        for channel_type, instance_keys in self._channels_by_type.items():
            instances = {}
            running = False
            for instance_key in instance_keys:
                channel = self.channels[instance_key]
                # 如果指定了 user_id，跳过不匹配的实例
                if user_id is not None and getattr(channel, '_user_id', None) != user_id:
                    continue
                account_id = getattr(channel, "account_id", "default")
                runtime_status = {}
                if hasattr(channel, "get_runtime_status"):
                    try:
                        runtime_status = channel.get_runtime_status() or {}
                    except Exception as e:
                        logger.debug(f"Failed to get runtime status for {instance_key}: {e}")
                        runtime_status = {}
                effective_running = bool(
                    runtime_status.get("healthy_running", channel.is_running)
                )
                instances[account_id] = {
                    "enabled": True,
                    "running": effective_running,
                    "display_name": channel.display_name,
                    "instance_key": instance_key,
                    "runtime_status": runtime_status,
                    "user_id": channel._user_id if hasattr(channel, '_user_id') else None,
                }
                running = running or effective_running

            if not instances:
                continue

            grouped[channel_type] = {
                "enabled": bool(instances),
                "running": running,
                "display_name": channel_type.capitalize(),
                "instances": instances,
            }
        return grouped

    @property
    def enabled_channels(self) -> List[str]:
        return list(self.channels.keys())

    @property
    def is_running(self) -> bool:
        return self._running
