# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**CountBot** is an open-source AI Agent framework and execution hub for Chinese users. It connects LLMs, IM channels, workflows, and external tools into a unified execution pipeline.

**Stack**: FastAPI (backend) + Vue 3 + TypeScript (frontend) + SQLite (database) + Python 3.8+

## Quick Commands

| Task | Command |
|------|---------|
| Start production | `python start_app.py` |
| Start dev (hot reload) | `python start_dev.py` or `uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000` |
| Start desktop app | `python start_desktop.py` |
| Lint (backend) | `flake8 backend/` |
| Run all tests | `python -m pytest tests/ -v` |
| Run single test | `python -m pytest tests/test_file.py::test_func -v` |
| Frontend dev | `cd frontend && npm run dev` |
| Frontend build | `cd frontend && npm run build` |
| Frontend lint | `cd frontend && npm run lint` |

**Default URL**: http://127.0.0.1:8000
**Frontend dev URL**: http://localhost:5173 (proxies API to backend)

**Environment overrides**: `COUNTBOT_HOST` / `COUNTBOT_PORT`

### CountBot 统一环境

**所有 Python 脚本默认在 `CountBot` conda 环境中运行。** `ExecTool._build_subprocess_env()` 会自动检测 CountBot 环境并优先使用其 Python。如果环境不存在，会自动通过 `setup_env.py` 创建。

```bash
# 手动创建
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
├── database.py               # SQLAlchemy async engine + declarative Base
│
├── api/                      # REST API routers (16 routers)
│   ├── chat.py               # Chat messages + AgentLoop via WebSocket
│   ├── auth.py               # Login / setup / logout / change-password
│   ├── tools.py              # Tool execution endpoints
│   ├── channels.py           # IM channel CRUD
│   ├── agent_teams.py        # Multi-agent team workflows
│   └── mcp.py / wiki.py      # MCP client & Wiki KB management
│
├── modules/
│   ├── agent/                # Agent core
│   │   ├── loop.py           # AgentLoop: ReAct cycle (LLM → tool → observe → repeat)
│   │   ├── workflow.py       # WorkflowEngine: pipeline / graph / council modes
│   │   ├── context.py        # ContextBuilder: assembles system prompt + history + skills
│   │   ├── memory.py         # MemoryStore: line-based persistent memory
│   │   ├── skills.py         # SkillsLoader: BM25-indexed skill loading from 3 sources
│   │   └── subagent.py       # SubagentManager: spawn & track sub-agents
│   │
│   ├── tools/                # Tool system (14+ tools)
│   │   ├── base.py           # Tool ABC (name, description, parameters, execute)
│   │   ├── registry.py       # ToolRegistry: register/execute/audit logging
│   │   ├── filesystem.py     # ReadFileTool, WriteFileTool, EditFileTool, ListDirTool
│   │   ├── shell.py          # ExecTool (with safety guards, auto CountBot env resolution)
│   │   ├── web.py            # WebFetchTool (basic / stealth / max-stealth)
│   │   ├── workflow_tool.py  # Expose WorkflowEngine as a tool
│   │   ├── spawn.py          # Sub-agent spawning tool
│   │   └── memory_tool.py    # Unified memory write/search/read
│   │
│   ├── channels/             # IM channel adapters (WeChat, Feishu, DingTalk, QQ, Telegram, etc.)
│   │   ├── manager.py        # ChannelManager: lifecycle for all channels
│   │   ├── handler.py        # ChannelMessageHandler: inbound → AgentLoop → outbound
│   │   └── base.py           # Channel ABC
│   │
│   ├── providers/            # LLM provider abstraction
│   │   ├── registry.py       # 23 providers registered with metadata (api_base, env_key, model)
│   │   ├── factory.py        # create_provider() → AnthropicProvider or OpenAIProvider
│   │   ├── runtime.py        # ProviderRuntimeState + KeyRotator (round-robin + failover)
│   │   └── anthropic.py / openai.py  # Provider implementations
│   │
│   ├── session/              # Session & conversation management
│   │   ├── manager.py        # SessionManager: CRUD sessions + messages
│   │   ├── context_service.py# ConversationContextService: history, summaries, context maint.
│   │   ├── message_context.py# Message context JSON utilities (attachments, reasoning)
│   │   └── runtime_config.py # SessionRuntimeConfig: per-session provider/model overrides
│   │
│   ├── config/               # Configuration (Pydantic → DB serialization)
│   │   ├── loader.py         # ConfigLoader: read/write nested config from SQLite
│   │   └── schema.py         # AppConfig: providers, model, workspace, security, channels, etc.
│   │
│   ├── mcp/                  # MCP client (multi-server, health check, tool sync)
│   │   └── client.py         # McpClientManager (singleton) + MCPToolWrapper
│   │
│   ├── wiki/                 # Wiki knowledge base (BM25 + jieba tokenizer)
│   ├── cron/                 # Scheduled tasks (scheduler, executor, service)
│   ├── auth/                 # Auth middleware + router + utils (PBKDF2, HMAC sessions)
│   └── external_agents/      # External coding agent adapters (Claude Code, Codex, OpenCode)
│
├── models/                   # SQLAlchemy models (Session, Message, AgentTeam, Setting, etc.)
└── utils/                    # Logger, paths, network, runtime_env
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

### Configuration Storage

All config stored in SQLite `settings` table with keys like `config.model.provider`, `config.workspace.path`. ConfigLoader reads/writes nested dicts via JSON serialization. Per-session overrides stored on the Session model, merged via `resolve_session_runtime_config()`.

### Provider System

- 23 providers registered in `registry.py` (Anthropic, OpenAI, DeepSeek, Zhipu, Qwen, etc.)
- Two implementations: `AnthropicProvider` (Messages API) and `OpenAIProvider` (Chat Completions API)
- `KeyRotator` supports round-robin key rotation + automatic failover on 401/403
- `create_provider()` auto-detects which implementation to use based on provider ID

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

# Tools return str (not print)
registry = ToolRegistry()
registry.register(MyTool())
result = await registry.execute("my_tool", {"param": "value"})
```

