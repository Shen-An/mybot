# 📘 CountBot 从零到一学习路线

> **目标**：能独立构建自己的 Agent 项目  
> **项目**：CountBot（AI Agent 框架）  
> **预计周期**：3~4 周（每天 1~2 小时）  
> **学习方式**：边学边做，每个阶段都有动手任务

---

## 🗺️ 总览：4 个阶段（加速版）

```
阶段1: 读懂 CountBot 骨架    ──→  理解项目怎么跑起来（约 3-4 天）
阶段2: 深入核心模块          ──→  理解 Agent 怎么思考（约 1 周）
阶段3: 动手改造实验          ──→  修改代码看效果（约 5-7 天）
阶段4: 独立构建自己的 Agent  ──→  从 0 到 1 写一个（约 1 周）
```

> 💡 **说明**：你有 Java + 前后端经验，很多概念可直接迁移，学习速度会快很多。

---

## 🔄 Java → Python 概念速查（5 分钟过完）

你已有的知识可以直接套用，只需要知道 Python 的对应写法：

| Java | Python | 说明 |
|------|--------|------|
| `public class X` | `class X:` | 类定义，不用写 `public` |
| `new X()` | `X()` | 实例化，不用 `new` |
| `private/protected/public` | 无关键字（约定 `_` 前缀表示私有） | Python 不强制访问控制 |
| `List<String> list = new ArrayList<>()` | `list: List[str] = []` | 类型注解是可选的 |
| `Map<String, Object> map` | `dict` / `{"key": value}` | 字典就是 HashMap |
| `try-catch` | `try-except` | 异常处理 |
| `@Override` | 无 | Python 不需要 |
| `Stream API / CompletableFuture` | `async/await` | 异步编程 |
| `Spring @Autowired` | 依赖注入靠构造函数/参数传递 | Python 更简单直接 |
| `Servlet Filter` | FastAPI Middleware | 概念一样 |
| `MyBatis / JPA` | SQLAlchemy | ORM 概念相同 |

### 关键差异（注意！）

```python
# 1. Python 没有分号和大括号，用缩进
if x > 0:
    print("positive")  # 缩进表示代码块

# 2. 列表推导式（Java Stream 的简洁版）
squares = [x*x for x in range(10)]  # [0,1,4,9,...,81]

# 3. 字典解包（类似 Java Map 但更灵活）
def greet(name, greeting="Hello"):
    return f"{greeting}, {name}!"
kwargs = {"name": "Alice", "greeting": "Hi"}
greet(**kwargs)  # "Hi, Alice!"

# 4. async/await 和 Java 的 CompletableFuture 概念类似
async def fetch_data():
    result = await api.call()  # await 就是 then()
    return result
```

---

## ⚠️ 你不需要学的（直接跳过）

| 内容 | 原因 |
|------|------|
| Web 基础（HTTP、REST、WebSocket） | 你做过前后端，直接懂 |
| 数据库操作概念 | SQLAlchemy 和 JPA/MyBatis 概念一样 |
| 面向对象基础 | Java 比 Python 复杂，你已经掌握了 |
| 项目结构/分层架构 | `api/` = Controller, `modules/` = Service, `models/` = Entity |

---

## ⚠️ 需要重点关注的（Java 里没有的）

| 内容 | 为什么重要 | 学习建议 |
|------|-----------|---------|
| `async/await` | CountBot 全异步代码 | 理解"协程"概念即可 |
| Python 类型注解 | 代码里大量 `-> str`, `: Dict` | 知道是类型提示，不影响运行 |
| `pathlib.Path` | 文件路径操作 | 比 Java `File` 简洁 |
| `loguru` 日志 | CountBot 用的日志库 | 比 `Logger` 简单 |
| Pydantic | 数据验证/配置模型 | 类似 Jackson + 验证注解 |
| LLM Tool Calling | Agent 的核心机制 | **重点学习** |

---

## ⚠️ 你提到不会的高阶内容，在这里的影响

| 你不会的 | 在 CountBot 中出现吗 | 需要学吗 |
|---------|-------------------|---------|
| 正则表达式 | 少量用于日志/解析 | **初期不需要**，遇到再查 |
| 网络编程细节 | 渠道模块有 WebSocket | 你做过前后端，概念都懂，只看实现 |
| 复杂装饰器 | 少量 `@decorator` | 知道是"包装函数"就行 |
| 设计模式 | 有但用得克制 | 不用专门学，边看边理解 |

---

## 📌 阶段 2：读懂 CountBot 骨架（约 1 周）

> **目标**：理解项目目录结构，知道每个文件夹是干什么的

### 2.1 先看项目目录树

