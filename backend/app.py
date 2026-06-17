"""FastAPI 应用入口"""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger

from backend.utils.logger import setup_logger
from backend.utils.runtime_env import resolve_bind_host
from backend.database import get_db_session_factory
from backend.version import APP_VERSION

setup_logger()


def _create_shared_components(config, config_loader=None):
    """创建共享组件（WebSocket 和渠道处理器共用）"""
    from loguru import logger
    from backend.modules.providers import create_provider
    from backend.modules.providers.runtime import (
        find_first_selectable_provider,
        get_provider_runtime_state,
    )
    from backend.modules.agent.context import ContextBuilder
    from backend.modules.agent.memory import MemoryStore
    from backend.modules.agent.skills import SkillsLoader
    from backend.modules.agent.subagent import SubagentManager
    from backend.modules.tools.setup import register_all_tools
    from backend.modules.workspace import (
        seed_bundled_workspace_resources,
        workspace_manager,
    )

    logger.info("Getting provider metadata...")
    provider_id = config.model.provider
    runtime_state = get_provider_runtime_state(config, provider_id)
    if not runtime_state.selectable:
        fallback_state = find_first_selectable_provider(config)
        if fallback_state and fallback_state.provider_id != provider_id:
            logger.warning(
                f"共享组件默认 provider '{provider_id}' 不可用（{runtime_state.reason}），"
                f"已回退到 '{fallback_state.provider_id}'"
            )
            runtime_state = fallback_state
            provider_id = fallback_state.provider_id
        else:
            logger.warning(
                f"共享组件默认 provider '{provider_id}' 当前不可用（{runtime_state.reason}），"
                "将继续使用现有配置完成启动，实际请求阶段会再校验"
            )

    logger.info("Setting up workspace...")
    workspace, used_fallback = workspace_manager.resolve_workspace_path_or_default(
        config.workspace.path
    )
    workspace_manager.activate_workspace_path(workspace)
    if used_fallback:
        config.workspace.path = str(workspace)
        logger.warning(f"共享组件启动时已回退到默认工作空间: {workspace}")

    logger.info("Creating LLM provider...")
    provider = create_provider(
        api_key=runtime_state.api_key or None,
        api_keys=runtime_state.api_keys or None,
        api_base=runtime_state.api_base,
        default_model=config.model.model,
        api_mode=config.model.api_mode,
        timeout=120.0,
        max_retries=3,
        provider_id=provider_id,
    )

    logger.info("Creating memory and skills directories...")
    memory_dir = workspace / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)

    seed_bundled_workspace_resources(workspace)

    # Skills 目录始终从 workspace/skills 加载
    # 确保用户修改 workspace 路径后，skills 也在新路径下
    skills_dir = workspace / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Workspace: {workspace}")
    logger.info(f"Skills directory: {skills_dir}")

    logger.info("Initializing memory store...")
    memory = MemoryStore(memory_dir)
    
    logger.info("Loading skills...")
    skills = SkillsLoader(skills_dir)

    logger.info("Building context builder...")
    context_builder = ContextBuilder(
        workspace=workspace,
        memory=memory,
        skills=skills,
        persona_config=config.persona,
    )

    logger.info("Creating subagent manager...")
    subagent_manager = SubagentManager(
        provider=provider,
        workspace=workspace,
        model=config.model.model,
        temperature=config.model.temperature,
        max_tokens=config.model.max_tokens,
        db_session_factory=get_db_session_factory(),
        config_loader=config_loader,
        skills=skills,
    )

    logger.info("Preparing tool parameters...")
    tool_params = dict(
        workspace=workspace,
        command_timeout=config.security.command_timeout,
        max_output_length=config.security.max_output_length,
        allow_dangerous=not config.security.dangerous_commands_blocked,
        restrict_to_workspace=config.security.restrict_to_workspace,
        custom_deny_patterns=config.security.custom_deny_patterns,
        custom_allow_patterns=(
            config.security.custom_allow_patterns
            if config.security.command_whitelist_enabled
            else None
        ),
        audit_log_enabled=config.security.audit_log_enabled,
        subagent_manager=subagent_manager,
        skills_loader=skills,
    )

    logger.info("Registering all tools...")
    tool_registry = register_all_tools(**tool_params, memory_store=memory)
    logger.info(f"Registered {len(tool_registry)} tools")

    return dict(
        provider=provider,
        workspace=workspace,
        context_builder=context_builder,
        subagent_manager=subagent_manager,
        tool_registry=tool_registry,
        tool_params=tool_params,
        memory=memory,
        skills=skills,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    from backend.database import init_db, get_db_session_factory
    from backend.modules.config.loader import config_loader
    from backend.modules.channels.manager import ChannelManager
    from backend.modules.messaging.enterprise_queue import EnterpriseMessageQueue
    from backend.modules.messaging.rate_limiter import RateLimiter
    from backend.modules.channels.handler import ChannelMessageHandler
    from backend.modules.cron.executor import CronExecutor
    from backend.modules.cron.scheduler import CronScheduler
    from backend.modules.cron.service import CronService
    from backend.modules.agent.loop import AgentLoop
    from backend.modules.tools.setup import register_all_tools
    from backend.api.channels import set_channel_manager
    from backend.modules.auth.middleware import (
        clear_remote_setup_secret,
        ensure_remote_setup_secret,
        get_remote_setup_secret_ttl_minutes,
    )
    from backend.modules.auth.router import get_password_hash as get_auth_password_hash

    # 初始化数据库和配置
    logger.info("Starting CountBot backend...")
    app.state.background_tasks = []
    await init_db()
    logger.info("Database initialized")
    await config_loader.load()
    logger.info("Configuration loaded")
    config = config_loader.config

    if await get_auth_password_hash():
        clear_remote_setup_secret(app)
    else:
        setup_secret = ensure_remote_setup_secret(app)
        setup_secret_ttl_minutes = get_remote_setup_secret_ttl_minutes()
        logger.info(
            f"远程首次初始化入口：将此路径拼接到上方 Network 地址后访问（有效期 {setup_secret_ttl_minutes} 分钟，初始化成功后立即失效） -> /setup/{setup_secret}"
        )
        logger.info(
            f"Remote first-time setup entry: append this path to the Network URL above (valid for {setup_secret_ttl_minutes} minutes and expires immediately after setup succeeds) -> /setup/{setup_secret}"
        )

    # 创建共享组件
    logger.info("Creating shared components...")
    shared = _create_shared_components(config, config_loader)
    app.state.shared = shared
    app.state.skills = shared["skills"]
    app.state.memory = shared["memory"]
    logger.info("Shared components created")
    
    # 设置全局 SubagentManager
    from backend.api.chat import set_global_subagent_manager
    set_global_subagent_manager(shared["subagent_manager"])

    logger.info("Creating message queue and rate limiter...")
    message_queue = EnterpriseMessageQueue(
        enable_dedup=True, 
        dedup_window=10
    )
    app.state.message_queue = message_queue
    rate_limiter = RateLimiter(rate=10, per=60)
    logger.info("Message queue and rate limiter created")

    # 创建渠道消息处理器
    logger.info("Creating message handler...")
    message_handler = ChannelMessageHandler(
        provider=shared["provider"],
        workspace=shared["workspace"],
        model=config.model.model,
        bus=message_queue,
        context_builder=shared["context_builder"],
        tool_params=shared["tool_params"],
        subagent_manager=shared["subagent_manager"],
        max_iterations=config.model.max_iterations,
        rate_limiter=rate_limiter,
        temperature=config.model.temperature,
        max_tokens=config.model.max_tokens,
        thinking_enabled=config.model.thinking_enabled,
        max_history_messages=config.persona.max_history_messages,
        memory_store=shared["memory"],
    )
    app.state.message_handler = message_handler
    logger.info("Message handler created")

    # 创建渠道管理器
    logger.info("Creating channel manager...")
    channel_manager = ChannelManager(message_queue, db_session_factory=get_db_session_factory())
    await channel_manager.async_init()
    app.state.channel_manager = channel_manager
    set_channel_manager(channel_manager)
    message_handler.set_channel_manager(channel_manager)
    shared_tool_params = shared.get("tool_params")
    if isinstance(shared_tool_params, dict):
        shared_tool_params["channel_manager"] = channel_manager
        shared["tool_registry"] = register_all_tools(
            **shared_tool_params,
            memory_store=shared["memory"],
        )
    logger.info("Channel manager created")

    # 初始化 MCP 客户端（如果已启用，非阻塞后台连接）
    if config.mcp.enabled:
        logger.info("Initializing MCP client (background)...")
        try:
            from backend.modules.mcp.client import McpClientManager
            manager = McpClientManager.get_instance()
            manager.set_registry(shared["tool_registry"])
            enabled_servers = [s for s in config.mcp.registry.servers if s.enabled]
            if enabled_servers:
                logger.info(f"Scheduling background connection to {len(enabled_servers)} MCP server(s)...")
                task = asyncio.create_task(manager.connect(enabled_servers))
                app.state.background_tasks.append(task)
            else:
                logger.info("No enabled MCP servers to connect")
        except ImportError:
            logger.info("MCP package not installed, skipping MCP initialization")
        except Exception as e:
            logger.warning(f"Failed to schedule MCP initialization: {e}")
    else:
        logger.info("MCP is disabled, skipping initialization")

    # 初始化 OSS 上传器（可选）
    logger.info("Initializing OSS uploader (optional)...")
    try:
        from backend.modules.tools.image_uploader import init_oss_uploader
        oss_config = None
        if hasattr(config.channels, "qq") and hasattr(config.channels.qq, "oss"):
            oss_config = config.channels.qq.oss.model_dump()
        init_oss_uploader(oss_config)
        logger.info("OSS uploader initialized")
    except ModuleNotFoundError as e:
        if e.name == "backend.modules.tools.image_uploader":
            logger.info("OSS uploader module not installed; skipping optional OSS uploader")
        else:
            logger.warning(f"OSS uploader init failed (optional): {e}")
    except Exception as e:
        logger.warning(f"OSS uploader init failed (optional): {e}")

    # 启动后台任务（不等待完成）
    app.state.background_tasks = []
    app.state.channel_manager_task = None
    # 启动所有已启用的渠道和出站调度器（异步非阻塞）
    channel_task = asyncio.create_task(channel_manager.start_all())
    app.state.channel_manager_task = channel_task
    app.state.background_tasks.append(channel_task)
    logger.info("Channel manager started")
    
    task = asyncio.create_task(message_handler.start_processing())
    app.state.background_tasks.append(task)
    logger.info("Started message handler in background")

    # 初始化定时任务系统
    logger.info("Initializing cron system...")
    cron_tool_registry = register_all_tools(
        **shared["tool_params"],
        memory_store=shared["memory"],
    )
    cron_agent = AgentLoop(
        provider=shared["provider"],
        workspace=shared["workspace"],
        tools=cron_tool_registry,
        context_builder=shared["context_builder"],
        subagent_manager=shared["subagent_manager"],
        model=config.model.model,
        max_iterations=config.model.max_iterations,
        temperature=config.model.temperature,
        max_tokens=config.model.max_tokens,
        thinking_enabled=config.model.thinking_enabled,
        user_id=None,  # cron 是系统级任务，无特定用户
    )
    logger.info("Cron agent created")

    # 初始化心跳服务
    logger.info("Initializing heartbeat service...")
    db_session_factory = get_db_session_factory()

    from backend.modules.agent.heartbeat import HeartbeatService, ensure_heartbeat_job
    heartbeat_config = config.persona.heartbeat
    heartbeat_service = HeartbeatService(
        provider=shared["provider"],
        model=config.model.model,
        workspace=shared["workspace"],
        db_session_factory=db_session_factory,
        ai_name=config.persona.ai_name or "小C",
        user_name=config.persona.user_name or "主人",
        user_address=config.persona.user_address or "",
        personality=config.persona.personality or "professional",
        custom_personality=config.persona.custom_personality or "",
        idle_threshold_hours=heartbeat_config.idle_threshold_hours,
        quiet_start=heartbeat_config.quiet_start,
        quiet_end=heartbeat_config.quiet_end,
        max_greets_per_day=heartbeat_config.max_greets_per_day,
    )
    logger.info("Heartbeat service created")

    logger.info("Creating cron executor...")
    cron_executor = CronExecutor(
        agent=cron_agent,
        bus=message_queue,
        channel_manager=channel_manager,
        heartbeat_service=heartbeat_service,
    )
    logger.info("Cron executor created")

    async def on_cron_execute(
        job_id: str,
        message: str,
        channel: str,
        account_id: str,
        chat_id: str,
        deliver_response: bool,
    ) -> str:
        return await cron_executor.execute(
            job_id, message, channel, account_id, chat_id, deliver_response
        )

    logger.info("Creating cron scheduler...")
    scheduler = CronScheduler(
        db_session_factory=db_session_factory,
        on_execute=on_cron_execute,
    )
    await scheduler.start()
    logger.info("Cron scheduler started")

    # 注册内置心跳任务
    logger.info("Ensuring heartbeat job...")
    await ensure_heartbeat_job(db_session_factory, heartbeat_config=heartbeat_config)
    await scheduler.trigger_reschedule()
    logger.info("Heartbeat job ensured")

    app.state.cron_scheduler = scheduler
    app.state.cron_executor = cron_executor

    # 注册进程退出清理处理器（备用机制）
    import atexit
    
    def cleanup_on_exit() -> None:
        """进程退出时的清理函数"""
        logger.info("atexit cleanup triggered")
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(channel_manager.stop_all())
            finally:
                loop.close()
        except RuntimeError as e:
            logger.debug(f"Event loop already closed: {e}")
        except Exception as e:
            logger.error(f"Error in atexit cleanup: {e}")
    
    atexit.register(cleanup_on_exit)

    logger.info("Backend started successfully")

    yield

    # 正常关闭流程
    logger.info("Initiating graceful shutdown...")
    await channel_manager.stop_all()
    await scheduler.stop()
    logger.info("Backend shutdown complete")


app = FastAPI(
    title="CountBot Desktop API",
    description="CountBot backend API",
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# 保存绑定地址用于认证判断
app.state.bind_host = resolve_bind_host()


def get_tool_registry():
    """返回全局共享工具注册表，供 XiaozhiChannel 等频道内部调用。"""
    try:
        return app.state.shared.get("tool_registry")
    except AttributeError:
        return None

app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# 远程访问认证中间件
from backend.modules.auth.middleware import (
    RemoteAuthMiddleware,
    has_valid_remote_setup_secret,
)
from backend.modules.auth.router import get_password_hash

app.add_middleware(RemoteAuthMiddleware, get_password_hash_fn=get_password_hash)

# 注册 API 路由
from backend.api.chat import router as chat_router
from backend.api.settings import router as settings_router
from backend.api.tools import router as tools_router
from backend.api.memory import router as memory_router
from backend.api.skills import router as skills_router
from backend.api.cron import router as cron_router
from backend.api.tasks import router as tasks_router
from backend.api.system import router as system_router
from backend.api.channels import router as channels_router
from backend.api.queue import router as queue_router
from backend.api.auth import router as auth_router
from backend.api.personalities import router as personalities_router
from backend.api.agent_teams import router as agent_teams_router
from backend.api.mcp import router as mcp_router
from backend.api.wiki import router as wiki_router

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(settings_router)
app.include_router(tools_router)
app.include_router(memory_router)
app.include_router(skills_router)
app.include_router(cron_router)
app.include_router(tasks_router)
app.include_router(system_router)
app.include_router(channels_router)
app.include_router(queue_router)
app.include_router(personalities_router)
app.include_router(agent_teams_router)
app.include_router(mcp_router)
app.include_router(wiki_router)


# WebSocket 端点
from fastapi import WebSocket
from backend.ws.connection import handle_websocket


@app.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 聊天端点，复用共享组件 — 多用户支持"""
    from backend.database import get_db_session_factory
    from backend.modules.agent.loop import AgentLoop
    from backend.modules.auth.context import set_current_user_context
    from backend.modules.auth.utils import validate_auth_session, get_user_by_id
    from backend.modules.providers import create_provider
    from backend.modules.providers.registry import get_provider_metadata
    from backend.modules.tools.setup import register_all_tools

    from backend.modules.auth.middleware import AUTH_COOKIE_NAME, is_direct_local_client
    from backend.modules.auth.router import get_password_hash as get_ws_password_hash

    client_ip = websocket.client.host if websocket.client and websocket.client.host else None
    is_local = is_direct_local_client(client_ip, websocket.headers.keys())

    user_id = None
    if not is_local:
        auth_enabled = bool(await get_ws_password_hash())
        if not auth_enabled:
            await websocket.close(code=4003, reason="Authentication setup required")
            return

        token = websocket.cookies.get(AUTH_COOKIE_NAME)
        if not token:
            auth_header = websocket.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]

        if not token:
            await websocket.close(code=4001, reason="Authentication required")
            return

        # Validate session and get user_id
        db = get_db_session_factory()()
        try:
            user_id = await validate_auth_session(token, db)
            if user_id is None:
                await websocket.close(code=4001, reason="Authentication required")
                return

            user = await get_user_by_id(user_id, db)
            if user is None or not user.is_active:
                await websocket.close(code=4001, reason="User not found or deactivated")
                return

            # Set contextvars for non-HTTP code paths
            set_current_user_context(user.id, user.username, user.role)

            # Store user_id in websocket app state for AgentLoop
            websocket.app.state.user_id = user.id
        finally:
            await db.close()

    if is_local and user_id is None:
        # 本地 WebSocket 无 token 时，使用首个 admin 作为默认用户
        db2 = get_db_session_factory()()
        try:
            from backend.models.user import User
            from sqlalchemy import select
            result = await db2.execute(
                select(User).where(User.is_active == True).order_by(User.id).limit(1)  # noqa: E712
            )
            default_user = result.scalar_one_or_none()
            if default_user and default_user.is_active:
                user_id = default_user.id
                set_current_user_context(default_user.id, default_user.username, default_user.role)
                websocket.app.state.user_id = default_user.id
        finally:
            await db2.close()

    shared = websocket.app.state.shared

    # 提前 accept WebSocket（客户端无需等待后端初始化）
    await websocket.accept()

    # 每个 WebSocket 连接使用独立的工具注册表（会话隔离）
    tool_registry = register_all_tools(
        **shared["tool_params"],
        memory_store=shared["memory"],
    )

    # 同步 MCP 工具到当前会话的工具注册表（同步版本）
    try:
        from backend.modules.mcp.client import McpClientManager
        manager = McpClientManager.get_instance()
        if manager.connected:
            synced = manager.sync_to_registry_sync(tool_registry)
            if synced > 0:
                logger.debug(f"Synced {synced} MCP tools to WebSocket session")
    except Exception as e:
        logger.debug(f"Failed to sync MCP tools to WebSocket: {e}")

    from backend.modules.config.loader import config_loader
    from backend.modules.config.user_config import get_all_user_config
    config = config_loader.config

    from backend.modules.providers.runtime import (
        build_provider_unavailable_message,
        get_provider_runtime_state,
    )

    # 加载当前用户的 provider/model 配置（每个用户独立）
    user_config = await get_all_user_config(user_id) if user_id else {}
    user_providers = user_config.get("providers", {})
    user_model = user_config.get("model", {})

    # 只使用用户自己的 provider 选择 — 不 fallback 到全局 config，
    # 防止管理员 provider 泄露给其他用户。
    user_provider_id = user_model.get("provider")
    if not user_provider_id:
        await websocket.close(
            code=1011,
            reason=(
                "请在设置页配置 AI 提供商后再试。"
                "Configure an AI provider in Settings before chatting."
            ),
        )
        return

    provider_id = user_provider_id
    user_p = user_providers.get(provider_id, {})
    runtime_state = get_provider_runtime_state(
        config,
        provider_id,
        api_key_override=user_p.get("api_key"),
        api_base_override=user_p.get("api_base"),
        enabled_override=user_p.get("enabled"),
    )
    if not runtime_state.selectable:
        # 不 fallback 到全局 provider — 用户隔离
        await websocket.close(
            code=1011,
            reason=build_provider_unavailable_message(
                provider_id,
                runtime_state.reason,
                compact=True,
            ),
        )
        return

    provider = create_provider(
        api_key=runtime_state.api_key or None,
        api_keys=runtime_state.api_keys or None,
        api_base=runtime_state.api_base,
        default_model=user_model.get("model") or config.model.model,
        api_mode=config.model.api_mode,
        timeout=120.0,
        max_retries=3,
        provider_id=provider_id,
    )

    agent_loop = AgentLoop(
        provider=provider,
        workspace=shared["workspace"],
        tools=tool_registry,
        context_builder=shared["context_builder"],
        subagent_manager=shared["subagent_manager"],
        model=user_model.get("model") or config.model.model,
        max_iterations=user_model.get("max_iterations") or config.model.max_iterations,
        temperature=user_model.get("temperature") or config.model.temperature,
        max_tokens=user_model.get("max_tokens") or config.model.max_tokens,
        thinking_enabled=user_model.get("thinking_enabled", config.model.thinking_enabled),
        user_id=getattr(websocket.app.state, 'user_id', None),
    )

    await handle_websocket(websocket, agent_loop=agent_loop)


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": APP_VERSION}


# 挂载前端静态文件
from backend.utils.paths import APPLICATION_ROOT

frontend_dist = APPLICATION_ROOT / "frontend" / "dist"
if frontend_dist.exists():
    from fastapi.responses import FileResponse
    import mimetypes
    
    # 确保 Windows 上正确识别 JavaScript 模块的 MIME 类型
    mimetypes.add_type("application/javascript", ".js")
    mimetypes.add_type("text/css", ".css")
    mimetypes.add_type("image/svg+xml", ".svg")

    # SPA 路由回退（必须在 StaticFiles 之前注册）
    @app.get("/login")
    async def spa_login():
        return FileResponse(str(frontend_dist / "index.html"))

    @app.get("/setup/{setup_secret}")
    async def spa_setup(setup_secret: str):
        if await get_password_hash():
            raise HTTPException(status_code=404)
        if not has_valid_remote_setup_secret(app, setup_secret):
            raise HTTPException(status_code=404)
        return FileResponse(str(frontend_dist / "index.html"))

    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="static")
