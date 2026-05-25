# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**CountBot** is an open-source AI Agent framework and execution hub for Chinese users. It connects LLMs, IM channels, workflows, and external tools into a unified execution pipeline.

**Stack**: FastAPI (backend) + Vue 3 + TypeScript (frontend) + SQLite (database) + Python 3.8+
**Deployment**: Source (`python start_app.py`) or Desktop (PyInstaller-packaged, see releases)

## Quick Commands

| Task | Command |
|------|---------|
| Start production | `python start_app.py` |
| Start dev (hot reload) | `python start_dev.py` or `uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000` |
| Start desktop app | `python start_desktop.py` |
| Lint (backend) | `flake8 backend/` |
| Run tests | `python -m pytest tests/ -v` |
| Frontend dev | `cd frontend && npm run dev` |
| Frontend build | `cd frontend && npm run build` |
| Frontend lint | `cd frontend && npm run lint` |
| Frontend type-check | `cd frontend && npm run type-check` |
| Install backend deps | `pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/` |
| Create conda env | `conda env create -f environment.yml` |

**Default URL**: http://127.0.0.1:8000
**Frontend dev URL**: http://localhost:5173 (proxies API to backend)
**Environment overrides**: `COUNTBOT_HOST` / `COUNTBOT_PORT`

### CountBot 统一环境

**所有 Python 脚本默认在 `CountBot` conda 环境中运行。** `ExecTool._build_subprocess_env()` 会自动检测 CountBot 环境并优先使用其 Python。如果环境不存在，会自动通过 `setup_env.py` 创建。

```bash
conda env create -f environment.yml
conda activate CountBot
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

# 初始化 UI 后需在设置页面配置 LLM Provider API Key 才能对话
```

详细说明见 `README_COUNTBOT_ENV.md`。

## Backend Architecture