```
CountBot/
├── backend/              ← 🎯 核心！后端全部代码在这里
│   ├── api/              ← API 接口（前端调用的入口）
│   ├── modules/          ← 🎯 核心模块（Agent、工具、渠道等）
│   │   ├── agent/        ← Agent 循环、记忆、工作流
│   │   ├── channels/     ← 微信、飞书等 IM 渠道
│   │   ├── tools/        ← 工具系统（文件、Shell、Web 等）
│   │   ├── providers/    ← LLM 提供商（OpenAI、Claude 等）
│   │   ├── config/       ← 配置加载
│   │   ├── cron/         ← 定时任务
│   │   └── ...
│   ├── models/           ← 数据库模型
│   └── app.py            ← 🎯 FastAPI 应用入口
├── frontend/             ← 前端（Vue.js，暂时不用深究）
├── config/               ← 配置文件
├── start_app.py          ← 🎯 启动脚本
└── requirements.txt      ← 依赖包列表
```

### 2.2 关键文件阅读顺序

| 顺序 | 文件 | 看什么 | 不看什么 |
|------|------|--------|---------|
| 1 | `start_app.py` | 看 `main()` 函数，了解启动流程 | 不用懂所有细节 |
| 2 | `backend/app.py` | 看 `lifespan` 函数，了解组件怎么创建 | 跳过中间件和 CORS |
| 3 | `backend/modules/agent/loop.py` | 看 `AgentLoop` 类的 `__init__` 和 `process_message` | 先跳过复杂的错误处理 |
| 4 | `backend/modules/tools/registry.py` | 看工具怎么注册和调用 | 不用看每个工具的实现 |
| 5 | `backend/modules/config/loader.py` | 看配置怎么加载和保存 | 不用深究数据库操作 |

### 2.3 动手任务

**任务 1：画一张项目架构图**

用纸笔或绘图工具，画出 CountBot 的数据流：
```
用户消息 → WebSocket → AgentLoop → 调用 LLM → 可能调用工具 → 返回结果 → WebSocket → 前端
```

**任务 2：跑起来看效果**

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动
python start_app.py

# 3. 浏览器打开 http://127.0.0.1:8000
# 4. 随便说句话，看看发生了什么
```

**任务 3：在代码里打点日志**

在 `backend/modules/agent/loop.py` 的 `process_message` 方法开头加一行：
```python
print(f"🔔 收到消息: {message[:50]}...")
```
重启后看看控制台输出。

### ✅ 阶段 2 检查清单

- [ ] 能说出 `backend/` 下面每个文件夹的作用
- [ ] 能画出数据从用户到 AI 回应的流程图
- [ ] 成功启动项目并看到前端界面
- [ ] 能在代码里找到 `AgentLoop` 类并看懂它的作用

---

## 📌 阶段 3：深入核心模块（约 2 周）

> **目标**：理解 Agent 的核心工作原理，能看懂关键代码

### 3.1 核心模块 1：Agent Loop（`loop.py`）

**核心思想**：Agent 像一个循环机器人

```
┌─────────────────────────────────────────────┐
│              Agent Loop 循环                  │
│                                              │
│  1. 接收用户消息                              │
│  2. 组装上下文（历史对话 + 记忆 + 技能）          │
│  3. 发给 LLM 请求回复                          │
│  4. 如果 LLM 说"我要调用工具"：                │
│     a. 执行工具                                │
│     b. 把工具结果放回对话                       │
│     c. 回到第 3 步继续问 LLM                      │
│  5. 如果 LLM 直接给答案：返回给用户              │
│                                              │
│  循环最多 25 次（max_iterations）               │
└─────────────────────────────────────────────┘
```

**关键代码位置**：`backend/modules/agent/loop.py:178`

```python
async def process_message(self, message, session_id, ...):
    # 第 1 步：组装消息
    messages = self.context_builder.build_messages(...)
    
    # 第 2 步：循环开始
    while iteration < max_iterations:
        # 发给 LLM
        async for chunk in provider.chat_stream(messages=messages, tools=tools):
            # 收集回复内容
            content_buffer += chunk.content
            
            # 如果 LLM 要调用工具
            if chunk.is_tool_call:
                tool_calls_buffer.append(chunk.tool_call)
        
        # 如果有工具调用，执行它们
        for tool_call in tool_calls_buffer:
            result = await self.execute_tool(tool_name, tool_args)
            # 把结果放回对话，继续循环
            messages.append({"role": "tool", "content": result})
        
        # 如果没有工具调用，说明 LLM 直接回答了
        if not tool_calls_buffer:
            break
    
    return final_content
```

**动手任务**：
1. 在 `process_message` 的 `while` 循环里加 `print(f"第 {iteration} 轮")`
2. 问一个需要调用工具的问题（比如"帮我列出当前目录的文件"）
3. 观察控制台输出，数一数循环了几轮

### 3.2 核心模块 2：工具系统（`tools/`）

**核心思想**：工具 = 函数 + 描述 + 参数

```python
# 每个工具都是一个类，继承自 Tool
class ReadFileTool(Tool):
    name = "read_file"
    description = "读取文件内容"
    
    async def execute(self, path: str) -> str:
        # 具体实现
        return Path(path).read_text()
