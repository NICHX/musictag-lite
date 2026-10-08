# MusicTag Lite

一个**轻量、可插拔、核心全免费**的自托管音乐标签（元数据）管理 Web 应用。

- 后端：Python 3.11+ / FastAPI / SQLModel / SQLite(WAL) / Alembic / httpx
- 音频核心：**mutagen**（纯 Python，**不依赖 ffmpeg**）
- 前端：Vue 3 `<script setup>` + TypeScript + Vite + Vue Router + Pinia + Tailwind CSS v4
- 实时进度：WebSocket `/ws/events`
- 部署：本地 dev 运行 + Docker 单镜像（FastAPI 同时托管 `/api` 与前端静态资源）

> 完整设计文档见 [`docs/music-tag-lite-design.md`](docs/music-tag-lite-design.md)。

## 目录结构

```
.
├─ backend/            # FastAPI 应用
│  ├─ app/
│  │  ├─ api/          # 路由（REST 契约）
│  │  ├─ core/         # 配置 / DB / 事件 / 任务 / 安全 / 日志
│  │  ├─ models/       # SQLModel 模型与 Pydantic schema
│  │  ├─ audio/        # 音频 IO 抽象（mutagen）
│  │  ├─ providers/    # 刮削插件（builtin / community）
│  │  └─ services/     # 领域服务
│  ├─ alembic/         # 数据库迁移
│  ├─ tests/           # pytest
│  ├─ pyproject.toml
│  └─ Dockerfile
├─ frontend/           # Vue 3 SPA
│  ├─ src/ (views, components, router, stores, api, design, assets)
│  ├─ vite.config.ts
│  └─ package.json
├─ docker/
│  └─ docker-compose.yml
└─ docs/
```

## 本地开发

### 后端

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

启动后：API 文档 <http://127.0.0.1:8000/docs>，健康检查 `GET /api/health`。

### 前端

```bash
cd frontend
npm install
npm run dev        # Vite dev server，已代理 /api 到 http://127.0.0.1:8000
```

### 测试

```bash
# 后端
cd backend && pytest

# 前端
cd frontend && npm run test
```

## Docker

```bash
cd docker
APP_SECRET_KEY=$(openssl rand -hex 32) MUSIC_ROOT=/path/to/music docker compose up --build
```

访问 <http://localhost:8000>。数据（SQLite / 缓存）落在挂载的 `./data`，曲库挂载为 `/music`。

## 阶段说明

- **M0 脚手架**（已完成）：工程结构、API 契约、DB 迁移、Docker 最小镜像。
- **M1 MVP（P0）**：库扫描、列表/详情、单条+批量编辑、封面、歌词、在线刮削、日志、任务进度。