```
backend/
├── app.py                    # FastAPI entry (lifespan manages: config, DB, MCP, cron, channels)
├── database.py               # SQLAlchemy async engine (aiosqlite) + declarative Base
├── version.py                # APP_VERSION
│
├── api/                      # REST API routers (mounted at /api/*)
│   ├── chat.py               # Chat messages + AgentLoop via WebSocket streaming
│   ├── auth.py               # Login / setup / logout / change-password (re-exports auth router)
│   ├── tools.py              # Tool execution endpoints
│   ├── channels.py           # IM channel CRUD (multi-user)
│   ├── agent_teams.py        # Multi-agent team workflows
│   ├── cron.py               # Scheduled task management
│   ├── mcp.py / wiki.py      # MCP client & Wiki KB management
│   ├── settings.py           # App configuration CRUD
│   ├── personalities.py      # Personality/profile management
│   ├── skills.py             # Skills library management
│   ├── memory.py             # Memory viewer/management
│   ├── tasks.py              # Background task management (queue status, cancel)
│   ├── queue.py              # Message queue management
│   └── system.py             # System info/status (disk, memory, version)
│
├── modules/
│   ├── agent/                # Agent core
│   │   ├── loop.py           # AgentLoop: ReAct cycle (LLM → tool → observe → repeat)
│   │   │                     #   Key rotation: retries on 401/429 with _is_key_rotation_eligible_error()
│   │   ├── workflow.py       # WorkflowEngine: pipeline / graph / council modes
│   │   ├── context.py        # ContextBuilder: system prompt + history + memory + BM25 skills
│   │   ├── memory.py         # MemoryStore: line-based persistent memory files
│   │   ├── skills.py         # SkillsLoader: BM25-indexed from workspace/builtin/OpenClaw
│   │   ├── subagent.py       # SubagentManager: spawn & track sub-agents
│   │   ├── heartbeat.py      # HeartbeatService: idle-time greetings, quiet hours
│   │   └── task_manager.py   # CancellationToken + task lifecycle
│   │
│   ├── tools/                # Tool system
│   │   ├── base.py           # Tool ABC (name, description, parameters JSON Schema, execute)
│   │   ├── registry.py       # ToolRegistry: register/execute with contextvars + audit logging
│   │   ├── setup.py          # register_all_tools() — single registration entry point (20+ tools)
│   │   ├── filesystem.py     # ReadFileTool, WriteFileTool, EditFileTool, ListDirTool, DeleteFileTool
│   │   ├── shell.py          # ExecTool (auto CountBot env, blocks dangerous commands)
│   │   ├── web.py            # WebFetchTool (basic / stealth / max-stealth with Playwright)
│   │   ├── workflow_tool.py  # Expose WorkflowEngine as a tool
│   │   ├── spawn.py          # Sub-agent spawning tool
│   │   ├── memory_tool.py    # Unified memory write/search/read
│   │   ├── screenshot.py     # Screenshot capture tool
│   │   ├── send_media.py     # Send media/files tool
│   │   ├── file_search.py    # Semantic/local file search (Whoosh index)
│   │   ├── monitoring.py     # System monitoring tool
│   │   ├── conversation_history.py # Conversation history retrieval tool
│   │   ├── execution_context.py    # Execution context inspection tool
│   │   ├── file_audit_logger.py    # File operation audit logging
│   │   ├── external_coding_agent.py # External agent adapter (Claude Code/Codex/OpenCode)
│   │   └── xiaozhi_message.py      # XiaoZhi AI message tool
│   │
│   ├── channels/             # IM channel adapters
│   │   ├── manager.py        # ChannelManager: lifecycle for all channels, auto-reconnect
│   │   ├── handler.py        # ChannelMessageHandler: inbound → AgentLoop → outbound
│   │   ├── base.py           # Channel ABC + InboundMessage / OutboundMessage
│   │   ├── wechat.py         # WeChat (via ClawBot)
│   │   ├── feishu.py         # Feishu/Lark
│   │   ├── dingtalk.py       # DingTalk
│   │   ├── qq.py             # QQ (with optional OSS uploader)
│   │   ├── telegram.py       # Telegram
│   │   ├── wecom.py          # WeCom/企业微信
│   │   ├── weibo.py          # Weibo
│   │   └── xiaozhi.py        # XiaoZhi AI
│   │
│   ├── providers/            # LLM provider abstraction
│   │   ├── registry.py       # 23 providers registered with metadata (api_base, env_key, model)
│   │   ├── factory.py        # create_provider() → AnthropicProvider or OpenAIProvider
│   │   ├── runtime.py        # ProviderRuntimeState + KeyRotator (round-robin, 401/403 failover)
│   │   ├── anthropic_provider.py  # Anthropic Messages API implementation
│   │   ├── openai_provider.py     # OpenAI Chat Completions API (also used by DeepSeek, Qwen, Zhipu, etc.)
│   │   ├── thinking_profiles.py   # Provider-specific thinking/reasoning field mappings
│   │   └── tool_parser.py         # Tool call response parsing (Anthropic vs OpenAI format)
│   │
│   ├── messaging/            # Message queue
│   │   ├── enterprise_queue.py   # Multi-priority queue (URGENT/HIGH/NORMAL/LOW), dedup, DLQ, retry
│   │   └── rate_limiter.py       # Per-channel rate limiting
│   │
│   ├── session/              # Session & conversation management
│   │   ├── manager.py        # SessionManager: CRUD sessions + messages
│   │   ├── context_service.py# ConversationContextService: history, summaries, context maint.
│   │   ├── message_context.py# Message context JSON utilities (attachments, reasoning)
│   │   └── runtime_config.py # SessionRuntimeConfig: per-session provider/model overrides
│   │
│   ├── config/               # Configuration (Pydantic → DB serialization)
│   │   ├── loader.py         # ConfigLoader: read/write nested config from SQLite `Setting` table
│   │   └── schema.py         # AppConfig: provider, model, workspace, security, channels, etc.
│   │
│   ├── auth/                 # Multi-user auth (PBKDF2, HMAC sessions, rate limiting, roles)
│   │   ├── middleware.py     # RemoteAuthMiddleware: cookie/Bearer auth, local auto-login
│   │   ├── dependencies.py   # get_current_user_id (from request.state), get_current_user, etc.
│   │   ├── router.py         # Login/setup/logout/change-password endpoints
│   │   ├── utils.py          # Password hashing (PBKDF2), session token HMAC, validate
│   │   └── context.py        # Contextvars for async-safe user context propagation
│   │
│   ├── mcp/                  # MCP client (multi-server, health check, tool sync)
│   ├── wiki/                 # Wiki knowledge base (BM25 + jieba, LRU cache)
│   ├── cron/                 # Scheduled tasks (scheduler, executor, service)
│   ├── external_agents/      # External coding agent adapters (Claude Code CLI, Codex, OpenCode)
│   ├── websocket/            # MCP status broadcast to connected WebSocket clients
│   └── workspace/            # WorkspaceManager (path resolution, resource seeding, tray icon)
│
├── models/                   # SQLAlchemy models
│   ├── user.py               # Users (id, username, password_hash, role, is_active)
│   ├── session.py            # Chat sessions
│   ├── message.py            # Messages (session_id, role, content, tool_calls)
│   ├── setting.py            # Key-value config store
│   ├── auth_session.py       # Auth session tokens
│   ├── agent_team.py         # Agent team definitions
│   ├── cron_job.py           # Scheduled job definitions
│   ├── personality.py        # Personalities/profiles
│   ├── tool_conversation.py  # Tool conversation history
│   ├── task.py               # Background task tracking
│   └── user_channel_config.py # Per-user channel config
│
└── utils/                    # Logger (loguru), paths (APPLICATION_ROOT), runtime_env
```

