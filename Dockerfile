# ---- Stage 1: 构建前端 ----
FROM node:18-alpine AS frontend-builder

WORKDIR /app/frontend

# 启用 pnpm（项目使用 pnpm@10.8.1）
RUN corepack enable

COPY frontend/package.json ./
# 如果没有 pnpm-lock.yaml 也不报错
COPY frontend/pnpm-lock.yaml ./ || true
RUN pnpm install --no-frozen-lockfile

COPY frontend/ .
RUN pnpm build

# ---- Stage 2: 构建后端运行环境 ----
FROM python:3.12-slim

WORKDIR /app

# 安装系统依赖（aiosqlite 等需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# 复制后端源码
COPY backend/ ./backend/
COPY start_app.py start_dev.py ./

# 复制前端构建产物
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist/

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    -i https://mirrors.aliyun.com/pypi/simple/

# 运行时目录（挂载卷用）
RUN mkdir -p /app/data /app/workspace

EXPOSE 7000

CMD ["python", "start_app.py"]
