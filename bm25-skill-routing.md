# BM25 技能路由优化 — 分步实现指南

## 目标

用户每次提问时，用 BM25 搜索技能名+描述，只把**与当前问题相关的技能**注入 System Prompt，而不是把所有已启用技能全塞进去。

### 改动范围

| 文件 | 改动 |
|------|------|
| `backend/modules/agent/skills.py` | 加 BM25 索引 + `search_skills()` 方法 |
| `backend/modules/agent/context.py` | 用 BM25 过滤，只展示相关技能 |

不新建文件，不改其他模块。

---

## 前置阅读（理解要改的代码）

打开这两个文件通读一遍，不需要记住每一行，但要知道它们分别在干什么：

| 文件 | 行数 | 核心职责 |
|------|------|----------|
| `skills.py` | ~786 行 | `SkillsLoader`: 扫描目录、加载 SKILL.md、管理启用/禁用、生成摘要 |
| `context.py` | ~550 行 | `ContextBuilder`: 组装 System Prompt + 历史消息 → 传给 LLM |

读的时候关注这几个方法，马上要改它们：

**skills.py**：
- `__init__` (第 140 行) — 初始化，末尾建索引
- `_load_all_skills` (第 301 行) — 从磁盘加载所有技能
- `reload` (第 650 行) — 重新加载
- `add_skill` / `delete_skill` / `enable_skill` / `disable_skill` — 增删改后要重建索引
- `build_skills_summary` (第 432 行) — 生成全量技能摘要

**context.py**：
- `build_system_prompt` (第 93 行) — 构建 System Prompt，其中第 110-134 行处理技能注入
- `build_messages` (第 512 行) — 组装完整消息列表，第 527 行调 `build_system_prompt`

---

## Step 1: skills.py — 加 BM25 索引

### 1a) 顶部加 import

**文件**: `backend/modules/agent/skills.py`  
**位置**: 第 11 行附近，现有 import 之后

**操作**: 新增一行 import

```
from backend.modules.wiki.index import BM25Index
```

**为什么**: BM25Index 已经在 wiki 模块里实现了，直接复用，不需要写新的搜索代码。

---

### 1b) 构造函数末尾建索引

**文件**: `backend/modules/agent/skills.py`  
**位置**: `__init__` 方法末尾，`_load_all_skills()` 调用之后（目前在第 168 行）

**思路**:
1. 声明一个 `self.skill_index: BM25Index` 属性
2. 写一个私有方法 `_build_skill_index(self)`，在里面：
   a. 新建 BM25Index(k1=1.2, b=0.5) — 参数比默认（1.5/0.75）宽松，因为技能描述文本短，词频低
   b. 遍历 `self.skills`，只取已启用且依赖满足的技能（`skill.enabled and skill.check_requirements()`）
   c. 对每个技能，把 `name + " " + description + " " + tags` 拼成一个文本
   d. 调 `BM25Index.add_document(name, title=name, content=拼接文本)` — `doc_id` 用技能名
3. `__init__` 末尾调 `self._build_skill_index()`

**为什么**: BM25 需要词频统计，不能每次搜索时现算。Skill 数量最多几十个，重建索引开销可忽略。

**注意 `add_document` 的参数**:

```python
# BM25Index.add_document(doc_id, title, content, tags, mtime)
# 我们只需要前4个参数
# content 里包含所有可搜索文本
self.skill_index.add_document(
    name,              # doc_id → 搜索命中时返回的就是技能名
    name,              # title 用技能名
    search_text,       # content → 真正被分词的文本
    tags=[]            # tags 已经拼进 content 了，这里传空
)
```

---

### 1c) 新增 search_skills 方法

**文件**: `backend/modules/agent/skills.py`  
**位置**: 随便找个空白处，比如放在 `build_skills_summary` 之前或之后

**操作**: 新增方法

```python
def search_skills(self, query: str, top_k: int = 3) -> List[str]:
    """用 BM25 搜索相关技能
    
    Args:
        query: 用户当前消息
        top_k: 最多返回几个技能
        
    Returns:
        skill_name 列表，按相关度降序
    """
    if not query or not hasattr(self, 'skill_index'):
        return []
    results = self.skill_index.search(query, top_k=top_k)
    return [doc_id for doc_id, score in results]
```

**为什么要设 `top_k=3`**: 
- 太少（1个）：可能漏掉相关技能
- 太多（5+）：又回到了"塞一堆进上下文"的老问题
- 3 个是经验值，既聚焦又不遗漏