```
ws/                          # Backward-compat WebSocket connection handler (imported by app.py)
├── connection.py            # handle_websocket(): auth → accept → event loop
└── events.py                # Message dispatch, streaming, tool notifications
```

### Key Data Flow

```
User message (WebSocket / IM channel)
  → ChannelMessageHandler
  → AgentLoop.process_message()
    → ContextBuilder.build_messages()  (history + memory + BM25-filtered skills)
    → LLM chat_stream()  (streaming chunks)
      → If tool call: execute_tool() → ToolRegistry.execute() → return result
      → Append tool result → loop again
    → Final content → yield
  → Channel.send() / WebSocket → User
```

### Startup Flow (backend/app.py lifespan)

1. Initialize DB (SQLAlchemy async engine + aiosqlite), load config from `Setting` table
2. Resolve workspace path (WorkspaceManager, falls back to `./workspace`), seed bundled resources
3. Create shared components via `_create_shared_components()`:
   - Provider, ContextBuilder, MemoryStore, SkillsLoader, SubagentManager, ToolRegistry (20+ tools)
4. Create EnterpriseMessageQueue (dedup, 4-level priority) + RateLimiter
5. Create ChannelMessageHandler (inbound → AgentLoop → outbound)
6. Create ChannelManager, start enabled channels in background
7. Initialize MCP client manager (non-blocking, if enabled)
8. Initialize cron scheduler + heartbeat service
9. Mount WebSocket endpoint at `/ws/chat` (per-connection auth, provider creation, AgentLoop)

### Configuration Storage

- All config stored in SQLite `settings` table with keys like `config.model.provider`, `config.workspace.path`
- `ConfigLoader` reads/writes nested dicts via JSON serialization
- Pydantic v2 `AppConfig` model in `modules/config/schema.py`
- Per-session overrides stored on Session model, merged via `resolve_session_runtime_config()`

### Provider System

- Two base classes: `AnthropicProvider` (Messages API) and `OpenAIProvider` (Chat Completions API)
- 23+ providers in `registry.py`, auto-detected by `create_provider(provider_id)`
- `KeyRotator`: round-robin key rotation + failover on 401/403/429
- `_is_key_rotation_eligible_error()` in `loop.py` decides which errors trigger rotation
- Per-session overrides via `SessionRuntimeConfig`

### Auth (Multi-User)

- Users table with roles: `admin`, `operator`, `user`
- PBKDF2 password hashing, HMAC session tokens
- Rate-limited login: 5 attempts / 15 min → 15 min lockout
- Middleware populates `request.state.user_id` + `request.state.user` for protected routes
- Local requests auto-login as first active admin if no cookie present
- `contextvars` in `auth/context.py` for non-HTTP code paths (channels, websocket)

### WebSocket

- `/ws/chat` endpoint in `app.py` handles per-connection auth + AgentLoop creation
- Each WebSocket gets an isolated tool registry (session isolation)
- MCP tools synced to each WebSocket session on connect
- `modules/websocket/broadcast.py` broadcasts MCP status changes to all active WS clients

### Skills System

- Markdown files with YAML frontmatter, BM25-indexed by name + description + tags
- 3 sources (descending priority): `workspace/skills/` → bundled → `~/.openclaw/skills/` + `~/skills/`
- top_k=3 injected into context per turn; always-loaded skills (identity, security rules) exempt
- Add new: create `workspace/skills/my-skill/SKILL.md` with frontmatter

### Tool Execution Pattern

```python
class MyTool(Tool):
    @property
    def name(self) -> str: ...
    @property
    def description(self) -> str: ...
    @property
    def parameters(self) -> Dict: ...  # JSON Schema
    async def execute(self, **kwargs) -> str: ...

# Register in backend/modules/tools/setup.py → register_all_tools()
# Tools return str (not print), ToolRegistry uses contextvars for async-safe context
```

