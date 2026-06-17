<div align="center">
  <h1>CountBot</h1>
  <p>面向中文用户的开源 AI Agent 框架与运行中枢</p>
  <p>连接大模型、IM 渠道、工作流与外部工具，帮助 AI 真正进入执行链路</p>

  <p>
    中文 | <a href="README_EN.md">English</a>
  </p>

  <p>
    <a href="https://github.com/countbot-ai/countbot/stargazers"><img src="https://img.shields.io/github/stars/countbot-ai/countbot?style=social" alt="GitHub stars"></a>
    <a href="https://github.com/countbot-ai/countbot"><img src="https://img.shields.io/badge/Python-3.8+-blue.svg" alt="Python"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License"></a>
  </p>
  <img src="https://github.com/user-attachments/assets/5a848b1f-04bf-40ff-8249-8a453294f444" alt="CountBot Logo" width="680">
</div>

---

## 关于本项目

本项目是 [CountBot](https://github.com/countbot-ai/CountBot) 的分支版本，在原作者开源框架的基础上进行了多项功能增强与优化。

> **向原作者致敬**：CountBot 是一个优秀的开源项目，为中文用户提供了完整、可用的 AI Agent 运行框架。本分支的所有改动均基于原作者的开源代码，感谢原作者的辛勤付出与持续维护。欢迎前往 [原作者仓库](https://github.com/countbot-ai/CountBot) 点亮 ⭐ 支持！

---

## 本分支的主要改动

### 🔐 多租户认证系统

- **多用户支持**：从单用户架构升级为多用户体系，支持 `admin` / `operator` / `user` 三种角色
- **PBKDF2 密码哈希** + HMAC 会话 Token，登录限流（5 次/15 分钟 → 15 分钟锁定时）
- **Cookie + Bearer Token 双认证**，支持 `CountBot_token` Cookie 和 Bearer Header
- **Admin Sudo 模式**：`POST /api/auth/switch?target_user_id=N` 切换用户身份，`get_effective_user_id()` 防止权限提升
- **远程首次初始化入口** `/setup/{random_secret}`，TTL 可控（默认 30 分钟），初始化成功后自动失效
- **WebSocket 多用户认证**：Cookie 或 Bearer Token，本地连接自动分配首个 admin 为默认用户

### 🏢 多租户渠道隔离

- **`UserChannelConfig` 表**：每行记录 `user_id` + `channel` + `account_id` + `config_json` + `is_enabled`
- **ChannelManager 用户隔离**：每个渠道实例绑定 `_user_id`，键名为 `f"{channel}:{account_id}:{user_id}"`
- **用户上下线生命周期**：登录时 `start_user_channels(user_id)`，登出时 `stop_user_channels(user_id)`
- **重复物理 Bot 检测**：`async_init()` 检查 `login_bot_id` 等唯一字段，跨用户跳过重复实例
- **Outbound 路由**：根据 `msg.metadata["user_id"]` + `account_id` 精确路由到对应用户实例
- **User context propagation**：`ChannelMessageHandler` → `set_current_user_context()` 通过 `contextvars` 将用户上下文注入非 HTTP 层（WebSocket、渠道处理器、工具）
- **Hot-reload**：渠道配置增删 → `_restart_channel_manager_if_needed()` → 全量重载

### 🖥️ 前端优化

- **登录页添加注册功能**：支持新用户自助注册
- **KaTeX LaTeX 数学公式渲染**：前端支持 `$...$` 和 `$$...$$` 数学公式渲染
- **设置页图标区分**：`users` tab 使用 `UsersIcon`（多人），`persona` tab 使用 `PersonIcon`（单人），避免混淆
- **前端构建产物不再提交**：`frontend/dist/` 加入 `.gitignore`，CI/CD 构建
- **UserManagement 角色标签优化**："用户" → "普通用户"，区分更清晰

### 🛠️ 工具系统优化

- **BM25 技能路由优化**：技能搜索效率提升
- **ExecTool 自动使用 CountBot conda 环境**：子进程 Python 自动检测项目 conda 环境
- **枚举替代硬编码字符串**：`memory_tool` + `workflow_tool` 使用枚举，避免字符串错误

### 📡 渠道消息 WebUI 刷新通知

- **`history_updated` + `sessions_updated` 事件推送**：渠道消息回写/镜像后主动通知 WebUI 刷新，修复渠道消息不显示在 WebUI 的问题
- **`session.user_id` 自动同步**：渠道会话自动设置 `user_id`，确保 WebUI 会话可见性

### 📦 构建修复

- **PyInstaller hidden-import 补全**：修复编译版缺失模块问题
- **Wiki 模块依赖修复**：修复编译版 Wiki 500 报错

### 🔒 安全加固

- **Provider 配置用户完全隔离**：每位用户的 API Key 仅存于各自 `user_config`，互不可见。`_sync_global_config` 不再同步 `providers` 到全局配置
- **新用户必须自行配置 AI 提供商**：WebSocket 端点不再 fallback 到管理员配置的全局 provider，新用户未配置时无法使用
- **Auth 管理端点 missing await 修复**：`delete_user` / `create_user` / `update_user` 均为 async 函数但遗漏 `await`，导致增删改实际未执行
- **用户管理接口 403 修复**：`RemoteAuthMiddleware` 将 `/api/auth/*` 视为公开路径导致 `request.state.user` 始终为 None，新增 `_get_current_user_from_request()` 自行验证会话

### 🛡️ 管理面板

- **新增管理面板**（设置页 → 管理面板，仅管理员可见）：
  - **注册限制**：设置最大用户数，超限时禁止新用户注册
  - **聊天记录查看**：按用户筛选、关键词搜索、分页浏览所有用户消息
  - **流量监控**：统计每个用户的上传/下载字节数，支持按时间范围筛选，可直接删除恶意用户
- **TrafficLog 模型**：按日按用户记录流量，消息保存时自动写入

### 🌐 反向代理部署支持

- **Uvicorn `forwarded_allow_ips="*"`**：支持 Nginx/面板反向代理，正确识别 `X-Forwarded-Host` / `X-Forwarded-Proto`

### 🔧 WebSocket 稳定性优化

- **保存设置不再主动断连**：后端热重载已同步配置到运行时，无需断开 WebSocket 重建
- **重连抑制机制**：设置保存期间自动抑制 WebSocket 重连，避免热重载导致重连闪烁
- **新用户配置后自动重连**：首次配置 provider 后，WS 断开状态下自动触发重连

---

## CountBot 是什么

CountBot 是一个符合中文用户习惯的轻量级 AI Agent 框架，也是面向本地部署与长期运行的 AI Agent 中枢。

它把角色、团队、工作流、工具调用、记忆、大模型、IM 渠道和本地工作空间连接起来，让 AI 具备长期运行、跨入口协作与任务执行能力。

你可以把 CountBot 理解为一个框架和中枢：

- 向上连接 100+ LLM 提供商与不同模型策略
- 向外连接 Web、微信、飞书、钉钉、Telegram、企业微信、QQ、微博等入口
- 向内组织角色、团队、工作流、记忆与安全边界
- 向执行层连接文件、Shell、Web、屏幕、文件传输，以及 Claude Code、Codex、OpenCode 一类外部行业工具

一句话概括：**CountBot 是连接模型、渠道、团队和工具的 AI Agent 框架与运行中枢。**

---

## 核心能力

| 模块 | 说明 |
|------|------|
| Agent Loop | ReAct 推理、工具调用、结果反馈与迭代控制 |
| Agent Teams | `pipeline`、`graph`、`council` 三种协作模式 |
| 多机器人渠道矩阵 | 一个工作区可服务多个渠道、多个机器人、多个业务入口 |
| 配置分层 | 全局默认、角色、团队、会话运行时配置分层协同 |
| 工具与技能 | 文件、Shell、Web、截图、记忆、工作流、媒体发送与技能扩展 |
| 外部执行工具接入 | 将 Claude Code、Codex、OpenCode 等外部行业工具接入统一运行时 |
| 记忆与会话 | 长期记忆、摘要、上下文注入、会话隔离 |
| Cron 与 Heartbeat | 定时任务、主动提醒、后台长期运行 |
| 安全与工作空间 | 本地可控、路径限制、审计日志、超时与远程认证边界 |
| 多模型接入 | 兼容国产与国际主流模型接入，支持团队级模型覆盖 |

---

## 适用场景

- 希望把自然语言需求拆成多个角色协同完成的复杂任务
- 希望在本地或私有环境中运行自己的 AI 助手、AI 团队或自动化流程
- 需要同时服务 Web、企业微信、飞书、钉钉、Telegram、Discord 等多个入口
- 希望将工具调用、文件操作、消息通知、定时任务整合进同一运行环境
- 希望把大模型、消息渠道、工具调用和团队协作整合到一个统一中枢
- 希望在 AI 助手之外，进一步构建可持续运行的 Agent 系统

---

## 快速开始

### 方式一：源码启动

```bash
git clone https://github.com/Shen-An/CountBot.git
cd CountBot

# 默认安装
pip install -r requirements.txt

# 国内网络可使用阿里云镜像
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

python start_app.py
```

启动完成后默认打开 `http://127.0.0.1:8000`。

可通过环境变量覆盖默认监听地址与端口，优先级为 `COUNTBOT_HOST` / `COUNTBOT_PORT` > 默认值。

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

如果国内网络访问 GitHub 受限，可切换到 Gitee：

```bash
git clone https://gitee.com/countbot-ai/CountBot.git
```

### 方式二：桌面版体验

- Gitee Releases: https://gitee.com/countbot-ai/CountBot/releases
- GitHub Releases: https://github.com/countbot-ai/CountBot/releases
- 适用平台：Windows / macOS / Linux

---

## 文档入口

| 文档 | 说明 | 链接 |
|------|------|------|
| 快速开始 | 安装、配置、启动 | [https://654321.ai/docs/getting-started/quick-start-guide](https://654321.ai/docs/getting-started/quick-start-guide) |
| 配置手册 | 完整配置说明 | [https://654321.ai/docs/getting-started/configuration-manual](https://654321.ai/docs/getting-started/configuration-manual) |
| 部署与运维 | 启动、部署、排障 | [https://654321.ai/docs/advanced/deployment](https://654321.ai/docs/advanced/deployment) |
| 远程访问指南 | 远程初始化、认证、排障 | [https://654321.ai/docs/advanced/remote-access](https://654321.ai/docs/advanced/remote-access) |
| 认证说明 | 密码初始化与访问边界 | [https://654321.ai/docs/advanced/auth](https://654321.ai/docs/advanced/auth) |
| API 参考 | REST API 与 WebSocket | [https://654321.ai/docs/api-reference](https://654321.ai/docs/api-reference) |

完整站点文档请查看：[https://654321.ai/docs](https://654321.ai/docs)

---

## 开发与贡献

### 本地开发

```bash
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000
```

### 社区交流

- QQ 交流群：`1028356423`
- 讨论方向：CountBot 使用、问题反馈、二次开发、场景共创

### 问题反馈

- GitHub Issues: https://github.com/Shen-An/CountBot/issues

---

## 开源协议与致谢

### 开源协议

MIT License

### 项目灵感

- OpenClaw
- NanoBot
- ZeroClaw
- anthropics/skills

### 致谢

感谢原作者 [countbot-ai/CountBot](https://github.com/countbot-ai/CountBot) 的开源贡献。本项目基于原作者的 MIT 开源代码 fork 并扩展，所有改动同样遵循 MIT License。

感谢 FastAPI、Vue.js、SQLAlchemy、Pydantic、LiteLLM 等开源项目。

---

<div align="center">
  <p>连接模型、渠道、团队与工具的 AI Agent 中枢</p>
  <p>
    <a href="https://654321.ai">官方网站</a> ·
    <a href="https://github.com/Shen-An/CountBot">本仓库 (Fork)</a> ·
    <a href="https://github.com/countbot-ai/CountBot">原作者仓库</a> ·
    <a href="https://654321.ai/docs">完整文档</a>
  </p>
</div>
