# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**CountBot** is an open-source AI Agent framework and execution hub for Chinese users. It connects LLMs, IM channels, workflows, and external tools into a unified execution pipeline.

**Stack**: FastAPI (backend) + Vue 3 + TypeScript (frontend) + SQLite (database) + Python 3.10+
**Deployment**: Source (`python start_app.py`) or Desktop (PyInstaller-packaged, see releases)
**Ports**: Default 7000 (both `start_app.py` and `start_dev.py`). Configurable via `COUNTBOT_HOST` / `COUNTBOT_PORT`.

## Quick Commands

| Task | Command |
|------|---------|
| Start production | `python start_app.py` (default port: 7000) |
| Start dev (hot reload) | `python start_dev.py` (default port: 7000) |
| Start backend only | `uvicorn backend.app:app --reload --host 0.0.0.0 --port 7000` |
| Backend lint | `flake8 backend/` |
| Run tests | `python -m pytest tests/ -v` |
| Frontend dev | `cd frontend && npm run dev` |
| Frontend build | `cd frontend && npm run build` |
| Frontend lint | `cd frontend && npm run lint` |
| Frontend type-check | `cd frontend && npm run type-check` |
| Frontend unit tests | `cd frontend && npm run test` |
| Install backend deps | `pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/` |
| Create conda env | `conda env create -f environment.yml` |

**Default backend URL**: http://127.0.0.1:7000 (configurable via `COUNTBOT_HOST` / `COUNTBOT_PORT`)
**Frontend dev URL**: http://localhost:5173 (Vite proxies `/api/*` and `/ws` to backend at `http://127.0.0.1:8000` by default; set `COUNTBOT_PORT=8000` or update Vite proxy target to match)

## Startup Flow

`backend/app.py` uses FastAPI `lifespan` context manager. On startup, in order:
1. Initialize DB (SQLAlchemy async engine)
2. Load config from `Setting` table via `ConfigLoader`
3. Resolve workspace path (via `WorkspaceManager`, falls back to `./workspace`)
4. Seed bundled workspace resources
5. Create `ProviderRuntimeState` with `KeyRotator` (round-robin + failover)
6. Create `ChannelManager` + **`await manager.async_init()`** (loads per-user channel configs from DB into memory, does NOT start them)
7. **`await manager.start_dispatch()`** starts only the outbound message dispatcher (channels start on user login, not on boot)
8. Start MCP client manager
9. Start cron scheduler
10. Mount WebSocket endpoint at `/ws/chat`

## Backend Architecture

