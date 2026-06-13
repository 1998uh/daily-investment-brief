# Plan D: Docker Compose 部署

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建完整的 Docker Compose 本地/云端部署方案，让系统可以一键 `docker compose up` 启动，同时保留 `memory/` 数据卷持久化。

**Architecture:** 两容器（backend + frontend）+ 一个 volume（memory/）。生产部署时 Nginx 可选，但不纳入本计划。

**Prerequisite:** Plan A（后端）、Plan B（Agent 层）、Plan C（前端）已完成。

---

## 文件地图

| 文件 | 职责 |
|------|------|
| `Dockerfile.backend` | Python 后端镜像 |
| `Dockerfile.frontend` | Next.js 前端镜像 |
| `docker-compose.yml` | 服务编排 |
| `docker-compose.dev.yml` | 本地开发覆盖（热重载）|
| `.dockerignore` | 根目录构建排除 |
| `frontend/.dockerignore` | 前端构建排除 |
| `scripts/health_check.sh` | 容器健康检查脚本 |

---

## Task 1: 后端 Dockerfile

**Files:**
- Create: `Dockerfile.backend`
- Create: `.dockerignore`

- [ ] **Step 1: 写失败检验命令**（确认 Docker 可用）

```bash
docker --version && docker compose version
```

Expected: 正常输出版本号。若 Docker 未安装则先安装 Docker Desktop。

- [ ] **Step 2: 创建 `.dockerignore`（根目录）**

```
# Development
**/__pycache__/
**/*.pyc
**/*.pyo
**/.pytest_cache/
**/.mypy_cache/
**/.ruff_cache/

# Environments
.env
.venv/
venv/
env/

# Runtime data (mounted as volumes)
memory/

# Frontend (built separately)
frontend/

# Git
.git/
.gitignore

# Docs
docs/

# Node
node_modules/

# Test
tests/
*.log
```

- [ ] **Step 3: 创建 `Dockerfile.backend`**

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.11-slim AS base

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY pyproject.toml ./
# Copy only source code needed for installation
COPY pipeline/ ./pipeline/
COPY agent/ ./agent/

# Install package with agent extras
RUN pip install --no-cache-dir -e ".[agent]"

# Non-root user for security
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Data directory (will be mounted)
RUN mkdir -p /data/memory

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/api/health || exit 1

EXPOSE 8080

CMD ["python", "-m", "agent", "--host", "0.0.0.0", "--port", "8080"]
```

- [ ] **Step 4: 验证 Dockerfile 语法**

```bash
docker build -f Dockerfile.backend --no-cache -t investment-agent-backend . 2>&1 | tail -20
```

Expected: 构建成功，最后一行 `Successfully built ...`。

> 注意：构建时会下载所有 Python 依赖，可能需要几分钟。ChromaDB 和 sentence-transformers 包较大。

- [ ] **Step 5: 本地运行测试**

```bash
docker run --rm -p 8080:8080 \
  -e AGENT_MEMORY_DIR=/data/memory \
  -e BRIEF_BASE_URL="" \
  -e BRIEF_MODEL="" \
  -e BRIEF_API_KEY="" \
  investment-agent-backend &

sleep 5
curl -s http://localhost:8080/api/health
docker stop $(docker ps -q --filter "ancestor=investment-agent-backend")
```

Expected: `{"status":"ok"}`.

---

## Task 2: 前端 Dockerfile

**Files:**
- Create: `frontend/.dockerignore`
- Create: `Dockerfile.frontend`

- [ ] **Step 1: 创建 `frontend/.dockerignore`**

```
node_modules/
.next/
.git/
*.log
.env.local
.env.development
.env.production
Dockerfile*
```

- [ ] **Step 2: 创建 `Dockerfile.frontend`**

```dockerfile
# syntax=docker/dockerfile:1

# Stage 1: Build
FROM node:20-alpine AS builder
WORKDIR /app

# Install dependencies first for layer caching
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund

# Copy source and build
COPY frontend/ ./
# Override API base URL for Docker network
ENV NEXT_PUBLIC_API_BASE=http://backend:8080
RUN npm run build

# Stage 2: Production runner
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV HOSTNAME=0.0.0.0
ENV PORT=3000

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# Copy built output
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

USER nextjs

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD wget -qO- http://localhost:3000/ || exit 1

EXPOSE 3000