注意 `search()` 内部已经做了过滤：`score >= max_score * 0.3 且 score >= 0.5`，所以如果完全不相关的技能返回空列表是正常的。

---

### 1d) 在增删改方法末尾重建索引

**文件**: `backend/modules/agent/skills.py`  
**需要改的方法**:

| 方法 | 行号 | 操作 |
|------|------|------|
| `_load_all_skills` | 318-321 行附近 | 末尾加 `self._build_skill_index()` |
| `reload` | 650-655 行 | 末尾加 `self._build_skill_index()` |
| `add_skill` | 693 行附近 | 末尾加 `self._build_skill_index()` |
| `delete_skill` | 765 行附近 | 末尾加 `self._build_skill_index()` |
| `enable_skill` | 540 行附近 | 末尾加 `self._build_skill_index()` |
| `disable_skill` | 560 行附近 | 末尾加 `self._build_skill_index()` |

**为什么每处都要加**: 因为 BM25 索引是 in-memory 的，任何技能状态变化（增/删/启/禁）都会改变"哪些技能可用"，索引必须同步。少加一处就是隐蔽 bug——不存在的技能被搜到，或者新技能搜不到。

---

## Step 2: context.py — 用 BM25 过滤技能

### 2a) 修改 build_messages → 传 current_message

**文件**: `backend/modules/agent/context.py`  
**位置**: 第 527-531 行，build_messages 方法内部

**当前代码大致结构**:

```python
system_prompt = self.build_system_prompt(
    skill_names,
    persona_config=persona_config,
    channel=channel,
)
```

**思路**:
在调 `build_system_prompt` 之前，插入一段逻辑：

1. 检查 `self.skills` 是否存在且 `current_message` 非空
2. 如果是，调 `self.skills.search_skills(current_message, top_k=3)` → `relevant`
3. 调 `self.skills.get_always_skills()` → `always`（always 技能永远展示，不受 BM25 过滤）
4. 合并去重：`skill_names = list(set(relevant + always))`
5. 把 `skill_names` 传给 `build_system_prompt`

**为什么要保留 always 技能**: `always: true` 的技能（如身份设定、安全规则）是 Agent 任何时候都必须知道的，不应该被 BM25 过滤掉。

### 2b) 修改 build_system_prompt → 接受 skill_names 并过滤

**文件**: `backend/modules/agent/context.py`  
**位置**: 第 110-134 行，"技能系统"部分

**当前代码做两件事**:
1. 第 114 行：`always_skills = self.skills.get_always_skills()` → 全文注入
2. 第 121 行：`skills_summary = self.skills.build_skills_summary()` → 所有技能的摘要

**思路**:
第 2 步要根据 `skill_names` 参数做分支：

- 如果 `skill_names` 不为空 → 只生成这些技能的摘要
- 如果 `skill_names` 为空或 None → 保持原样，全部展示（向后兼容）

具体做法：给 `SkillsLoader.build_skills_summary()` 加一个可选参数 `skill_names: Optional[List[str]] = None`，传了就只过滤这些技能。

**为什么做向后兼容**: 因为 `build_system_prompt` 可能在其他地方被调用（目前看主要在 `build_messages` 里），那些调用方可能没传 `skill_names`，这时候退回到全量展示是安全的。

---

## 验证方法

改完之后启动项目，跑几个测试看效果：

```
用户："百度今天的新闻"
```

→ 预期：System Prompt 只有 baidu-search（可能还有 always 技能），没有 email/image-gen/stock

```
用户："帮我算 356 * 89"
```

→ 预期：BM25 可能命中"计算器"相关技能，如果没有对应技能，BM25 返回空列表 → 技能摘要部分直接不展示

```
用户："你好"
```

→ 预期：问候语和任何技能都不相关 → BM25 返回空 → System Prompt 没有技能摘要（always 的除外）

---

## 关键设计决策小结

| 决策 | 选择 | 理由 |
|------|------|------|
| BM25 参数 | k1=1.2, b=0.5 | 技能描述文本短，宽松参数提高召回 |
| top_k | 3 | 聚焦且不遗漏 |
| always 技能 | 不过滤 | 身份/安全规则永远需要 |
| 向后兼容 | 保留 skill_names=None 分支 | 其他调用方不受影响 |
| 索引重建时机 | 所有增删改方法末尾 | 确保索引始终与技能状态一致 |
| 索引文本 | name + description + tags | 技能名 + 描述 + 标签覆盖主要搜索场景 |