```

**关键文件**：
- `backend/modules/tools/base.py` → 工具的基类
- `backend/modules/tools/registry.py` → 工具注册表（管理所有工具）
- `backend/modules/tools/filesystem.py` → 文件操作工具示例

**动手任务**：
1. 看 `ReadFileTool` 的代码，理解它怎么读取文件
2. 尝试写一个最简单的工具：返回当前时间的工具

### 3.3 核心模块 3：记忆系统（`memory.py`）

**核心思想**：记忆 = 文本文件 + 关键词搜索

```python
class MemoryStore:
    def __init__(self, memory_dir):
        self.memory_file = memory_dir / "MEMORY.md"
    
    def append_entry(self, source, content):
        # 格式：日期|来源|内容
        entry = f"{date}|{source}|{content}"
        # 追加到文件末尾
    
    def search(self, keywords):
        # 在文件里搜索包含关键词的行
```

**动手任务**：
1. 打开 `workspace/memory/MEMORY.md`，看看里面的内容
2. 在对话框里问："我上次问过什么问题？"
3. 看看 AI 是怎么搜索记忆的

### 3.4 核心模块 4：工作流引擎（`workflow.py`）

**核心思想**：多 Agent 协作的三种模式

| 模式 | 比喻 | 适用场景 |
|------|------|---------|
| `pipeline` | 流水线 | 顺序处理，如：搜索→整理→输出 |
| `graph` | 依赖图 | 有依赖关系的多任务，自动并行 |
| `council` | 委员会 | 多视角讨论，如：正反方辩论 |

**关键代码位置**：`backend/modules/agent/workflow.py:47`

**动手任务**：
1. 在前端找到"工作流"面板
2. 用 pipeline 模式做一个"搜索新闻→总结摘要"的流程
3. 观察每个阶段的输出

### ✅ 阶段 3 检查清单

- [ ] 能画出 Agent Loop 的循环流程图
- [ ] 能解释"LLM 调用工具"的完整过程
- [ ] 能看懂一个工具类的代码结构
- [ ] 能解释记忆是怎么存储和搜索的
- [ ] 能说出 pipeline/graph/council 三种模式的区别

---

## 📌 阶段 4：动手改造实验（约 2 周）

> **目标**：通过修改代码来验证理解，积累实战经验

### 4.1 实验 1：添加一个简单的工具

**目标**：创建一个"返回当前时间"的工具

```python
# 在 backend/modules/tools/ 下新建 time_tool.py
from datetime import datetime
from backend.modules.tools.base import Tool

class TimeTool(Tool):
    name = "get_time"
    description = "获取当前时间"
    
    async def execute(self) -> str:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"当前时间是：{now}"
```

然后在 `backend/modules/tools/setup.py` 的 `register_all_tools` 里注册它。

### 4.2 实验 2：修改 Agent 的提示词

**目标**：改变 AI 的性格

```python
# backend/modules/agent/prompts.py
# 找到 system prompt，修改 AI 的自我介绍
# 比如把"你是一个 helpful 的助手"改成"你是一个幽默的宠物猫"
```

### 4.3 实验 3：添加一个新的渠道

**目标**：理解渠道系统的工作方式

```python
# backend/modules/channels/base.py
# 看 BaseChannel 的定义
# 理解 channel 是怎么接收消息、发送消息的
```

### 4.4 实验 4：调试一个工作流

**目标**：用 graph 模式做一个多步骤任务

```python
# 定义一个 graph：
# 节点 1：搜索用户想要的信息
# 节点 2：整理搜索结果
# 节点 3：生成最终报告
# 节点 2 依赖节点 1，节点 3 依赖节点 2
```

### ✅ 阶段 4 检查清单

- [ ] 成功添加并测试了一个新工具
- [ ] 修改了 AI 的提示词并看到了效果
- [ ] 理解了渠道消息的接收和发送流程
- [ ] 能独立配置一个简单的工作流

---

## 📌 阶段 5：独立构建自己的 Agent 项目（约 2 周）

> **目标**：脱离 CountBot，从 0 到 1 写一个自己的 Agent

### 5.1 最小可行 Agent（MVP）

一个最简 Agent 只需要 3 个组件：

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   LLM API    │ ←→  │  Agent Loop  │ ←→  │   Tools      │
│  (Claude/    │     │  (循环处理)   │     │  (文件/Shell) │
│   OpenAI)    │     │              │     │              │
└──────────────┘     └──────────────┘     └──────────────┘
```

### 5.2 你的第一个 Agent 项目模板