## Frontend Architecture

```
frontend/src/
├── main.ts                   # Entry: Vue 3 + Pinia + Router + i18n
├── App.vue                   # Root: router-view + global overlays
├── api/                      # Axios API client (typed endpoints)
├── assets/styles/            # Design system: light/dark themes, tokens, components
├── components/
│   ├── chat/                 # Chat UI (ChatHeader, ChatInput, MessageContent, etc.)
│   └── ui/                   # Generic UI kit (Button, Modal, Select, Toast, etc.)
├── composables/              # Vue composables (useWebSocket, useMarkdown, useTheme, etc.)
├── modules/
│   ├── chat/                 # ChatWindow, MessageList, MessageItem, timeline, streaming
│   ├── settings/             # Full settings UI (model, provider, persona, channels, etc.)
│   ├── mcp/                  # MCP panel + server editor
│   ├── skills/               # Skills library + editor
│   ├── scheduler/            # Cron manager
│   ├── teams/                # Multi-agent team config + dependency graph
│   ├── wiki/                 # Wiki panel + editor
│   └── memory/               # Memory viewer
├── store/                    # Pinia stores (chat, settings, skills, tools, etc.)
├── types/                    # TypeScript type definitions
└── i18n/                     # Locale files (zh-CN, en-US)
```

## Skills System

Skills are markdown files with YAML frontmatter, loaded from 3 sources (priority order):
1. **workspace** — `workspace/skills/` (user-managed)
2. **builtin** — `APPLICATION_ROOT/workspace/skills/` (shipped with app)
3. **OpenClaw** — `~/.openclaw/skills/` + `~/skills/` (read-only, import to workspace to edit)

Each skill directory contains `SKILL.md` (metadata + instructions), optionally `scripts/` (Python scripts), `config.json`, and `references/`.

Skills are BM25-indexed by name + description + tags. The agent only injects relevant skills (top_k=3) into context, plus always-loaded skills (identity, security rules, etc.).

**Add a new skill**: Create `workspace/skills/my-skill/SKILL.md` with YAML frontmatter (name, description, always/auto_load). Optionally add `scripts/` for executable content.

## Common Development Tasks

**Add a new tool**:
1. Create `backend/modules/tools/my_tool.py`, inherit `Tool`
2. Implement `name`, `description`, `parameters` (JSON Schema), `async execute(**kwargs) -> str`
3. Register in `backend/modules/tools/setup.py` → `register_all_tools()`

**Add a new IM channel**:
1. Create `backend/modules/channels/my_channel.py`, inherit `Channel`
2. Implement message receive/send, connection management
3. Register in `backend/modules/channels/manager.py`
4. Add config model in `backend/modules/config/schema.py`

**Add a new LLM provider**:
1. Create `backend/modules/providers/my_provider.py`, inherit `Provider`
2. Register in `backend/modules/providers/registry.py` with metadata

**MCP server config**: Configured via UI (settings → MCP) or directly in DB. Supports stdio, SSE, and streamable_http transports. Tools are auto-discovered and registered as `mcp_{server}_{tool_name}`.

## Important Notes

- All backend code uses `async/await`
- `contextvars` used for async-safe session/channel context propagation in ToolRegistry
- Audit logging writes to `data/tool_audit.log` — enabled by default
- Workspace path validated by `WorkspaceValidator` to prevent path traversal
- Dangerous shell commands (`rm -rf`, `shutdown`, etc.) blocked by default
- `ExecTool` auto-detects CountBot conda environment and prefers its Python
- Authentication: single-user model, cookie-based sessions, rate-limited login (5/15min → 15min lockout)
- All config is Pydantic v2 models serialized to SQLite `Setting` table