---
name: countbot-env
description: CountBot 统一 Python 运行环境管理。所有技能命令执行前先运行 setup_env.py 检测并创建 conda 环境，确保技能脚本能在正确的 Python 环境中运行。
always: true
---

# CountBot 统一环境

本项目的所有 Python 脚本和依赖都安装在 `CountBot` conda 环境中。

## 强制执行规则

在调用需要 Python 的**技能**执行 `exec` 命令前，**必须先运行**以下检测脚本：

```bash
python skills/countbot-env/scripts/setup_env.py
```
（exec 默认工作目录就是 workspace，所以用相对路径 `skills/...` 即可，脚本内部会自动定位项目根目录）

### 脚本输出含义

| 输出 | 含义 | 后续执行方式 |
|------|------|------------|
| `conda:COUNTBOT_EXISTS` | conda 可用 + CountBot 环境已就绪 | → 用 conda 方式 |
| `conda:CREATED` | conda 可用 + 已自动创建 CountBot | → 用 conda 方式 |
| `conda:CREATE_FAILED` | conda 可用但创建失败 | → 提示用户手动处理 |
| `NO_CONDA` | 系统没有 conda | → 直接用默认 python |

### 后续执行方式

**conda 可用时(Windows)：** — `conda run` 是首选的跨平台方式
```bash
conda run -n CountBot python scripts/tool.py args
```
如果 `conda run` 失败（比如路径问题），用以下方式：
```bash
conda activate CountBot && python scripts/tool.py args
```

**没有 conda 时：**
```bash
python scripts/tool.py args
```

### Windows 特别注意事项

- **conda run 路径**: 用正斜杠 `/` 而非反斜杠，或加引号处理空格
  - 正确: `conda run -n CountBot python scripts/tool.py arg`
  - 有时报错: `conda run -n CountBot python scripts\tool.py arg`
- **conda activate**: 如果 `conda run` 不好使，先 `conda activate CountBot` 再执行 `python ...`
- **setup_env.py** 会自动处理这些细节，所以务必**先运行它**

### 同次对话不重复检测

首次运行 `setup_env.py` 后，同次对话后续所有技能直接使用对应方式执行。