CMD ["node", "server.js"]
```

> 注意：Next.js standalone output 需要在 `next.config.js` 中添加 `output: 'standalone'`。

- [ ] **Step 3: 更新 `frontend/next.config.js` 添加 standalone 模式**

修改 `frontend/next.config.js`：

```js
/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  async rewrites() {
    // In Docker, NEXT_PUBLIC_API_BASE points to backend service
    const apiBase = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8080';
    return [
      {
        source: '/api/:path*',
        destination: `${apiBase}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
```

- [ ] **Step 4: 构建前端镜像测试**

```bash
docker build -f Dockerfile.frontend -t investment-agent-frontend . 2>&1 | tail -20
```

Expected: 构建成功。

---

## Task 3: Docker Compose 编排

**Files:**
- Create: `docker-compose.yml`
- Create: `docker-compose.dev.yml`

- [ ] **Step 1: 创建 `docker-compose.yml`（生产模式）**

```yaml
version: "3.9"

services:
  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    image: investment-agent-backend:latest
    container_name: investment-backend
    restart: unless-stopped
    environment:
      # LLM settings — override with actual values in production
      BRIEF_BASE_URL: ${BRIEF_BASE_URL:-}
      BRIEF_MODEL: ${BRIEF_MODEL:-}
      BRIEF_API_KEY: ${BRIEF_API_KEY:-}
      TAVILY_API_KEY: ${TAVILY_API_KEY:-}
      # Agent settings
      AGENT_MEMORY_DIR: /data/memory
      AGENT_DB_NAME: ${AGENT_DB_NAME:-agent.db}
      AGENT_JWT_SECRET: ${AGENT_JWT_SECRET}
      AGENT_JWT_ALGORITHM: ${AGENT_JWT_ALGORITHM:-HS256}
      AGENT_JWT_EXPIRE_MINUTES: ${AGENT_JWT_EXPIRE_MINUTES:-1440}
      AGENT_CHROMA_DIR: /data/memory/chroma
      # Pipeline data — bind-mounted from host
      AGENT_SOURCES_DIR: /data/sources
      AGENT_REPORTS_DIR: /data/reports
    volumes:
      - memory_data:/data/memory
      - ${SOURCES_DIR:-./sources}:/data/sources:ro
      - ${REPORTS_DIR:-./reports}:/data/reports:ro
    ports:
      - "${BACKEND_PORT:-8080}:8080"
    networks:
      - agent_net
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/api/health"]
      interval: 30s
      timeout: 10s
      start_period: 60s
      retries: 3

  frontend:
    build:
      context: .
      dockerfile: Dockerfile.frontend
    image: investment-agent-frontend:latest
    container_name: investment-frontend
    restart: unless-stopped
    environment:
      NEXT_PUBLIC_API_BASE: http://backend:8080
    ports:
      - "${FRONTEND_PORT:-3000}:3000"
    networks:
      - agent_net
    depends_on:
      backend:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:3000/"]
      interval: 30s
      timeout: 10s
      start_period: 30s
      retries: 3

volumes:
  memory_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: ${MEMORY_DIR:-./memory}

networks:
  agent_net:
    driver: bridge
```

- [ ] **Step 2: 创建 `docker-compose.dev.yml`（开发覆盖）**

开发模式挂载源码，支持热重载：

```yaml
version: "3.9"

services:
  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
      target: base
    volumes:
      # Override: mount source code for live reload
      - ./agent:/app/agent:ro
      - ./pipeline:/app/pipeline:ro
      - ./memory:/data/memory
      - ./sources:/data/sources:ro
      - ./reports:/data/reports:ro
    command: ["python", "-m", "uvicorn", "agent.main:app",
              "--host", "0.0.0.0", "--port", "8080",
              "--reload", "--reload-dir", "/app/agent"]

  frontend:
    # Skip standalone build in dev — use npm run dev instead (not Dockerized in dev)
    profiles:
      - skip_in_dev
```

> 开发时只跑 backend 容器，前端用 `npm run dev` 本地启动并通过 next.config.js rewrite 代理到 8080。

---

## Task 4: 环境变量模板 + 启动脚本

**Files:**
- Modify: `.env.example`
- Create: `scripts/docker-start.sh`
- Create: `scripts/health_check.sh`

- [ ] **Step 1: 更新 `.env.example` 添加 Docker 配置段**

在现有 `.env.example` 末尾追加：

```bash
# ─── Docker Compose ────────────────────────────────────────────────
# Host port mappings
BACKEND_PORT=8080
FRONTEND_PORT=3000

# Host paths (defaults work if running from project root)
MEMORY_DIR=./memory
SOURCES_DIR=./sources
REPORTS_DIR=./reports
```

- [ ] **Step 2: 创建 `scripts/docker-start.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Check .env exists
if [ ! -f ".env" ]; then
    echo "ERROR: .env file not found. Copy .env.example and fill in values:"
    echo "  cp .env.example .env"
    exit 1
fi

# Check required env vars
source .env
if [ -z "${AGENT_JWT_SECRET:-}" ]; then
    echo "ERROR: AGENT_JWT_SECRET must be set in .env"
    echo "  Generate one: python -c \"import secrets; print(secrets.token_hex(32))\""
    exit 1
fi

# Create memory directory if needed
mkdir -p "${MEMORY_DIR:-./memory}"

echo "Building and starting services..."
docker compose up --build -d

echo ""
echo "Services started:"
echo "  Backend:  http://localhost:${BACKEND_PORT:-8080}"
echo "  Frontend: http://localhost:${FRONTEND_PORT:-3000}"
echo ""
echo "To view logs: docker compose logs -f"
echo "To stop:      docker compose down"
```

```bash
chmod +x scripts/docker-start.sh
```

- [ ] **Step 3: 创建 `scripts/health_check.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

BACKEND_PORT="${BACKEND_PORT:-8080}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
MAX_RETRIES=30
SLEEP=2

echo "Waiting for backend health..."
for i in $(seq 1 $MAX_RETRIES); do
    if curl -sf "http://localhost:${BACKEND_PORT}/api/health" > /dev/null 2>&1; then
        echo "✓ Backend healthy"
        break
    fi
    if [ $i -eq $MAX_RETRIES ]; then
        echo "✗ Backend failed to start after ${MAX_RETRIES} retries"
        exit 1
    fi
    sleep $SLEEP
done

echo "Waiting for frontend health..."
for i in $(seq 1 $MAX_RETRIES); do
    if curl -sf "http://localhost:${FRONTEND_PORT}/" > /dev/null 2>&1; then
        echo "✓ Frontend healthy"
        break
    fi
    if [ $i -eq $MAX_RETRIES ]; then
        echo "✗ Frontend failed to start after ${MAX_RETRIES} retries"
        exit 1
    fi
    sleep $SLEEP
done

echo ""
echo "All services healthy!"
echo "Open: http://localhost:${FRONTEND_PORT}"
```

```bash
chmod +x scripts/health_check.sh
```

---

## Task 5: 集成验证

- [ ] **Step 1: 确认目录结构**

```bash
ls -la Dockerfile.backend Dockerfile.frontend docker-compose.yml docker-compose.dev.yml scripts/
```

- [ ] **Step 2: 验证 compose 文件语法**

```bash
docker compose config --quiet && echo "✓ docker-compose.yml valid"
```

- [ ] **Step 3: 端对端构建测试**

```bash
# 需要 .env 文件存在且包含 AGENT_JWT_SECRET
cp .env.example .env.docker.test
echo "AGENT_JWT_SECRET=$(python -c 'import secrets; print(secrets.token_hex(32))')" >> .env.docker.test

# 构建不启动（验证 Dockerfile 可构建）
docker compose --env-file .env.docker.test build 2>&1 | tail -20
rm .env.docker.test
```

Expected: 两个镜像都构建成功。

- [ ] **Step 4: 完整启动测试（可选，需要 .env 完整配置）**

```bash
# 仅在有完整 .env 配置时运行
bash scripts/docker-start.sh
bash scripts/health_check.sh
docker compose down
```

- [ ] **Step 5: 更新 `.gitignore` 排除测试 env 文件**

确认 `.gitignore` 包含：
```
.env.docker.test
```

- [ ] **Step 6: Commit**

```bash
git add Dockerfile.backend Dockerfile.frontend docker-compose.yml docker-compose.dev.yml \
        scripts/ frontend/next.config.js .env.example
git commit -m "feat(docker): multi-container deployment — backend + frontend with memory volume"
```

---

## 部署手册（快速参考）

### 本地开发（无 Docker）

```bash
# 后端
python -m agent --port 8080

# 前端（新终端）
cd frontend && npm run dev
```

访问 `http://localhost:3000`

### 本地 Docker 一键启动

```bash
# 1. 准备 .env
cp .env.example .env
# 编辑 .env，填入 BRIEF_BASE_URL / BRIEF_MODEL / BRIEF_API_KEY / AGENT_JWT_SECRET

# 2. 启动
bash scripts/docker-start.sh

# 3. 等待健康检查
bash scripts/health_check.sh
```

### 云端部署（Linux Server）

```bash
# 1. SSH 到服务器，克隆仓库
git clone <repo> /opt/investment-agent
cd /opt/investment-agent

# 2. 配置 .env
cp .env.example .env
vim .env  # 填入生产配置

# 3. 挂载数据目录（可选 NFS / 本地磁盘）
mkdir -p /data/investment/{memory,sources,reports}
sed -i 's|MEMORY_DIR=./memory|MEMORY_DIR=/data/investment/memory|' .env
sed -i 's|SOURCES_DIR=./sources|SOURCES_DIR=/data/investment/sources|' .env
sed -i 's|REPORTS_DIR=./reports|REPORTS_DIR=/data/investment/reports|' .env

# 4. 启动
bash scripts/docker-start.sh
```

### 数据备份

```bash
# 备份 SQLite + ChromaDB
docker compose exec backend tar czf /tmp/backup.tar.gz /data/memory
docker cp investment-backend:/tmp/backup.tar.gz ./backup-$(date +%Y%m%d).tar.gz
```

### 更新部署

```bash
git pull
docker compose build
docker compose up -d
```

### 重建索引

```bash
docker compose exec backend python -m agent --rebuild-index
```