```python
# my_agent.py
import os
from anthropic import AsyncAnthropic

class MyAgent:
    def __init__(self):
        self.client = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self.messages = []
    
    async def chat(self, user_message):
        # 1. 添加用户消息
        self.messages.append({"role": "user", "content": user_message})
        
        # 2. 调用 LLM
        response = await self.client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            messages=self.messages,
            tools=[{
                "name": "get_time",
                "description": "获取当前时间",
                "input_schema": {"type": "object", "properties": {}}
            }]
        )
        
        # 3. 处理回复
        if response.stop_reason == "tool_use":
            # LLM 要调用工具，执行后再问一次
            for tool_use in response.content:
                if tool_use.type == "tool_use":
                    result = self.execute_tool(tool_use.name, tool_use.input)
                    self.messages.append({"role": "assistant", "content": response.content})
                    self.messages.append({"role": "user", "content": [
                        {"type": "tool_result", "tool_use_id": tool_use.id, "content": result}
                    ]})
                    # 递归调用
                    return await self.chat("")
        
        # 4. 返回最终答案
        answer = response.content[0].text
        self.messages.append({"role": "assistant", "content": response.content})
        return answer
    
    def execute_tool(self, name, args):
        if name == "get_time":
            from datetime import datetime
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return "未知工具"

# 使用
import asyncio
agent = MyAgent()
result = asyncio.run(agent.chat("现在几点了？"))
print(result)
```

### 5.3 逐步扩展你的 Agent

| 步骤 | 添加什么 | 参考 CountBot 的 |
|------|---------|-----------------|
| 1 | 基础对话 | `loop.py` 的 `process_message` |
| 2 | 工具调用 | `tools/registry.py` |
| 3 | 记忆存储 | `memory.py` |
| 4 | 多轮对话上下文 | `context.py` |
| 5 | 文件操作工具 | `filesystem.py` |
| 6 | Shell 命令工具 | `shell.py` |
| 7 | Web 搜索工具 | `web.py` |
| 8 | 多 Agent 协作 | `workflow.py` |
| 9 | 渠道接入（微信等） | `channels/` |

### 5.4 你的最终项目建议

选择一个方向，做一个完整的 Agent：

**选项 A：个人知识助手**
- 工具：文件读写 + 搜索 + 记忆
- 功能：帮你整理笔记、回答问题、总结文档

**选项 B：自动化办公助手**
- 工具：Shell + 文件 + 邮件
- 功能：自动处理文件、发送报告、定时任务

**选项 C：学习伙伴 Agent**
- 工具：Web 搜索 + 文件 + 记忆
- 功能：帮你查资料、做笔记、出练习题

---

## 📚 学习资源汇总

### Python 基础
- [廖雪峰 Python 教程](https://www.liaoxuefeng.com/books/python/introduction/index.html) - 中文，适合入门
- [Python 官方文档](https://docs.python.org/zh-cn/3/) - 权威参考

### FastAPI（CountBot 后端框架）
- [FastAPI 官方文档](https://fastapi.tiangolo.com/) - 有中文

### 异步编程
- [Python asyncio 文档](https://docs.python.org/zh-cn/3/library/asyncio.html)
- [asyncio 入门教程](https://www.jianshu.com/p/d945c9a7c2b7)

### LLM API
- [Anthropic API 文档](https://docs.anthropic.com/)
- [LiteLLM 文档](https://docs.litellm.ai/) - CountBot 使用的统一接口

### CountBot 文档
- [官方文档](https://654321.ai/docs)
- [GitHub 仓库](https://github.com/countbot-ai/CountBot)

---

## 💡 学习建议

1. **不要试图一次性读懂所有代码** — 先跑起来，再边用边看
2. **每个阶段都要动手** — 只看不练记不住
3. **善用 print 调试** — 在代码里加 `print()` 是最快的学习方式
4. **遇到问题先查文档** — 培养独立解决问题的能力
5. **记录学习过程** — 在 `workspace/learning_notes.md` 里写笔记

---

## 📅 推荐学习节奏（加速版）

| 时间 | 阶段 | 每天 | 周末 |
|------|------|------|------|
| 第 1-3 天 | CountBot 骨架 | 30 分钟读代码 + 30 分钟启动实验 | 2 小时画架构图 |
| 第 4-10 天 | 核心模块 | 45 分钟读代码 + 15 分钟实验 | 3 小时深度实验 |
| 第 11-17 天 | 改造实验 | 1 小时做实验 + 30 分钟总结 | 3 小时大实验 |
| 第 18-25 天 | 独立项目 | 1.5 小时写代码 | 4 小时项目开发 |

---

> **记住**：学习编程就像学游泳，看再多教程也不如下水游。  
> 遇到问题很正常，每个开发者都经历过。坚持下来，你就能做到！💪
