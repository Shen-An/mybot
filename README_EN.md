<div align="center">
  <img src="https://github.com/user-attachments/assets/d42ee929-a9a9-4017-a07b-9eb66670bcc3" alt="CountBot Logo" width="180">
  <h1>CountBot</h1>
  <p>Open-source AI agent framework and runtime hub for Chinese users</p>
  <p>Connects LLMs, IM channels, workflows, and external tools so AI can actually execute work</p>

  <p>
    <a href="README.md">中文</a> | English
  </p>

  <p>
    <a href="https://github.com/countbot-ai/countbot/stargazers"><img src="https://img.shields.io/github/stars/countbot-ai/countbot?style=social" alt="GitHub stars"></a>
    <a href="https://github.com/countbot-ai/countbot"><img src="https://img.shields.io/badge/Python-3.8+-blue.svg" alt="Python"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License"></a>
  </p>
</div>

---

## About This Project

This project is a **fork** of [CountBot](https://github.com/countbot-ai/CountBot), an excellent open-source AI agent framework. It builds on the original project with several feature enhancements and optimizations.

> **Credit to the original author**: CountBot is a well-designed open-source project that provides a complete, production-ready AI agent framework for Chinese users. All modifications in this fork are built on the original author's open-source code. We deeply appreciate the original author's hard work and ongoing maintenance. Please visit the [original repository](https://github.com/countbot-ai/CountBot) and drop a ⭐ to show your support!

---

## Major Changes in This Fork

### 🔐 Multi-Tenant Authentication System

- **Multi-user support**: Upgraded from single-user to a multi-user architecture with `admin` / `operator` / `user` roles
- **PBKDF2 password hashing** + HMAC session tokens, with rate-limited login (5 attempts / 15 min → 15 min lockout)
- **Cookie + Bearer Token dual authentication**, supporting both `CountBot_token` cookie and Bearer header
- **Admin sudo mode**: `POST /api/auth/switch?target_user_id=N` to switch user identity, `get_effective_user_id()` prevents privilege escalation
- **Remote first-time setup entry** `/setup/{random_secret}` with configurable TTL (default 30 min), auto-invalidated after successful setup
- **WebSocket multi-user auth**: Cookie or Bearer token; local connections auto-assign the first admin as default user

### 🏢 Multi-Tenant Channel Isolation

- **`UserChannelConfig` table**: Each row records `user_id` + `channel` + `account_id` + `config_json` + `is_enabled`
- **ChannelManager user isolation**: Each channel instance is bound to `_user_id`, with key format `f"{channel}:{account_id}:{user_id}"`
- **User lifecycle**: `start_user_channels(user_id)` on login, `stop_user_channels(user_id)` on logout
- **Duplicate physical bot detection**: `async_init()` checks unique fields like `login_bot_id` across users and skips redundant instances
- **Outbound routing**: Routes precisely to the correct user's instance based on `msg.metadata["user_id"]` + `account_id`
- **User context propagation**: `ChannelMessageHandler` → `set_current_user_context()` injects user context via `contextvars` into non-HTTP layers (WebSocket, channel handlers, tools)
- **Hot-reload**: Channel config changes → `_restart_channel_manager_if_needed()` → full reload

### 🖥️ Frontend Enhancements

- **Registration on login page**: New users can self-register
- **KaTeX LaTeX math rendering**: Supports `$...$` and `$$...$$` math formulas
- **Settings page icon differentiation**: `users` tab uses `UsersIcon` (multiple people), `persona` tab uses `PersonIcon` (single person)
- **Frontend `dist/` no longer committed**: Added to `.gitignore`, CI/CD builds instead
- **UserManagement role label optimization**: "User" → "Regular User" for clearer distinction

### 🛠️ Tool System Improvements

- **BM25 skill routing optimization**: Improved skill search efficiency
- **ExecTool auto-detects CountBot conda env**: Subprocess Python automatically uses the project's conda environment
- **Enums replace hardcoded strings**: `memory_tool` + `workflow_tool` use enums to prevent string errors

### 📡 WebUI Refresh Notifications for Channel Messages

- **`history_updated` + `sessions_updated` event push**: Channel message backfill/mirroring now actively notifies WebUI to refresh, fixing the issue where channel messages didn't appear in WebUI
- **`session.user_id` auto-sync**: Channel sessions automatically set `user_id` to ensure WebUI session visibility

### 📦 Build Fixes

- **PyInstaller hidden-imports completed**: Fixed missing modules in compiled builds
- **Wiki module dependency fixes**: Fixed 500 errors in compiled Wiki builds

### 🔒 Security Hardening

- **Full provider isolation**: Each user's API keys exist only in their own `user_config`, invisible to others. `_sync_global_config` no longer syncs `providers` to the global config
- **New users must configure their own AI provider**: WebSocket endpoint no longer falls back to the admin's provider — new users without their own config cannot chat
- **Fixed missing `await` in auth admin endpoints**: `delete_user` / `create_user` / `update_user` are async functions but were called without `await`, causing CRUD operations to silently fail
- **Fixed 403 on user management API**: `RemoteAuthMiddleware` treated `/api/auth/*` as public paths, leaving `request.state.user` as `None`. Added `_get_current_user_from_request()` for self-validated session auth

### 🛡️ Admin Panel

- **New Admin Panel** (Settings → Admin tab, admin-only):
  - **Registration limit**: Set max users count, block new registrations when limit is reached
  - **Chat log viewer**: Filter by user, keyword search, paginated browsing of all user messages
  - **Traffic monitoring**: Per-user upload/download byte statistics, time-range filtering, direct user deletion for malicious activity
- **TrafficLog model**: Daily per-user traffic recording, auto-populated when messages are saved

### 🌐 Reverse Proxy Support

- **Uvicorn `forwarded_allow_ips="*"`**: Properly handles `X-Forwarded-Host` / `X-Forwarded-Proto` headers behind Nginx or server panels

### 🔧 WebSocket Stability

- **No forced reconnection on settings save**: Backend hot-reload syncs config at runtime — no need to disconnect WebSocket
- **Reconnection suppression**: Auto-suppresses WebSocket reconnection during settings saves to avoid flickering
- **Auto-reconnect after provider config**: Triggers reconnection when a new user saves their provider config while WS is disconnected

---

## What Is CountBot

CountBot is a lightweight AI agent framework that better fits Chinese users' habits, and also a runtime hub built for local deployment and long-running operation.

It connects roles, teams, workflows, tool invocation, memory, LLMs, IM channels, and local workspaces so AI can run continuously, collaborate across entry points, and execute real tasks.

You can think of CountBot as both a framework and a hub:

- Upward, it connects to 100+ LLM providers and different model strategies
- Outward, it connects to Web, WeChat, Lark, DingTalk, Telegram, Discord, QQ, Weibo, and more
- Inward, it organizes roles, teams, workflows, memory, and security boundaries
- At the execution layer, it connects files, Shell, Web, screenshots, file transfer, and external professional tools such as Claude Code, Codex, and OpenCode

In one sentence: **CountBot is an AI agent framework and runtime hub that connects models, channels, teams, and tools.**

CountBot was born from natural language. Its vision is not to require more people to learn complex configuration and programming before they can use AI, but to let ordinary users interact with AI directly through natural language to retrieve information, generate content, break down tasks, call tools, orchestrate workflows, and even build their own assistants, team collaboration flows, and automation systems.

---

## Core Capabilities

| Module | Description |
|------|------|
| Agent Loop | ReAct reasoning, tool invocation, result feedback, and iterative control |
| Agent Teams | Three collaboration modes: `pipeline`, `graph`, and `council` |
| Multi-bot channel matrix | One workspace can serve multiple channels, multiple bots, and multiple business entry points |
| Configuration layers | Global defaults, roles, teams, and runtime session configuration working together |
| Tools and skills | Files, Shell, Web, screenshots, memory, workflows, media delivery, and skill extensions |
| External execution tool integration | Connect external professional tools such as Claude Code, Codex, and OpenCode into one unified runtime |
| Memory and sessions | Long-term memory, summaries, context injection, and session isolation |
| Cron and Heartbeat | Scheduled tasks, proactive reminders, and long-running background operation |
| Security and workspace | Local control, path restrictions, audit logs, timeouts, and remote authentication boundaries |
| Multi-model access | Compatible with major domestic and international models, with team-level model override support |

---

## Use Cases

- Breaking down complex tasks into multiple roles that collaborate through natural-language instructions
- Running your own AI assistant, AI team, or automation workflow locally or in a private environment
- Serving multiple entry points at the same time, including Web, WeCom, Lark, DingTalk, Telegram, and Discord
- Unifying tool invocation, file operations, message delivery, and scheduled tasks in one runtime
- Bringing LLMs, message channels, tool usage, and team collaboration into a single operating hub
- Going beyond a simple AI assistant to build a sustainable, long-running agent system

---

## Quick Start

### Option 1: Start From Source

```bash
git clone https://github.com/Shen-An/CountBot.git
cd CountBot

# Default installation
pip install -r requirements.txt

# If you are in mainland China, you can use the Aliyun mirror
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

python start_app.py
```

After startup, CountBot opens at `http://127.0.0.1:8000` by default.

You can override the default bind host and port with environment variables. Priority is `COUNTBOT_HOST` / `COUNTBOT_PORT` > defaults.

```powershell
$env:COUNTBOT_HOST = '0.0.0.0'
$env:COUNTBOT_PORT = '8001'
python start_app.py
```

```cmd
set COUNTBOT_HOST=0.0.0.0
set COUNTBOT_PORT=8001
python start_app.py
```

If GitHub access is limited, you can switch to Gitee:

```bash
git clone https://gitee.com/countbot-ai/CountBot.git
```

### Option 2: Use the Desktop Build

- Gitee Releases: https://gitee.com/countbot-ai/CountBot/releases
- GitHub Releases: https://github.com/countbot-ai/CountBot/releases
- Supported platforms: Windows / macOS / Linux

---

## Documentation

| Document | Description | Link |
|------|------|------|
| Quick Start | Installation, configuration, and startup | [https://654321.ai/docs/getting-started/quick-start-guide](https://654321.ai/docs/getting-started/quick-start-guide) |
| Configuration Manual | Full configuration reference | [https://654321.ai/docs/getting-started/configuration-manual](https://654321.ai/docs/getting-started/configuration-manual) |
| Deployment and Operations | Startup, deployment, and troubleshooting | [https://654321.ai/docs/advanced/deployment](https://654321.ai/docs/advanced/deployment) |
| Remote Access Guide | Remote initialization, authentication, and troubleshooting | [https://654321.ai/docs/advanced/remote-access](https://654321.ai/docs/advanced/remote-access) |
| Authentication | Password setup and access boundaries | [https://654321.ai/docs/advanced/auth](https://654321.ai/docs/advanced/auth) |
| API Reference | REST API and WebSocket | [https://654321.ai/docs/api-reference](https://654321.ai/docs/api-reference) |

For the full documentation site, see: [https://654321.ai/docs](https://654321.ai/docs)

---

## Development and Contribution

### Local Development

```bash
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000
```

### Community

- QQ group: `1028356423`
- Discussion topics: CountBot usage, issue feedback, secondary development, and scenario co-creation

### Issue Reporting

- GitHub Issues: https://github.com/Shen-An/CountBot/issues

---

## License and Acknowledgements

### License

MIT License

### Project Inspiration

- OpenClaw
- NanoBot
- ZeroClaw
- anthropics/skills

### Acknowledgements

Thanks to the original author of [countbot-ai/CountBot](https://github.com/countbot-ai/CountBot) for the open-source contribution. This project is a fork with extensions based on the original author's MIT-licensed code. All modifications are also released under the MIT License.

Thanks to FastAPI, Vue.js, SQLAlchemy, Pydantic, LiteLLM, and other open-source projects.

---

<div align="center">
  <p>An AI agent runtime hub that connects models, channels, teams, and tools</p>
  <p>
    <a href="https://654321.ai">Official Website</a> ·
    <a href="https://github.com/Shen-An/CountBot">This Fork</a> ·
    <a href="https://github.com/countbot-ai/CountBot">Original Repository</a> ·
    <a href="https://654321.ai/docs">Full Documentation</a>
  </p>
</div>
