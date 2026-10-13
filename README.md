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
│  │  ├─ api/          # 路由（REST 契约，含对外 /api/open）
│  │  ├─ core/         # 配置 / DB / 事件 / 任务 / 安全 / 日志
│  │  ├─ models/       # SQLModel 模型与 Pydantic schema
│  │  ├─ audio/        # 音频 IO 抽象（mutagen）
│  │  ├─ extensions/   # 扩展体系（动态加载 / 安装 / 卸载）
│  │  ├─ providers/    # 刮削源（builtin；社区源以可安装扩展提供）
│  │  └─ services/     # 领域服务
│  ├─ extensions/      # 可安装扩展目录（内置 catalog，如 community-cn）
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

歌词只有一种最终产物 —— **逐字 LRC**（数据源或 AI 提供译文时，即「逐字 + 译文」），可写入：

| 目标 | 位置 |
| --- | --- |
| 内嵌 | 音频标签容器 |
| 同名 `.nilyric` | 逐字（含字级时间轴） |
| 同名 `.lrc` | 通用 |

检查器「歌词」区：

- **预览逐字**：从数据源预览逐字歌词（只读）；
- **写入位置**：内嵌 + `.nilyric`（默认）/ 内嵌 + `.lrc` / 仅内嵌 / 仅 `.nilyric` / 仅 `.lrc`；
- **译文来源**：`无译文` / `译文·数据源`（默认，免费）/ `译文·AI`（显式选择，**可能产生费用**；未配置 AI 时不可选）；
- **抓取并写入**：抓取逐字歌词并写入所选位置。

**AI 默认不参与**：只有显式选「译文·AI」才会调用模型——逐字写入与批量抓取**都不会**自动调用 AI。
数据源（网易云 / QQ）的歌词接口本就合并了译文，选「译文·数据源」即可免费并入；不需要译文的歌选「无译文」。
下方只读展示当前歌词。批量场景用资源库底部的「逐字歌词」按钮（写内嵌 + `.nilyric`，仅用数据源译文）；
它是**后台任务**，进度见任务中心，完成后列表会自动刷新。

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

## 扩展（可安装的刮削源）

刮削源以**扩展**形式分发：社区源（网易云 / QQ 音乐 / 酷狗）不再随核心代码内置，而是打包为
可安装扩展（`backend/extensions/community-cn/`，随镜像分发的内置 catalog）。在
**设置 → 扩展** 中一键安装或上传 zip 安装；安装后其 Provider 会动态注册，出现在
「刮削源」列表中（默认关闭，需手动启用）。卸载会注销 Provider 并清理其配置。

- 扩展目录：已安装扩展存放于 `<DATA_DIR>/extensions/<key>/`（随数据卷持久化）。
- 扩展包结构：目录内含 `extension.json` 清单（`key` / `name` / `version` / `providers`）
  与 Provider 模块（模块内用相对导入引用同目录工具模块）。
- 接口：`GET /api/extensions`、`POST /api/extensions/catalog/{key}/install`、
  `POST /api/extensions/install`（上传 zip）、`DELETE /api/extensions/{key}`。

## 对外 API（Token 鉴权）

供外部系统（Navidrome / 脚本 / 自建前端 / 智能音箱等）集成的接口挂在 **`/api/open`**，
开放**核心功能白名单**（浏览 + 匹配 + 单条写入）；管理类与重型接口不开放
（库增删改/扫描、数据源配置、批量编辑、封面替换、整理/转码、任务日志、扩展、设置等仅内部 SPA 使用）。

| 分组 | 端点 | 说明 |
| --- | --- | --- |
| 浏览 | `GET /api/open/health` · `/version` | 健康检查 / 版本 |
| 浏览 | `GET /api/open/libraries` | 音乐库列表 |
| 浏览 | `GET /api/open/providers` | 数据源列表（含启用状态，便于选择匹配源） |
| 浏览 | `GET /api/open/tracks` · `/ids` · `/facets` | 曲目列表 / 命中 id / 聚合计数 |
| 浏览 | `GET /api/open/tracks/{id}` | 曲目详情 |
| 浏览 | `GET /api/open/tracks/{id}/cover` · `/lyrics` · `/stream` | 封面 / 歌词 / 音频流（Range） |
| 匹配 | `POST /api/open/scrape/search` | 发起检索，返回候选（按 track_id 或自定义 query） |
| 匹配 | `POST /api/open/scrape/fingerprint` | 指纹识别（fpcalc → AcoustID → MusicBrainz） |
| 匹配 | `POST /api/open/scrape/apply` | 写入匹配结果（标签/封面/歌词，可仅补空值） |
| 写入 | `PATCH /api/open/tracks/{id}` | 单条标签编辑（落盘） |
| 写入 | `PUT /api/open/tracks/{id}/lyrics` | 歌词写入（内嵌 / .lrc / 两者） |

所有请求需携带令牌：

```bash
# 发起匹配 → 返回候选
curl -H "X-API-Token: <token>" -H "Content-Type: application/json" \
  -d '{"track_id": 12, "limit": 10}' http://<host>:8000/api/open/scrape/search

# 写入匹配结果
curl -H "X-API-Token: <token>" -H "Content-Type: application/json" \
  -d '{"track_id": 12, "candidate_ids": ["musicbrainz:rec-1"], "only_missing": true, "apply_cover": true}' \
  http://<host>:8000/api/open/scrape/apply
```

令牌在 **设置 → 对外 API** 中查看/复制/重新生成，可一键停用。首次访问设置页时自动生成。

## 阶段说明

- **M0 脚手架**（已完成）：工程结构、API 契约、DB 迁移、Docker 最小镜像。
- **M1 MVP（P0）**（已完成）：库扫描（增量）、列表/详情、单条 + 批量编辑、封面读写/导出、
  歌词读写、在线刮削（MusicBrainz + Cover Art Archive + LRCLIB）、操作日志、任务进度推送。
  全链路**不依赖 ffmpeg**。
- **M2 增强（P1）**（已完成）：试听（Range 流式）、文件名↔标签互转、查找替换、繁简转换、智能整理、
  多源兜底（网易云 / QQ 音乐 / 酷狗，以**可安装扩展**提供、默认关闭）、封面批处理、AcoustID 指纹识别、
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

