# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**CountBot** is an open-source AI Agent framework and execution hub for Chinese users. It connects LLMs, IM channels, workflows, and external tools into a unified execution pipeline.

**Stack**: FastAPI (backend) + Vue.js (frontend) + SQLite (database) + Python 3.8+

## Quick Commands

| Task | Command |
|------|---------|
| Install dependencies | `pip install -r requirements.txt` |
| Install (China mirror) | `pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/` |
| Start production | `python start_app.py` |
| Start dev (hot reload) | `python start_dev.py` or `uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000` |
| Start desktop app | `python start_desktop.py` |
| Lint | `flake8 backend/` |

**Default URL**: http://127.0.0.1:8000

Environment overrides: `COUNTBOT_HOST` / `COUNTBOT_PORT`

## Architecture

```
backend/
├── app.py                    # FastAPI app entry (lifespan manages all components)
├── database.py               # SQLAlchemy async engine + Base model
├── api/                      # REST API routes (16 routers)
│   ├── chat.py               # Chat messages + AgentLoop invocation
│   ├── auth.py               # Login / setup / logout / change-password
│   ├── tools.py              # Tool execution endpoints
│   ├── channels.py           # IM channel management
│   ├── agent_teams.py        # Multi-agent team workflows
│   ├── mcp.py / wiki.py      # MCP client & Wiki knowledge base
│   └── ...
├── modules/                  # Core business logic
│   ├── agent/                # Agent core: loop, workflow, memory, context, skills
│   │   ├── loop.py           # AgentLoop: ReAct cycle (LLM → tool → observe → repeat)
│   │   ├── workflow.py       # WorkflowEngine: pipeline / graph / council modes
│   │   ├── memory.py         # MemoryStore: line-based persistent memory
│   │   ├── context.py        # ContextBuilder: assembles messages for LLM
│   │   └── subagent.py       # SubagentManager: spawns & tracks sub-agents
│   ├── tools/                # Tool system (14+ tools)
│   │   ├── base.py           # Tool abstract base class (name, description, parameters, execute)
│   │   ├── registry.py       # ToolRegistry: register / execute / audit logging
│   │   ├── filesystem.py     # ReadFileTool, WriteFileTool, EditFileTool, ListDirTool
│   │   ├── shell.py          # ExecTool (with safety guards: deny patterns, workspace restrict)
│   │   ├── web.py            # WebFetchTool (basic / stealth / max-stealth modes)
│   │   ├── workflow_tool.py  # WorkflowTool: exposes WorkflowEngine as a tool
│   │   ├── spawn.py          # SpawnTool: spawn sub-agent as a tool
│   │   ├── memory_tool.py    # MemoryTool: unified write/search/read via action param
│   │   └── ...
│   ├── channels/             # IM channel adapters (WeChat, Feishu, DingTalk, QQ, Telegram, Wecom...)
│   │   ├── manager.py        # ChannelManager: lifecycle management for all channels
│   │   ├── handler.py        # ChannelMessageHandler: inbound message → AgentLoop → outbound
│   │   └── base.py           # Channel abstract base
│   ├── providers/            # LLM provider abstraction (Anthropic, OpenAI, etc.)
│   │   ├── factory.py        # create_provider() → provider instance
│   │   ├── registry.py       # Provider registry with metadata
│   │   └── runtime.py        # Provider runtime state + key rotation
│   ├── config/               # Configuration loading (Pydantic models → DB → runtime)
│   │   ├── loader.py         # ConfigLoader: load/save nested config to DB
│   │   └── schema.py         # Pydantic models: ProviderConfig, ModelConfig, WorkspaceConfig...
│   ├── cron/                 # Scheduled tasks (scheduler, executor, service)
│   ├── session/              # Session management + context service
│   ├── auth/                 # Authentication (middleware + router + utils)
│   ├── mcp/                  # MCP client (multi-server, health check, tool sync)
│   ├── wiki/                 # Wiki knowledge base (BM25 index + service + tool)
│   └── external_agents/      # External coding agent adapters (Claude Code, Codex...)
├── models/                   # SQLAlchemy database models (Session, Message, AgentTeam, etc.)
└── utils/                    # Utilities (logger, paths, network, runtime_env...)
```

### Key Data Flow

```
User message (WebSocket / IM channel)
  → ChannelMessageHandler
  → AgentLoop.process_message()
    → ContextBuilder.build_messages()  (history + memory + skills)
    → LLM chat_stream()  (streaming chunks)
      → If tool call: execute_tool() → ToolRegistry.execute() → return result
      → Append tool result to messages → loop again
    → Final content → yield to WebSocket
  → Channel.send() → User
```

### Configuration Storage

All config is stored in SQLite `settings` table with keys like `config.model.provider`, `config.workspace.path`, `auth.username`, `auth.password_hash`. `ConfigLoader` reads/writes nested dicts via JSON serialization.

### Tool Execution Pattern

```python
# All tools inherit from Tool base class
class MyTool(Tool):
    @property
    def name(self) -> str: ...
    @property
    def description(self) -> str: ...
    @property
    def parameters(self) -> Dict: ...  # JSON Schema
    async def execute(self, **kwargs) -> str: ...

# Registry manages all tools
registry = ToolRegistry()
registry.register(MyTool())
result = await registry.execute("my_tool", {"param": "value"})
```

### Workflow Modes

| Mode | File | Behavior |
|------|------|----------|
| `pipeline` | `workflow.py:run_pipeline()` | Sequential stages, context passes forward |
| `graph` | `workflow.py:run_graph()` | DAG with auto-parallel scheduling |
| `council` | `workflow.py:run_council()` | Multi-perspective: round 1 → cross-review → synthesis |

### Authentication

- Single-user model (one admin account)
- Password setup via `/api/auth/setup` (local only or with setup secret)
- Login via `/api/auth/login` → Cookie-backed session token
- Middleware protects all `/api/*` routes except public health endpoints
- Rate limiting: 5 attempts per 15 min → 15 min lockout

## Common Development Tasks

**Add a new tool**:
1. Create `backend/modules/tools/my_tool.py`, inherit `Tool`
2. Implement `name`, `description`, `parameters` (JSON Schema), `execute()`
3. Register in `backend/modules/tools/setup.py` → `register_all_tools()`

**Add a new channel**:
1. Create `backend/modules/channels/my_channel.py`, inherit `Channel`
2. Implement message receive/send, connection management
3. Register in `backend/modules/channels/manager.py`

**Add a new LLM provider**:
1. Create `backend/modules/providers/my_provider.py`, inherit `Provider`
2. Register in `backend/modules/providers/registry.py`
3. Add config in `backend/modules/config/schema.py`

**Run a single test**:
```bash
python -m pytest tests/test_something.py -v
```

## Important Notes

- All code uses `async/await` — the entire backend is async
- Tools return `str` (not print) — use `await registry.execute()` to get results
- `contextvars` used for async-safe session/channel context propagation in `ToolRegistry`
- Audit logging writes to `data/tool_audit.log` — enabled by default
- Workspace path is validated by `WorkspaceValidator` to prevent path traversal
- Dangerous shell commands (`rm -rf`, `shutdown`, etc.) are blocked by default
