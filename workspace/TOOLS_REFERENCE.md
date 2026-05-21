# 🛠️ CountBot 工具系统完整参考

> **用途**：所有内置工具的类、方法、用途、使用参数一览  
> **适用对象**：开发者 / 想自己写工具的进阶用户  
> **最后更新**：基于 v0.9.0

---

## 📋 目录

1. [工具系统架构](#1-工具系统架构)
2. [工具基类](#2-工具基类-basepy)
3. [工具注册表](#3-工具注册表-registrypy)
4. [文件系统工具](#4-文件系统工具-filesystempy)
5. [Shell 命令工具](#5-shell-命令工具-shellpy)
6. [Web 工具](#6-web-工具-webpy)
7. [记忆工具](#7-记忆工具-memory_toolpy)
8. [工作流工具](#8-工作流工具-workflow_toolpy)
9. [子 Agent 工具](#9-子-agent-工具-spawnpy)
10. [文件搜索工具](#10-文件搜索工具-file_searchpy)
11. [截图工具](#11-截图工具-screenshotpy)
12. [媒体发送工具](#12-媒体发送工具-send_mediaPy)
13. [外部编程 Agent 工具](#13-外部编程-agent-工具-external_coding_agentpy)
14. [Wiki 知识库工具](#14-wiki-知识库工具-wiki)
15. [工具注册入口](#15-工具注册入口-setuppy)

---

## 1. 工具系统架构

```
┌─────────────────────────────────────────────────────────┐
│                    ToolRegistry                          │
│  (管理所有工具：注册 / 查询 / 执行 / 审计日志)            │
└───────────┬──────────────────────┬──────────────────────┘
            │                      │
     ┌──────▼──────┐        ┌──────▼──────┐
     │  Tool (基类) │        │  各工具实现  │
     │  (抽象基类)  │        │  (继承 Tool) │
     └─────────────┘        └──────────────┘
```

**核心设计思想**：
- 每个工具 = 一个 Python 类，继承自 `Tool`
- 工具由 `ToolRegistry` 统一管理
- LLM 通过 `tool_definitions` 知道有哪些工具可用
- LLM 决定调用哪个工具 → `registry.execute(name, args)` → 返回结果

---

## 2. 工具基类 `base.py`

### 类：`Tool`（抽象基类）

所有工具必须继承此类并实现 4 个抽象属性/方法。

| 成员 | 类型 | 用途 |
|------|------|------|
| `name` | `@property` → `str` | 工具的唯一名称（如 `"read_file"`） |
| `description` | `@property` → `str` | 人类可读描述（LLM 用这个决定何时调用） |
| `parameters` | `@property` → `Dict` | JSON Schema，定义工具参数的类型和必填项 |
| `execute(**kwargs)` | `async` → `str` | 执行工具，返回结果字符串 |

### 辅助方法

| 方法 | 用途 |
|------|------|
| `validate_params(params)` | 验证参数是否符合 JSON Schema |
| `get_definition()` | 返回完整的工具定义（用于传给 LLM） |
| `to_schema()` | 别名方法，同 `get_definition()` |

### 自定义工具的模板

```python
from backend.modules.tools.base import Tool

class MyTool(Tool):
    @property
    def name(self) -> str:
        return "my_tool"

    @property
    def description(self) -> str:
        return "Do something useful."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "input": {"type": "string", "description": "Input text."},
            },
            "required": ["input"],
        }

    async def execute(self, **kwargs) -> str:
        input_text = kwargs.get("input", "")
        # 你的逻辑
        return f"Processed: {input_text}"
```

---

## 3. 工具注册表 `registry.py`

### 类：`ToolRegistry`

管理所有工具的注册、查询、执行。

### 核心方法

| 方法 | 用途 | 示例 |
|------|------|------|
| `register(tool)` | 注册一个工具 | `registry.register(ReadFileTool(...))` |
| `unregister(name)` | 注销一个工具 | `registry.unregister("read_file")` |
| `get_tool(name)` | 获取工具实例 | `registry.get_tool("read_file")` |
| `has_tool(name)` | 检查工具是否存在 | `registry.has_tool("read_file")` |
| `list_tools()` | 列出所有工具名 | `["read_file", "write_file", ...]` |
| `get_definitions()` | 获取所有工具定义（传给 LLM） | 返回 `List[Dict]` |
| `execute(name, args)` | **执行工具**（核心方法） | `await registry.execute("read_file", {"path": "a.txt"})` |
| `set_session_id(sid)` | 设置当前会话 ID（异步安全） | `registry.set_session_id("abc-123")` |
| `set_channel(channel)` | 设置渠道（web-chat / wechat / telegram） | `registry.set_channel("wechat")` |
| `set_cancel_token(token)` | 设置取消令牌 | `registry.set_cancel_token(token)` |
| `set_audit_enabled(bool)` | 设置是否启用审计日志 | `registry.set_audit_enabled(True)` |
| `get_stats()` | 获取统计信息 | `{"total_tools": 15, "tool_names": [...]}` |
| `clear()` | 清空所有工具 | — |

### 执行流程（`execute` 方法）

```
1. 查找工具 → 不存在则返回错误
2. 生成调用 ID（UUID）
3. 记录审计日志（调用时间、参数）
4. 验证参数（JSON Schema）
5. 执行 tool.execute(**args)
6. 计算耗时，更新审计日志
7. 记录到对话历史
8. 返回结果字符串
```

---

## 4. 文件系统工具 `filesystem.py`

### 类：`WorkspaceValidator`

**用途**：验证文件路径是否在工作空间内，防止路径遍历攻击。

| 方法 | 用途 |
|------|------|
| `validate_path(path)` | 验证并解析路径，如果越界则抛异常 |

---

### 类：`ReadFileTool`

**用途**：读取文件内容，支持单文件/多文件、行范围读取。

| 属性 | 值 |
|------|-----|
| `name` | `"read_file"` |
| `description` | "Read one file or many files. Single-file mode supports optional 1-based line ranges." |

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `path` | `string` | 单文件模式必填 | 单个文件路径 |
| `paths` | `array[string]` | 多文件模式必填 | 多个文件路径 |
| `start_line` | `integer` | 可选 | 起始行号（1-based） |
| `end_line` | `integer` | 可选 | 结束行号（1-based） |
| `show_line_numbers` | `boolean` | 可选，默认 `true` | 是否显示行号 |

**使用示例**：

```python
# 单文件读取
await registry.execute("read_file", {"path": "README.md"})

# 读取指定行范围
await registry.execute("read_file", {
    "path": "backend/app.py",
    "start_line": 100,
    "end_line": 200
})

# 批量读取多个文件
await registry.execute("read_file", {
    "paths": ["README.md", "LICENSE", "config/default.yaml"]
})
```

**输出格式**：
```
[File: README.md | Lines: 264]
  1| # CountBot
  2| 面向中文用户的开源 AI Agent 框架...
```

---

### 类：`WriteFileTool`

**用途**：写入文件，支持覆盖和追加模式。

| 属性 | 值 |
|------|-----|
| `name` | `"write_file"` |
| `description` | "Write text to a file. Modes: `overwrite` or `append`." |

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `path` | `string` | ✅ | 文件路径 |
| `content` | `string` | ✅ | 要写入的内容 |
| `mode` | `string` | 可选，默认 `"overwrite"` | `"overwrite"` 或 `"append"` |

**使用示例**：

```python
# 覆盖写入（第一个块）
await registry.execute("write_file", {
    "path": "output.html",
    "content": "<!DOCTYPE html>...",
    "mode": "overwrite"
})

# 追加写入（后续块）
await registry.execute("write_file", {
    "path": "output.html",
    "content": "<body>...</body>",
    "mode": "append"
})
```

> ⚠️ **建议**：大文件（HTML/code）分段写入，每段 ≤ 800 字符，先用 `overwrite` 写第一段，后续用 `append`。

---

### 类：`EditFileTool`

**用途**：编辑文件，支持文本替换和按行号编辑。

| 属性 | 值 |
|------|-----|
| `name` | `"edit_file"` |
| `description` | "Edit a file by text replace or 1-based line range." |

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `path` | `string` | ✅ | 文件路径 |
| `old_text` | `string` | 文本模式必填 | 要替换的旧文本 |
| `new_text` | `string` | 可选 | 新文本 |
| `start_line` | `integer` | 行模式必填 | 起始行号（1-based） |
| `end_line` | `integer` | 行模式可选 | 结束行号 |
| `insert` | `boolean` | 可选，默认 `false` | `true` 表示在 start_line 前插入 |

**使用示例**：

```python
# 文本替换模式
await registry.execute("edit_file", {
    "path": "config.yaml",
    "old_text": "model: claude-3-haiku",
    "new_text": "model: claude-3-5-sonnet"
})

# 按行号替换
await registry.execute("edit_file", {
    "path": "backend/app.py",
    "start_line": 100,
    "end_line": 110,
    "new_text": "新的代码内容"
})

# 按行号删除
await registry.execute("edit_file", {
    "path": "backend/app.py",
    "start_line": 100,
    "end_line": 110
})

# 按行号插入
await registry.execute("edit_file", {
    "path": "backend/app.py",
    "start_line": 100,
    "new_text": "新插入的代码",
    "insert": true
})
```

---

### 类：`ListDirTool`

**用途**：列出目录内容。

| 属性 | 值 |
|------|-----|
| `name` | `"list_dir"` |
| `description` | "List files and subdirectories in a directory." |

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `path` | `string` | 可选，默认 `"."` | 目录路径 |

**使用示例**：

```python
await registry.execute("list_dir", {"path": "backend/modules"})
```

**输出**：
```
Contents of backend/modules/:
dir   agent                        0 bytes
dir   channels                     0 bytes
dir   config                       0 bytes
file  __init__.py              1234 bytes
...
```

---

## 5. Shell 命令工具 `shell.py`

### 类：`ExecTool`

**用途**：在工作空间中安全执行 Shell 命令。

| 属性 | 值 |
|------|-----|
| `name` | `"exec"` |
| `description` | "Run a shell command." |

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `command` | `string` | ✅ | Shell 命令 |
| `working_dir` | `string` | 可选 | 工作目录（相对于 workspace） |
| `timeout` | `integer` | 可选 | 超时时间（秒），范围 10-3600 |
| `monitor` | `object` | 可选 | 监控配置（进度更新） |

**安全机制**：

| 机制 | 说明 |
|------|------|
| 危险命令拦截 | `rm -rf`、`shutdown`、`dd if=` 等被默认阻止 |
| 路径限制 | 命令只能在工作空间内执行 |
| 超时控制 | 默认 180 秒超时 |
| 输出截断 | 默认最多 10000 字符 |
| 白名单/黑名单 | 可配置自定义 `allow_patterns` / `deny_patterns` |

**危险命令列表**（默认拦截）：
```
rm -rf, del /f, rmdir /s, format, mkfs, diskpart, dd if=, 
> /dev/sd*, shutdown, reboot, poweroff, halt, fork bomb, init 0/6
```

**使用示例**：

```python
# 简单命令
await registry.execute("exec", {"command": "ls -la"})

# 带工作目录
await registry.execute("exec", {
    "command": "npm install",
    "working_dir": "frontend"
})

# 带超时
await registry.execute("exec", {
    "command": "python train.py",
    "timeout": 600
})
```

---

### 类：`ExecToolSafe`

**用途**：安全模式 Shell 执行工具，预配置严格策略。

| 配置 | 值 |
|------|-----|
| 超时 | 30 秒 |
| 允许危险命令 | `False` |
| 工作空间限制 | `True`（强制） |

---

## 6. Web 工具 `web.py`

### 类：`WebFetchTool`

**用途**：获取网页内容，集成 Scrapling 反爬虫能力。

| 属性 | 值 |
|------|-----|
| `name` | `"web_fetch"` |
| `description` | "Fetch a web page. Returns text by default. Modes: basic, stealth, max-stealth." |

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `url` | `string` | ✅ | 网页 URL（必须是 http/https） |
| `mode` | `string` | 可选，默认 `"basic"` | `"basic"` / `"stealth"` / `"max-stealth"` |
| `outputFormat` | `string` | 可选，默认 `"text"` | `"text"` / `"html"` / `"json"` |
| `maxChars` | `integer` | 可选，默认 `50000` | 最大返回字符数 |

**三种抓取模式**：

| 模式 | 技术 | 耗时 | 适用场景 |
|------|------|------|---------|
| `basic` | curl-cffi + 伪装 headers | 1-2 秒 | 普通静态页面 |
| `stealth` | Playwright 无头浏览器 | 3-8 秒 | JavaScript 渲染的页面 |
| `max-stealth` | Camoufox | 10+ 秒 | 强反爬网站 |

**使用示例**：

```python
# 快速模式（默认）
await registry.execute("web_fetch", {"url": "https://example.com"})

# 隐身模式（JS 渲染页面）
await registry.execute("web_fetch", {
    "url": "https://example.com",
    "mode": "stealth"
})

# 返回 HTML 原文
await registry.execute("web_fetch", {
    "url": "https://example.com",
    "outputFormat": "html"
})

# 返回结构化 JSON
await registry.execute("web_fetch", {
    "url": "https://api.example.com/data",
    "outputFormat": "json"
})
```

---

## 7. 记忆工具 `memory_tool.py`

### 类：`MemoryTool`（统一工具，推荐使用）

**用途**：统一的记忆读写搜索工具，通过 `action` 参数区分操作。

| 属性 | 值 |
|------|-----|
| `name` | `"memory"` |
| `description` | "Long-term memory: `write`, `search`, or `read`." |

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `action` | `string` | ✅ | `"write"` / `"search"` / `"read"` |
| `content` | `string` | `write` 时必填 | 要写入的记忆内容 |
| `keywords` | `string` | `search` 时必填 | 搜索关键词 |
| `max_results` | `integer` | 可选，默认 `15` | 搜索最大结果数 |
| `match_mode` | `string` | 可选，默认 `"or"` | `"or"`（任意匹配）/ `"and"`（全部匹配） |
| `start_line` | `integer` | `read` 时可选 | 起始行号 |
| `end_line` | `integer` | `read` 时可选 | 结束行号 |
| `recent_count` | `integer` | `read` 时可选，默认 `10` | 获取最近 N 条 |

**使用示例**：

```python
# 写入记忆
await registry.execute("memory", {
    "action": "write",
    "content": "用户喜欢 Python；项目用 FastAPI + Vue"
})

# 搜索记忆（OR 模式，任意关键词匹配）
await registry.execute("memory", {
    "action": "search",
    "keywords": "Python FastAPI",
    "match_mode": "or"
})

# 搜索记忆（AND 模式，全部关键词匹配）
await registry.execute("memory", {
    "action": "search",
    "keywords": "Python FastAPI",
    "match_mode": "and"
})

# 读取指定行
await registry.execute("memory", {
    "action": "read",
    "start_line": 1,
    "end_line": 10
})

# 读取最近 20 条
await registry.execute("memory", {
    "action": "read",
    "recent_count": 20
})
```

---

### 遗留工具（向后兼容，不推荐新代码使用）

| 类 | `name` | 用途 |
|------|--------|------|
| `MemoryWriteTool` | `"memory_write"` | 仅写入 |
| `MemorySearchTool` | `"memory_search"` | 仅搜索 |
| `MemoryReadTool` | `"memory_read"` | 仅读取 |

---

## 8. 工作流工具 `workflow_tool.py`

### 类：`WorkflowTool`

**用途**：运行多 Agent 协作工作流。

| 属性 | 值 |
|------|-----|
| `name` | `"workflow_run"` |
| `description` | "Run a multi-agent workflow. Modes: `pipeline`, `graph`, `council`." |

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `mode` | `string` | ✅ | `"pipeline"` / `"graph"` / `"council"` |
| `goal` | `string` | ✅ | 工作流目标 |
| `agents` | `array` | 自定义团队时必填 | Agent 定义列表 |
| `team_name` | `string` | 预定义团队时必填 | 预定义团队名称 |
| `cross_review` | `boolean` | 可选，默认 `true` | council 模式是否交叉评审 |

**三种模式详解**：

#### mode = `pipeline`（流水线）

顺序执行，每个 Agent 继承前序所有输出。

```python
await registry.execute("workflow_run", {
    "mode": "pipeline",
    "goal": "写一篇技术博客",
    "agents": [
        {"id": "researcher", "role": "研究者", "task": "搜索相关技术资料"},
        {"id": "writer", "role": "作者", "task": "根据研究结果写一篇博客文章"},
        {"id": "editor", "role": "编辑", "task": "润色文章，检查语法和逻辑"}
    ]
})
```

#### mode = `graph`（依赖图）

DAG 依赖图，满足依赖的节点自动并行执行。

```python
await registry.execute("workflow_run", {
    "mode": "graph",
    "goal": "分析一家公司的财务状况",
    "agents": [
        {"id": "fetch_revenue", "role": "数据获取", "task": "获取公司营收数据", "depends_on": []},
        {"id": "fetch_users", "role": "数据获取", "task": "获取用户增长数据", "depends_on": []},
        {"id": "analyze", "role": "分析师", "task": "综合分析营收和用户数据", "depends_on": ["fetch_revenue", "fetch_users"]},
        {"id": "report", "role": "报告生成", "task": "生成最终分析报告", "depends_on": ["analyze"]}
    ]
})
```

#### mode = `council`（委员会）

多视角审议：第 1 轮独立分析 → 第 2 轮交叉评审。

```python
await registry.execute("workflow_run", {
    "mode": "council",
    "goal": "评估是否应该采用微服务架构",
    "agents": [
        {"id": "pro", "role": "支持方", "task": "列出微服务的优势", "perspective": "支持微服务架构"},
        {"id": "con", "role": "反对方", "task": "列出微服务的缺点", "perspective": "反对微服务架构"},
        {"id": "neutral", "role": "中立分析", "task": "给出客观分析", "perspective": "中立技术分析师"}
    ],
    "cross_review": true
})
```

---

## 9. 子 Agent 工具 `spawn.py`

### 类：`SpawnTool`

**用途**：生成一个子 Agent 执行任务，等待完成后返回结果。

| 属性 | 值 |
|------|-----|
| `name` | `"spawn"` |
| `description` | "Run a sub-agent and return its final result." |

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `task` | `string` | ✅ | 子 Agent 的任务描述 |
| `label` | `string` | 可选 | 显示标签 |

**使用示例**：

```python
await registry.execute("spawn", {
    "task": "搜索最新的 Python 3.13 特性，总结成 5 个要点",
    "label": "Python 特性调研"
})
```

**超时**：默认 1200 秒（20 分钟），可在配置中修改 `security.subagent_timeout`。

---

## 10. 文件搜索工具 `file_search.py`

### 类：`FileSearchTool`

**用途**：跨平台文件搜索，支持通配符匹配。

| 属性 | 值 |
|------|-----|
| `name` | `"file_search"` |
| `description` | "Search files by wildcard pattern." |

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `path` | `string` | ✅ | 搜索目录 |
| `pattern` | `string` | 可选，默认 `"*"` | 通配符模式（如 `"*.py"`） |
| `type` | `string` | 可选，默认 `"all"` | `"file"` / `"dir"` / `"all"` |
| `max_depth` | `integer` | 可选，默认 `-1` | 最大递归深度（-1 表示无限制） |
| `limit` | `integer` | 可选，默认 `20` | 最大返回结果数（1-100） |

**使用示例**：

```python
# 搜索所有 Python 文件
await registry.execute("file_search", {
    "path": "backend",
    "pattern": "*.py"
})

# 只搜索目录
await registry.execute("file_search", {
    "path": "backend/modules",
    "type": "dir"
})

# 限制深度和结果数
await registry.execute("file_search", {
    "path": "workspace",
    "pattern": "*.md",
    "max_depth": 2,
    "limit": 10
})
```

---

## 11. 截图工具 `screenshot.py`

### 类：`ScreenshotTool`

**用途**：桌面截图或网页截图。

| 属性 | 值 |
|------|-----|
| `name` | `"screenshot"` |
| `description` | "Capture a desktop or webpage screenshot." |

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `mode` | `string` | ✅ | `"desktop"` / `"webpage"` |
| `url` | `string` | `webpage` 模式必填 | 网页 URL |
| `output_path` | `string` | 可选 | 输出文件路径 |
| `monitor` | `integer` | `desktop` 模式可选，默认 `0` | 显示器编号 |
| `full_page` | `boolean` | `webpage` 模式可选 | 是否全页截图 |
| `viewport_width` | `integer` | 可选，默认 `1280` | 视口宽度 |
| `viewport_height` | `integer` | 可选，默认 `720` | 视口高度 |
| `wait_time` | `integer` | 可选，默认 `1000` | 等待时间（毫秒） |
| `timeout` | `integer` | 可选，默认 `30000` | 超时时间（毫秒） |

**使用示例**：

```python
# 桌面截图
await registry.execute("screenshot", {"mode": "desktop"})

# 多显示器截图（第 2 个显示器）
await registry.execute("screenshot", {"mode": "desktop", "monitor": 1})

# 网页截图
await registry.execute("screenshot", {
    "mode": "webpage",
    "url": "https://example.com"
})

# 网页全页截图
await registry.execute("screenshot", {
    "mode": "webpage",
    "url": "https://example.com",
    "full_page": true,
    "viewport_width": 1920
})
```

---

## 12. 媒体发送工具 `send_media.py`

### 类：`SendMediaTool`

**用途**：发送本地文件/图片到当前频道聊天。

| 属性 | 值 |
|------|-----|
| `name` | `"send_media"` |
| `description` | "Send local files or images to the current channel chat." |

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file_paths` | `array[string]` | ✅ | 本地文件路径列表 |
| `message` | `string` | 可选 | 附带消息 |

**支持的文件格式**：

| 类型 | 扩展名 |
|------|--------|
| 图片 | `.png`, `.jpg`, `.jpeg`, `.gif`, `.bmp`, `.webp` |
| 文档 | `.txt`, `.pdf`, `.doc`, `.docx`, `.xls`, `.xlsx`, `.ppt`, `.pptx`, `.md` |
| 压缩包 | `.zip`, `.rar`, `.7z` |
| 音视频 | `.mp3`, `.mp4`, `.avi`, `.mov` |
| 数据 | `.json`, `.xml`, `.csv` |

**限制**：
- 单个文件 ≤ 20MB
- 企业微信：图片 ≤ 10MB，单次最多 10 张

**使用示例**：

```python
await registry.execute("send_media", {
    "file_paths": ["workspace/screenshots/desktop_20260521.png"],
    "message": "这是今天的截图"
})
```

---

## 13. 外部编程 Agent 工具 `external_coding_agent.py`

### 类：`ExternalCodingAgentTool`

**用途**：将编程任务分派给外部编程 Agent（如 Claude Code、Codex、OpenCode）。

| 属性 | 值 |
|------|-----|
| `name` | `"external_coding_agent"` |
| `description` | "Run a configured external coding agent." |

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `task` | `string` | ✅ | 任务描述 |
| `profile` | `string` | 可选 | 配置 profile 名称 |
| `mode` | `string` | 可选，默认 `"run"` | `"run"` / `"analyze"` / `"edit"` / `"review"` / `"debug"` |
| `working_dir` | `string` | 可选 | 工作目录 |
| `context_files` | `array[string]` | 可选 | 相关上下文文件列表 |
| `extra_instructions` | `string` | 可选 | 额外指令 |
| `timeout` | `integer` | 可选 | 超时（秒） |
| `monitor` | `object` | 可选 | 监控配置 |

**使用示例**：

```python
await registry.execute("external_coding_agent", {
    "task": "为 CountBot 添加一个新的工具：计算两个日期的天数差",
    "mode": "edit",
    "working_dir": "backend/modules/tools",
    "context_files": ["backend/modules/tools/base.py", "backend/modules/tools/filesystem.py"],
    "extra_instructions": "遵循现有的 Tool 基类模式，添加完整的 JSON Schema 参数定义"
})
```

---

## 14. Wiki 知识库工具 `wiki/tool.py`

### 类：`WikiTool`

**用途**：Wiki 知识库管理，支持搜索、问答、CRUD。

| 属性 | 值 |
|------|-----|
| `name` | `"wiki"` |
| `description` | "Wiki knowledge base with BM25 search." |

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `action` | `string` | ✅ | 操作类型（见下表） |
| `query` | `string` | `search`/`ask` 时必填 | 搜索查询或问题 |
| `slug` | `string` | `get`/`delete`/`update` 时必填 | Wiki 条目唯一标识 |
| `slugs` | `array[string]` | `batch_get` 时必填 | 批量获取的条目列表 |
| `title` | `string` | `create`/`update` 时必填 | 条目标题 |
| `content` | `string` | `create`/`update` 时必填 | Markdown 内容 |
| `tags` | `array[string]` | `create`/`update` 可选 | 标签列表 |
| `tag` | `string` | `list` 时可选 | 按标签过滤 |
| `top_k` | `integer` | 可选，默认 `10` | 搜索最大结果数 |

**支持的 action**：

| action | 用途 | 必填参数 |
|--------|------|---------|
| `search` | 搜索 Wiki 条目 | `query` |
| `ask` | 基于知识库回答问题 | `query` |
| `get` | 获取单个条目完整内容 | `slug` |
| `batch_get` | 批量获取多个条目 | `slugs` |
| `list` | 列出所有条目 | 无 |
| `stats` | 获取统计信息 | 无 |
| `create` | 创建新条目 | `title`, `content` |
| `update` | 更新现有条目 | `slug`, `title`/`content`/`tags` |
| `delete` | 删除条目 | `slug` |
| `sync` | 同步索引（检测文件变更） | 无 |

**使用示例**：

```python
# 搜索
await registry.execute("wiki", {
    "action": "search",
    "query": "BM25 召回率优化",
    "top_k": 5
})

# 问答（会用 LLM 基于搜索结果回答）
await registry.execute("wiki", {
    "action": "ask",
    "query": "CountBot 怎么提升 RAG 召回率？"
})

# 获取单个条目
await registry.execute("wiki", {
    "action": "get",
    "slug": "bm25-optimization"
})

# 批量获取
await registry.execute("wiki", {
    "action": "batch_get",
    "slugs": ["bm25-optimization", "agent-loop-design", "tool-system"]
})

# 列出所有条目（按标签过滤）
await registry.execute("wiki", {
    "action": "list",
    "tag": "ai"
})

# 获取统计
await registry.execute("wiki", {"action": "stats"})

# 创建新条目
await registry.execute("wiki", {
    "action": "create",
    "title": "BM25 优化技巧",
    "content": "# BM25 优化技巧\n\n## 1. 标题权重\n...\n",
    "tags": ["ai", "search", "rag"]
})

# 更新条目
await registry.execute("wiki", {
    "action": "update",
    "slug": "bm25-optimization",
    "content": "# 更新后的内容\n..."
})

# 删除条目
await registry.execute("wiki", {
    "action": "delete",
    "slug": "old-entry"
})

# 同步索引
await registry.execute("wiki", {"action": "sync"})
```

---

## 15. 工具注册入口 `setup.py`

### 函数：`register_all_tools()`

**用途**：一次性注册所有可用工具，通常在应用启动时调用。

**参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `workspace` | `Path` | — | 工作空间路径 |
| `command_timeout` | `int` | `180` | 命令超时时间（秒） |
| `max_output_length` | `int` | `10000` | 最大输出长度 |
| `allow_dangerous` | `bool` | `False` | 是否允许危险命令 |
| `restrict_to_workspace` | `bool` | `True` | 是否限制在工作空间内 |
| `custom_deny_patterns` | `List[str]` | `None` | 自定义拒绝模式 |
| `custom_allow_patterns` | `List[str]` | `None` | 自定义允许模式 |
| `audit_log_enabled` | `bool` | `True` | 是否启用审计日志 |
| `subagent_manager` | `object` | `None` | SubagentManager（启用 spawn/workflow） |
| `skills_loader` | `object` | `None` | SkillsLoader |
| `session_id` | `str` | `None` | 会话 ID |
| `channel_manager` | `object` | `None` | ChannelManager（启用 send_media） |
| `memory_store` | `object` | `None` | MemoryStore（启用 memory 工具） |

**注册的工具列表**：

| 序号 | 工具类 | 工具名 | 条件 |
|------|--------|--------|------|
| 1 | `ReadFileTool` | `read_file` | 始终注册 |
| 2 | `WriteFileTool` | `write_file` | 始终注册 |
| 3 | `EditFileTool` | `edit_file` | 始终注册 |
| 4 | `ListDirTool` | `list_dir` | 始终注册 |
| 5 | `ExecTool` | `exec` | 始终注册 |
| 6 | `ExternalCodingAgentTool` | `external_coding_agent` | 有 enabled profile 时 |
| 7 | `WebFetchTool` | `web_fetch` | 依赖可用时 |
| 8 | `SpawnTool` | `spawn` | 提供了 subagent_manager |
| 9 | `WorkflowTool` | `workflow_run` | 提供了 subagent_manager |
| 10 | `SendMediaTool` | `send_media` | 提供了 channel_manager |
| 11 | `ScreenshotTool` | `screenshot` | 依赖可用时 |
| 12 | `FileSearchTool` | `file_search` | 始终注册 |
| 13 | `MemoryTool` | `memory` | 提供了 memory_store |
| 14 | `WikiTool` | `wiki` | 始终注册 |
| 15 | `XiaozhiMessageTool` | `send_message` | 小智频道启用且 conversation 模式开启 |

**使用示例**：

```python
from backend.modules.tools.setup import register_all_tools
from pathlib import Path

registry = register_all_tools(
    workspace=Path("workspace"),
    command_timeout=300,
    allow_dangerous=False,
    subagent_manager=subagent_mgr,
    memory_store=memory_store,
    channel_manager=channel_mgr,
)

# 现在可以使用 registry.execute() 调用所有工具
result = await registry.execute("read_file", {"path": "README.md"})
```

---

## 📊 工具速查表

| 工具名 | 用途 | 核心参数 | 备注 |
|--------|------|---------|------|
| `read_file` | 读文件 | `path` / `paths`, `start_line`, `end_line` | 支持行号显示 |
| `write_file` | 写文件 | `path`, `content`, `mode` | `overwrite`/`append` |
| `edit_file` | 编辑文件 | `path`, `old_text`/`new_text`, `start_line`/`end_line` | 文本替换或按行编辑 |
| `list_dir` | 列目录 | `path` | — |
| `exec` | 执行命令 | `command`, `working_dir`, `timeout` | 有安全拦截 |
| `web_fetch` | 抓网页 | `url`, `mode`, `outputFormat` | 3 种反爬模式 |
| `memory` | 记忆管理 | `action` + `content`/`keywords` | 统一工具 |
| `workflow_run` | 多 Agent 工作流 | `mode`, `goal`, `agents`/`team_name` | pipeline/graph/council |
| `spawn` | 生成子 Agent | `task`, `label` | 等待完成 |
| `file_search` | 搜文件 | `path`, `pattern`, `type`, `limit` | 通配符匹配 |
| `screenshot` | 截图 | `mode`, `url`/`monitor` | desktop/webpage |
| `send_media` | 发媒体 | `file_paths`, `message` | 支持图片/文档 |
| `external_coding_agent` | 外部编程 Agent | `task`, `profile`, `mode` | Claude Code 等 |
| `wiki` | Wiki 知识库 | `action` + 其他参数 | 10 种操作 |

---

## 💡 写一个新工具的步骤

1. **继承 `Tool` 基类**
2. **实现 4 个抽象成员**：`name`、`description`、`parameters`、`execute()`
3. **在 `setup.py` 的 `register_all_tools()` 中注册**
4. **在 LLM 的 tool definitions 中自动可见**

```python
# 步骤 1-2：定义工具
from backend.modules.tools.base import Tool

class CalculatorTool(Tool):
    @property
    def name(self): return "calculate"
    
    @property
    def description(self): return "Perform mathematical calculations."
    
    @property
    def parameters(self):
        return {
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "Math expression like '2 + 3 * 4'."}
            },
            "required": ["expression"]
        }
    
    async def execute(self, **kwargs):
        expression = kwargs.get("expression", "")
        result = eval(expression)  # ⚠️ 生产环境请用 safer 的方式
        return f"Result: {result}"

# 步骤 3：注册
registry = ToolRegistry()
registry.register(CalculatorTool())

# 步骤 4：使用
result = await registry.execute("calculate", {"expression": "2 + 3 * 4"})
# → "Result: 14"
```

---

> **提示**：这份文档覆盖了所有内置工具。如果你想深入了解某个工具的源码实现，可以直接查看对应的 `.py` 文件。
