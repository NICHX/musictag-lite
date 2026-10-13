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

## 歌词

歌词来源分两类**分别记录**，便于筛选与展示：

- **内嵌歌词**：写在音频文件的标签容器里；
- **同名歌词文件**：与音频同名的 `.lrc`（标准逐行）与 `.nilyric`（逐字，含字级时间轴）。

资源库按「是否有词」合并筛选（`无歌词`），详情页则分别显示来源（内嵌 / 同名文件 / 逐字）。

**逐字歌词**：在支持逐字的源（酷狗 / QQ 音乐，需在「设置 → 数据源」启用）抓取后，可预览并一键写入
`.lrc` + `.nilyric` 两个同名文件（逐字需支持该标记的播放器）；也可在底部批量条对所选曲目批量抓取。

**AI 双语翻译**：在检查器里选择目标语言（中文 / English / 日本語）后，由模型生成「原文 + 译文」
对照的标准 LRC，确认后再写入。复用「可选 AI 辅助」的配置，默认关闭、仅手动触发，只发送歌词文本。

## 文件名识别与可选 AI 辅助

文件名解析采用**分层收敛**（全部离线，默认可用）：

1. 清洗：剥离 `[FLAC]`、`(Official Video)` 等音质/来源标记；
2. 分段：按 ` - ` / `–` / `—` 切分，并提取 `01 -` 音轨号前缀；
3. **消歧**：用曲库中已出现过的艺术家判断哪个片段是艺术家，从而兼容
   「标题 - 艺术家」与「艺术家 - 标题」两种命名惯例；
4. 查询：MusicBrainz 字段限定查询，命中即止、落空则反向再试；
5. 兜底：标签查询无结果时回退用文件名再查（标签拼错也能救回）；
6. 排序：分词覆盖率打分，与分隔符/顺序无关。

资源库检查器里的「按文件名解析」可**预览**解析结果（字段 old → new），确认后再写入文件。

### 可选 AI 辅助（默认关闭，仅手动触发）

需要模型更强地处理「长括号描述 + 多艺术家 + 冷门曲目」这类规则难拆的文件名时，
可接入任意 **OpenAI 兼容**接口（OpenAI / DeepSeek / 硅基流动 / LM Studio / Ollama…）：

```bash
# backend/.env（本地开发）
AI_ENABLED=true
AI_BASE_URL=https://api.deepseek.com/v1
AI_MODEL=deepseek-chat
AI_API_KEY=sk-xxx
```

隐私与安全约束：**默认关闭**；**只发送文件名字符串**（不含路径、不上传音频）；
**仅在你点击「AI 解析」时调用**，不会在扫描/刮削流程中自动触发；密钥不写日志。
启用后检查器会出现「AI 解析」按钮，解析失败会自动回退到本地规则。

Unraid 上把上述变量写进栈的 `.env`
（`/boot/config/plugins/compose.manager/projects/musictag-lite/.env`）后重启栈即可；
`deploy/unraid/deploy.sh` 会**保留**这些手填的键，重新部署不会覆盖它们。

## Docker 部署

### Unraid（推荐，一键脚本）

仓库内置了可复用的部署脚本，会自动同步源码、注册为 Unraid **Compose Manager 栈**（可在
`Unraid → Docker → Compose` 中启动/停止/更新/编辑/看日志）并构建启动：

```bash
# 默认部署到 root@192.168.31.252，可用环境变量覆盖
deploy/unraid/deploy.sh

# 例：换 NAS / 换端口 / 换曲库
NAS_HOST=root@10.0.0.5 PORT=8080 MUSIC_PATH=/mnt/user/media/music \
  deploy/unraid/deploy.sh
```

默认目录布局（NAS 上）：

| 路径 | 说明 |
| --- | --- |
| `/mnt/user/appdata/musictag-lite/src` | 源码（构建上下文） |
| `/mnt/user/appdata/musictag-lite/data` | SQLite / 配置（持久化） |
| `/boot/config/plugins/compose.manager/projects/musictag-lite` | Compose 栈定义与 `.env` |

### 通用主机（docker compose）

```bash
cd docker
APP_SECRET_KEY=$(openssl rand -hex 32) MUSIC_PATH=/path/to/music docker compose up --build
```

访问 <http://localhost:8000>。曲库挂载为 `/music`，数据落在 `./data`。

## 阶段说明

- **M0 脚手架**（已完成）：工程结构、API 契约、DB 迁移、Docker 最小镜像。
- **M1 MVP（P0）**（已完成）：库扫描（增量）、列表/详情、单条 + 批量编辑、封面读写/导出、
  歌词读写、在线刮削（MusicBrainz + Cover Art Archive + LRCLIB）、操作日志、任务进度推送。
  全链路**不依赖 ffmpeg**。
- **M2 增强（P1）**（已完成）：试听（Range 流式）、文件名↔标签互转、查找替换、繁简转换、智能整理、
  多源兜底（网易云 / QQ 音乐 / 酷狗，社区源**默认关闭**）、封面批处理、AcoustID 指纹识别、
  逐字歌词（预览 + 落盘 `.lrc`/`.nilyric`）、AI 歌词双语翻译、刮削响应 TTL 缓存、跨页「选择全部」批量。
- **M3 重型（P2）**：ffmpeg 转码、CUE 分轨、播放统计、多用户与权限。

### 使用流程

1. 设置页添加音乐库根目录（服务器绝对路径）。
2. 资源库页点「扫描」→ 后台任务通过 `/ws/events` 推送进度。
3. 表格/封面墙浏览，按「缺封面 / 无歌词 / 无逐字歌词 / 缺标签」筛选；标题/艺术家/专辑/文件名最多两行，
   点击封面可放大查看。
4. 点开任意曲目 → 检查器（宽屏为居中弹窗、窄屏为右侧抽屉）编辑标签、替换封面、写入歌词、试听（`⌘S` 保存）；
   可「按文件名解析」或生成「AI 双语翻译」「逐字歌词」并落盘。
5. 多选 → 底部批量条：覆盖 / 仅填空 / 追加 / 查找替换 / 简繁转换、封面、逐字歌词；
   本页全选后可「选择全部 N 首」跨页批量操作。
6. 刮削中心：选曲 → 多源候选（按匹配分排序）→ 字段 diff 对比 → 应用（可仅补空值、带封面/歌词/逐字）；
   返回资源库会自动打开刚匹配曲目的详情。
7. 操作日志页查看每次写入的前后值与来源。

