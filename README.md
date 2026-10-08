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
- **M1 MVP（P0）**（已完成）：库扫描（增量）、列表/详情、单条 + 批量编辑、封面读写/导出、
  歌词读写、在线刮削（MusicBrainz + Cover Art Archive + LRCLIB）、操作日志、任务进度推送。
  全链路**不依赖 ffmpeg**。
- **M2 增强（P1）**：试听（Range 流式）、文件名↔标签互转、查找替换、繁简转换、智能整理、多源兜底、封面批处理、指纹识别。
- **M3 重型（P2）**：歌词翻译、ffmpeg 转码、CUE 分轨、播放统计、多用户与权限。

### M1 使用流程

1. 设置页添加音乐库根目录（服务器绝对路径）。
2. 资源库页点「扫描」→ 后台任务通过 `/ws/events` 推送进度。
3. 表格/封面墙浏览，按「缺封面 / 无歌词 / 缺标签」筛选。
4. 点开任意曲目 → 右侧检查器编辑标签、替换封面、写入歌词（`⌘S` 保存）。
5. 多选 → 底部批量条：覆盖 / 仅填空 / 追加 / 查找替换，支持 dry-run 预演。
6. 刮削中心：选曲 → 多源候选（按匹配分排序）→ 字段 diff 对比 → 应用（可仅补空值、带封面/歌词）。
7. 操作日志页查看每次写入的前后值与来源。