```
backend/
├── app.py                  # FastAPI entry + lifespan (config, DB, MCP, cron, channels)
├── database.py             # SQLAlchemy async engine + declarative Base + get_db dependency
│
├── api/                    # REST API routers (mounted at /api/*)
│   ├── chat.py             # Chat messages + WebSocket streaming
│   ├── auth.py             # Re-exports router from modules/auth/
│   ├── channels.py         # IM channel CRUD
│   ├── agent_teams.py      # Multi-agent team workflows
│   ├── cron.py             # Scheduled task management
│   ├── mcp.py / wiki.py    # MCP client & Wiki KB management
│   └── ...                 # settings, tools, personalities, skills, memory, tasks, queue, system
│
├── modules/
│   ├── agent/              # Agent core
│   │   ├── loop.py         # AgentLoop: ReAct cycle (LLM → tool → observe → repeat)
│   │   ├── workflow.py     # WorkflowEngine: pipeline / graph / council modes
│   │   ├── context.py      # ContextBuilder: assembles system prompt + history + memory + skills
│   │   ├── memory.py       # MemoryStore: line-based persistent memory
│   │   ├── skills.py       # SkillsLoader: BM25-indexed skill loading from 3 sources
│   │   └── subagent.py     # SubagentManager: spawn & track sub-agents
│   │
│   ├── tools/              # Tool system
│   │   ├── base.py         # Tool ABC: name, description, parameters (JSON Schema), execute
│   │   ├── registry.py     # ToolRegistry: register/execute with contextvars + audit logging
│   │   └── setup.py        # register_all_tools() — single registration entry point
│   │
│   ├── providers/          # LLM provider abstraction (22 providers)
│   │   ├── registry.py     # Provider metadata (api_base, env_key, model list)
│   │   ├── factory.py      # create_provider() → AnthropicProvider or OpenAIProvider
│   │   ├── runtime.py      # ProviderRuntimeState + KeyRotator
│   │   ├── anthropic_provider.py  # Anthropic Messages API
│   │   ├── openai_provider.py     # OpenAI-compatible Chat Completions API
│   │   └── tool_parser.py  # Tool call parsing (Anthropic vs OpenAI format)
│   │
│   ├── messaging/          # Message queue & rate limiting
│   │   ├── enterprise_queue.py # Dedup-aware message queue
│   │   └── rate_limiter.py     # Per-channel rate limiting
│   │
│   ├── channels/           # IM channel adapters
│   │   ├── manager.py      # ChannelManager: loads from UserChannelConfig, user_id-tagged instances
│   │   ├── handler.py      # ChannelMessageHandler: inbound → AgentLoop → outbound (user-scoped sessions)
│   │   ├── base.py         # Channel ABC (send_message, receive, lifecycle hooks)
│   │   ├── feishu_websocket_worker.py # Feishu WS subprocess worker (runs in separate process)
│   │   └── media_utils.py  # Shared media download/conversion utilities
│   │
│   ├── external_agents/    # External coding agent (Claude Code, Codex, OpenCode)
│   │   ├── registry.py     # ExternalAgentRegistry: JSON-config profile management
│   │   ├── base.py         # Adapter ABC + profile/request/result data classes
│   │   ├── routing.py      # Regex-based NL intent extraction for agent routing
│   │   ├── conversation.py # Session mode helpers (stateless/history/native)
│   │   └── adapters/cli.py # CliExternalAgentAdapter via subprocess
│   │
│   ├── session/            # Session & conversation management
│   │   ├── manager.py      # SessionManager: CRUD sessions + messages
│   │   ├── context_service.py # History, summaries, overflow handling
│   │   └── runtime_config.py  # Per-session provider/model overrides
│   │
│   ├── ws/                 # WebSocket streaming & connection management
│   │   ├── connection.py   # ConnectionManager: accept, register, disconnect
│   │   ├── events.py       # websocket_event_loop: message dispatch, agent interaction
│   │   ├── streaming.py    # Streaming response: chunk assembly, tool call notifications
│   │   ├── task_notifications.py # Background task progress push via WS
│   │   └── tool_notifications.py # Real-time tool call status push via WS
│   │
│   └── auth/               # Multi-user auth (PBKDF2, HMAC sessions, rate limiting)
│
├── modules/config/          # Config schema & loader
│   ├── schema.py            # All Pydantic models: AppConfig, PersonaConfig, HeartbeatConfig,
│   │                        #   ChannelsConfig + per-channel account configs (Telegram, QQ, etc.)
│   ├── loader.py            # ConfigLoader: read/write from Setting table via JSON serialization
│   └── user_config.py       # Per-user config storage/retrieval
│
├── models/                 # SQLAlchemy models
│   ├── user.py             # Users (id, username, password_hash, role, is_active)
│   ├── session.py          # Chat sessions
│   ├── message.py          # Messages (session_id, role, content, tool_calls)
│   ├── setting.py          # Key-value config store
│   ├── auth_session.py     # Auth session tokens
│   ├── agent_team.py       # Agent team definitions
│   ├── cron_job.py         # Scheduled job definitions
│   ├── personality.py      # Personalities/profiles
│   ├── tool_conversation.py # Tool conversation history
│   ├── task.py             # Background task tracking
│   └── user_channel_config.py # Per-user channel config
│
└── utils/                  # Logger, paths, network helpers, runtime_env
```

## Frontend Architecture

```
frontend/src/
├── main.ts                 # Entry: Vue 3 + Pinia + Router + i18n
├── App.vue                 # Root: router-view + global overlays
├── api/                    # Axios API client + typed endpoint modules
│   ├── client.ts           # Axios instance with interceptors, retry, timeout
│   ├── endpoints.ts        # Centralized typed API calls (chatAPI, systemAPI, authAPI, etc.)
│   ├── index.ts            # Unified re-exports
│   └── auth.ts             # Auth-specific helpers
├── store/                  # Pinia stores (chat, settings, auth, channels, tools, skills, cron, memory, agentTeams, externalCodingTools)
├── components/             # Reusable components
│   ├── chat/               # ChatHeader, ChatInput, MessageContent, etc.
│   └── ui/                 # UI kit (Button, Modal, Select, Toast, DropZone, etc.)
├── modules/                # Feature modules (chat, settings, mcp, skills, scheduler, teams, wiki, memory)
├── composables/            # Vue composables (useWebSocket, useMarkdown, useTheme, useI18n, etc.)
├── types/                  # TypeScript type definitions
└── i18n/                   # Locale files (zh-CN, en-US — loaded lazily)
```

