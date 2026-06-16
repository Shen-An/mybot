#!/bin/bash
# CountBot Docker 部署脚本 — 甲骨文 1c6g 优化版
set -e

# ── 颜色 ──
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  CountBot Docker 部署${NC}"
echo -e "${GREEN}========================================${NC}"

# ── 检查 Docker ──
if ! command -v docker &>/dev/null; then
    echo -e "${RED}[错误] 未安装 Docker。请先安装 Docker。${NC}"
    echo "快速安装: curl -fsSL https://get.docker.com | bash -s docker"
    exit 1
fi

if ! command -v docker-compose &>/dev/null && ! docker compose version &>/dev/null 2>&1; then
    echo -e "${RED}[错误] 未安装 Docker Compose。${NC}"
    echo "快速安装: apt install docker-compose-plugin"
    exit 1
fi

# ── 检查端口冲突 ──
PORT=${COUNTBOT_PORT:-7000}
if ss -tlnp "sport = :$PORT" 2>/dev/null | grep -q LISTEN; then
    echo -e "${YELLOW}[警告] 端口 $PORT 已被占用。${NC}"
    echo "可通过 COUNTBOT_PORT 环境变量修改端口。"
fi

# ── 确保目录存在 ──
mkdir -p data workspace

# ── 构建并启动 ──
echo -e "${GREEN}[1/3] 构建镜像...${NC}"
docker compose build

echo -e "${GREEN}[2/3] 启动服务...${NC}"
docker compose up -d

echo -e "${GREEN}[3/3] 等待就绪...${NC}"
for i in $(seq 1 30); do
    if curl -s http://localhost:$PORT/docs >/dev/null 2>&1; then
        echo -e "${GREEN}✓ CountBot 已就绪！${NC}"
        echo -e "${GREEN}  访问地址: http://localhost:$PORT${NC}"
        break
    fi
    sleep 1
done

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  部署完成${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "  常用命令:"
echo "  查看日志:  docker compose logs -f"
echo "  重启服务:  docker compose restart"
echo "  更新镜像:  docker compose pull && docker compose up -d"
echo "  停止服务:  docker compose down"
echo ""
echo "  数据目录:"
echo "  data/     — SQLite 数据库 + 日志 (务必定期备份!)"
echo "  workspace/ — 技能、记忆、Wiki、上传文件"
echo ""