## Frontend Architecture

```
frontend/src/
├── main.ts                   # Entry: Vue 3 + Pinia + Router + i18n
├── App.vue                   # Root: router-view + global overlays
├── api/                      # Axios API client (client.ts + endpoints.ts)
├── assets/styles/            # Design system: light/dark themes, tokens, SCSS
├── components/
│   ├── chat/                 # ChatHeader, ChatInput, MessageContent, etc.
│   └── ui/                   # UI kit (Button, Modal, Select, Toast, DropZone, etc.)
├── composables/              # useWebSocket, useMarkdown, useTheme, useI18n, etc.
├── modules/                  # Feature modules (chat, settings, mcp, skills, scheduler, teams, wiki, memory)
├── store/                    # Pinia stores (chat, settings, skills, tools, auth, etc.)
├── types/                    # TypeScript type definitions
└── i18n/                     # Locale files (zh-CN, en-US, loaded lazily)
```

### Frontend Patterns

- **API layer**: `api/endpoints.ts` has typed methods per backend endpoint, shared `apiClient` (Axios) from `client.ts`
- **State**: Pinia stores in `store/`, each managing a domain
- **Vite proxy**: Dev server proxies `/api/*` → `http://127.0.0.1:8000` and `/ws` → WebSocket
- **Path aliases**: `@/` → `src/`, plus `@components/`, `@modules/`, `@store/`, `@api/`, `@composables/`, `@i18n/`, `@assets/`
- **Routing**: `router/index.ts` with lazy-loaded route components

## Workspace and Runtime Data

```
data/
├── countbot.db          # SQLite database (auto-created on first startup)
├── logs/                # Application logs (loguru)
└── audit_logs/          # Tool execution audit logs (tool_audit.log)

workspace/
├── skills/              # User-managed skills (15+ built-in skills)
├── memory/              # Persistent agent memory files
├── wiki/                # Wiki knowledge base articles
├── uploads/             # File uploads from chat
├── temp/                # Temporary workspace files
├── AI_QUICK_REFERENCE.md   # Loaded into agent context — CountBot architecture reference
├── TOOLS_REFERENCE.md      # Loaded into agent context — tool usage reference
├── LEARNING_PATH.md        # Loaded into agent context — learning roadmaps
└── external_coding_tools.json  # External agent config (Claude Code, Codex, OpenCode paths)
```

## Important Patterns

### Common Development Tasks

| Task | Steps |
|------|-------|
| Add new tool | Create `backend/modules/tools/my_tool.py` → inherit `Tool` → register in `setup.py:register_all_tools()` |
| Add new IM channel | Create `modules/channels/my_channel.py` → inherit `Channel` → add to `manager.py:_CHANNEL_REGISTRY` |
| Add new LLM provider | Create `modules/providers/my_provider.py` → inherit `Provider` → register in `registry.py` |
| Add new API route | Create `backend/api/my_routes.py` → create APIRouter → mount in `app.py` |
| Add new DB model | Create `backend/models/my_model.py` → import in `models/__init__.py` (auto-created on startup) |
| Add frontend module | Create `frontend/src/modules/my-module/` → add route in `router/index.ts` |
| Add new skill | Create `workspace/skills/my-skill/SKILL.md` with YAML frontmatter (name, description, always/auto_load) |

### Code Conventions

- All backend Python is `async def` with `async/await`
- `contextvars` for async-safe request context propagation (auth, session, channel in ToolRegistry)
- Logger: `from loguru import logger`
- Database: SQLAlchemy async sessions via `get_db()` dependency
- Path traversal prevented by `WorkspaceValidator`
- `ExecTool` auto-detects `CountBot` conda env; blocks dangerous commands (`rm -rf`, `shutdown`, etc.)
- Audit logging writes to `data/tool_audit.log` (enabled by default)
- `_create_shared_components()` builds provider, context, tools once; shared by channels and WebSocket
- WebSocket creates per-connection AgentLoop + isolated tool registry for session isolation

### MCP

- Configured via UI or directly in DB. Supports stdio, SSE, streamable_http transports
- Tools auto-registered as `mcp_{server}_{tool_name}`
- Status broadcast to all WebSocket clients via `modules/websocket/broadcast.py`

### External Coding Agents

- Configured in `workspace/external_coding_tools.json`
- Adapters for Claude Code CLI, Codex, OpenCode in `modules/external_agents/`
- Channel-level routing: `routing_mode = "ai"` (default) or `"direct"` (bypass CountBot agent)