### Frontend Patterns

- **API layer**: `endpoints.ts` has typed methods for every backend endpoint, using a shared `apiClient` (Axios) from `client.ts`
- **State**: Pinia stores in `store/`, each managing a domain (chat, auth, settings, tools, skills, etc.)
- **Vite proxy**: Dev server proxies `/api/*` → backend at the configured target. If backend is on port 7000 (default for `start_dev.py`), update `vite.config.ts` proxy target accordingly.
- **Path aliases**: `@/` → `src/`, `@components/`, `@modules/`, `@store/`, `@api/`, `@composables/`, `@i18n/`, `@assets/`

## Key Data Flow

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

## Important Patterns & Conventions

### Tool Execution
```python
class MyTool(Tool):
    @property
    def name(self) -> str: ...
    @property
    def description(self) -> str: ...
    @property
    def parameters(self) -> Dict: ...  # JSON Schema
    async def execute(self, **kwargs) -> str: ...
```
- Tools return `str` results (not print)
- Register in `backend/modules/tools/setup.py` → `register_all_tools()`
- `ToolRegistry` uses `contextvars` for async-safe session/channel propagation
- Audit logging is auto-enabled via `file_audit_logger.py`

### Provider System
- 20+ LLM providers in `registry.py`, auto-detected by `create_provider(provider_id)`
- Two base implementations: `AnthropicProvider` (Messages API) and `OpenAIProvider` (Chat Completions API)
- `KeyRotator` handles round-robin key rotation + 401/403 failover
- Per-session provider overrides via `SessionRuntimeConfig`

### Auth (Multi-User)
- Users table with roles: `admin`, `operator`, `user`
- PBKDF2 password hashing, HMAC session tokens
- Rate-limited login: 5 attempts / 15 min window → 15 min lockout
- Cookie-based auth (`CountBot_token`) + Bearer token fallback
- `request.state.user` populated by `RemoteAuthMiddleware` for protected routes
- `get_current_user_id()` / `get_effective_user_id()` Depends helpers for route-level user extraction
- `set_current_user_context(id, username, role)` in `modules/auth/context.py` propagates user context via `contextvars` into non-HTTP layers (WebSocket, channel handlers, tools)
- **Admin sudo mode**: `POST /api/auth/switch?target_user_id=N` creates a `CountBot_switch_token` cookie. Use `get_effective_user_id()` in user-scoped endpoints (channels, sessions) — `get_current_user_id()` in admin-only endpoints to prevent escalation.

### Config Storage
- **Global config** in SQLite `Setting` table (key-value). `ConfigLoader` reads/writes nested dicts via JSON serialization (keys like `config.model.provider`). Pydantic v2 `AppConfig` model in `modules/config/schema.py`.
- **Per-user channel config** in `UserChannelConfig` table. Each row has `user_id`, `channel`, `account_id`, `config_json` (JSON blob), `is_enabled`. Pydantic config classes (e.g., `WeChatConfig`) rebuilt from JSON via `_lazy_load_config_classes()` in `manager.py`.
- Per-session overrides stored on Session model, merged via `resolve_session_runtime_config()`.

### Skills System
- Markdown files with YAML frontmatter, loaded from 3 sources (descending priority):
  1. `workspace/skills/` (user-managed, editable)
  2. Application root `workspace/skills/` (bundled)
  3. `~/.openclaw/skills/` + `~/skills/` (read-only)
- BM25-indexed by name + description + tags, top_k=3 injected into context
- Always-loaded skills: identity, security rules, etc.
- Add new: create `workspace/skills/my-skill/SKILL.md` with frontmatter (name, description, always/auto_load)

### WebSocket
- Chat streaming at `/ws/chat` (WebSocket endpoint)
- Connection managed via `ConnectionManager` in `ws/connection.py`
- Heartbeat mechanism with configurable intervals, exponential backoff reconnect
- Event loop in `ws/events.py` dispatches messages → AgentLoop → streaming responses
- Tool call notifications pushed in real-time via `ws/tool_notifications.py`
- Background task progress pushed via `ws/task_notifications.py`

### Tools
- ~15 tools registered in `register_all_tools()` (filesystem, shell, web, sub-agent, etc.), some conditionally based on available dependencies
- `ExecTool`: auto-detects `CountBot` conda env for subprocess Python, blocks dangerous commands
- `WebFetchTool`: three stealth levels (basic/stealth/max-stealth with Playwright)
- `ExternalCodingAgentTool`: adapters for Claude Code CLI, Codex, OpenCode
- `MemoryTool`: unified memory write/search/read
- `FileSearchTool`: semantic search via Whoosh index

### Channels (IM) — Multi-Tenant
- Abstract base class `Channel` in `modules/channels/base.py`
- Implemented: WeChat, Feishu, DingTalk, QQ, Telegram, Discord, WeCom, Weibo, XiaoZhi AI
- Each channel: `send_message()`, `receive_loop()`, lifecycle hooks

#### Channel Isolation Architecture
- Configs stored in **`UserChannelConfig`** table (per-user rows with `user_id`, `channel`, `account_id`, `config_json`, `is_enabled`)
- **`ChannelManager.__init__(bus, db_session_factory)`** — creates empty manager. Call **`await manager.async_init()`** to load enabled configs from DB into `self.channels` dict (keyed as `f"{channel}:{account_id}:{user_id}"`)
- **Lifecycle**: On server boot, only the outbound dispatcher starts (`start_dispatch()`). Channels start when the owning user logs in (`start_user_channels(user_id)`) and stop on logout (`stop_user_channels(user_id)`). Explicit save/delete of channel config triggers a full reload (`_restart_channel_manager` → `start_all()`)
- Each instance tagged with `channel._user_id` and stored in `self.channels[instance_key]`
- **Config class registry**: `_lazy_load_config_classes()` lazily imports Pydantic config classes (TelegramConfig, QQConfig, etc.) from `schema.py` to rebuild config objects from `UserChannelConfig.config_json`
- **Duplicate physical bot detection**: `async_init()` checks unique fields (e.g., `login_bot_id` for WeChat) across users and skips duplicates
- **Outbound routing**: `_resolve_outbound_channel()` uses `msg.metadata["user_id"]` + `account_id` to route to the correct user's instance
- **Status filtering**: `get_status(user_id=None)` skips instances not belonging to the specified user
- **Hot-reload**: Save/delete channel config via API → `_restart_channel_manager_if_needed(request)` → creates new manager, calls `async_init()`, stops old, swaps, then starts all channels via `start_all()`
- **User context propagation**: `ChannelMessageHandler.handle_message()` reads `msg.metadata["user_id"]` and calls `set_current_user_context(user_id, ...)` to scope AgentLoop sessions per user

### Code Conventions
- All backend Python is `async/await` throughout
- `contextvars` used for async-safe request context propagation (`backend/modules/auth/context.py`)
- Logger: `from loguru import logger`
- Database: SQLAlchemy async session via `get_db()` dependency
- WorkspaceValidator prevents path traversal in file operations
- `ExecTool` blocks dangerous commands (`rm -rf`, `shutdown`, etc.) by default
- `ExecTool` auto-detects `CountBot` conda environment for subprocess Python
- Audit logging enabled by default, writes to `data/tool_audit.log`

## Common Development Tasks

**Add a new tool**: Create `backend/modules/tools/my_tool.py` → inherit `Tool` → register in `setup.py`
**Add a new IM channel**: Create `modules/channels/my_channel.py` → inherit `Channel` → add Pydantic config in `schema.py` → register channel class + config class in `manager.py` (`_CHANNEL_REGISTRY` + `_CHANNEL_CONFIG_CLASSES`)
**Add a new LLM provider**: Create `modules/providers/my_provider.py` → inherit `Provider` → register in `registry.py`
**Add a new API route**: Create `backend/api/my_routes.py` → create APIRouter → mount in `app.py`
**Add a new DB model**: Create `backend/models/my_model.py` → import in `models/__init__.py` → auto-created on startup
**Add a frontend module**: Create `frontend/src/modules/my-module/` with Vue components + add route in `router/index.ts`
**MCP server**: Configured via UI or directly in DB. Supports stdio, SSE, streamable_http. Tools auto-registered as `mcp_{server}_{tool_name}`.

## Runtime Data (`data/`)

```
data/
├── countbot.db          # SQLite database (auto-created on first startup)
├── logs/                # Application logs
└── audit_logs/          # Tool execution audit logs
```

## Workspace (`workspace/`)

```
workspace/
├── skills/              # User-managed skills
├── memory/              # Persistent agent memory files
├── wiki/                # Wiki knowledge base articles
├── uploads/             # File uploads from chat
└── temp/                # Temporary workspace files
```