# MusicTag Lite · 项目设计文档

> 一个轻量的自托管音乐元数据（标签）管理 Web 应用设计说明。
> 目标：对标 [music-tag-web](https://github.com/xhongc/music-tag-web) 的能力，但**更轻、更透明、核心功能全部免费开源**，并采用插件化刮削架构与品牌化产品界面。

| 项 | 内容 |
| --- | --- |
| 文档版本 | v0.1（提案稿） |
| 状态 | 待评审，用于后续另开项目落地 |
| 技术栈 | Python 3.11+ / FastAPI + Vue 3 / Vite |
| 运行方式 | 本地开发运行 + Docker 自托管，二者皆支持 |
| 界面风格 | 品牌产品风（封面驱动、暖色品牌色、深色优先） |
| 刮削数据源 | 插件式，默认启用开放数据源（MusicBrainz 系） |
| 授权建议 | 项目代码 MIT/Apache-2.0；刮削插件独立、可选、默认关闭高风险源 |

---

## 1. 项目概述

### 1.1 背景

自建影音服务（Navidrome / Jellyfin / Plex / Emby）的用户，音乐文件通常存放在 NAS 或 Linux 服务器上。本地的 MP3Tag、MusicBrainz Picard 等工具只能操作本机文件，无法远程批量整理服务器曲库的元数据。music-tag-web 通过 Docker 一键部署解决了这个问题，因此广受欢迎。

但它也存在明显的门槛与痛点：

- **体量重**：Python/Django + 大量依赖 + 内置 ffmpeg/指纹等重型组件，镜像大、启动慢、资源占用高，小主机/NAS 部署有压力。
- **功能杂**：单进程塞进了刮削、转码、分轨、代理、统计等全部能力，耦合度高，二次开发与裁剪困难。
- **高级功能收费/受限**：部分高级能力需要赞助或授权，开源体验被切割。
- **刮削源封闭**：内置的国内音乐平台接口有合规灰区，且用户无法自主选择或替换数据源。

### 1.2 定位与目标

MusicTag Lite 的定位是"**轻量、可插拔、核心全免费**"的音乐标签管理 Web 工具：

1. **轻**：默认依赖尽量少，核心能力（元数据/封面/歌词）只依赖一个音频标签库（mutagen），不强制内置 ffmpeg。
2. **快**：扫描与编辑走本地文件系统 + SQLite 索引，前端为单页应用，交互流畅。
3. **开放**：刮削为**插件体系**，默认启用开放、合规的数据源（MusicBrainz / Cover Art Archive / LRCLIB / AcoustID），用户可自行接入其他源。
4. **透明**：核心功能 100% 开源免费，无功能阉割、无内置收费墙。
5. **好看好用**：品牌化产品级 UI，封面驱动视觉，深色优先，移动端可用。

### 1.3 与 music-tag-web 的差异

| 维度 | music-tag-web | MusicTag Lite |
| --- | --- | --- |
| 后端 | Django（重，含 admin/ORM/全量组件） | FastAPI（轻，异步，接口先行） |
| 前端 | 内置模板 + 前端混合 | 独立 Vue 3 SPA，前后端分离 |
| 媒体处理 | 内置 ffmpeg、指纹、转码、分轨 | 核心不依赖 ffmpeg；重型能力做成**可选模块/外部命令** |
| 刮削 | 内置多平台源（含国内平台，合规灰区） | **插件式 Provider**，默认开放源，高风险源默认关闭 |
| 收费 | 部分高级功能受限/需赞助 | 全部核心功能免费开源 |
| 界面 | 工具型后台风 | 品牌产品风，封面驱动、深色优先 |
| 部署 | Docker 为主 | 本地开发 + Docker 双支持 |

### 1.4 设计原则

- **核心零阻塞**：不装 ffmpeg 也能完成元数据/封面/歌词的读写与刮削。
- **接口先行**：先定 REST API 契约，前后端可并行开发。
- **一切可预期**：批量操作异步化 + 进度可见 + 失败可回滚/可重试。
- **默认安全**：库目录可配置、路径防穿越；刮削网络请求可控、可关。
- **渐进增强**：P0 先做"能看能改能刮"，复杂能力按阶段叠加。

---

## 2. 参考项目功能拆解

music-tag-web 的能力清单（作为对标基线）：

1. 全格式音频元数据查看与单条/批量编辑、ID3 修复
2. 批量自动刮削（专辑、艺术家、歌词、封面）
3. 内置音乐指纹识别（无标签歌曲自动匹配）
4. 智能整理文件（按艺术家/专辑自动分组，多级曲库分类）
5. 多维度排序（文件名、大小、更新时间）
6. 批量繁简转换（歌名/专辑/艺术家）
7. 文件名拆解补全标签
8. 批量文本查找替换
9. 集成 ffmpeg 无损格式转换
10. 整轨 APE/FLAC/CUE 切割分轨并补标签
11. 多源元数据接口（多渠道兜底）
12. 内嵌歌词翻译 / 双语歌词写入
13. 完整操作日志
14. 批量导出/自定义上传替换封面
15. 全响应式移动端 UI
16. 适配小爱同学本地曲库播放
17. 兼容私人网盘挂载曲库在线播放与编辑
18. 播放数据统计（柱状图/折线图）

**我们的取舍**：全部纳入规划，但按"核心 → 增强 → 重型"分层，明确分期（见第 4、12 章）。第 16、17 项属于集成型需求，通过"提供标准 API / WebDAV 友好路径"间接满足，不单独作为核心模块。

---

## 3. 目标用户与核心场景

### 3.1 用户画像

- **A. NAS/Homelab 自建玩家**：音乐库在 NAS，用 Navidrome/Jellyfin 播放，需要远程批量修正标签与封面。
- **B. 无损曲库收藏者**：拥有大量 FLAC/APE/DSF，重视标签规范、封面与歌词完整性。
- **C. 轻度整理用户**：希望有个好看、开箱即用的网页工具来给下载的歌曲补标签。

### 3.2 核心用户故事（P0）

- 作为用户，我能**扫描**一个音乐库目录，看到所有曲目及标签状态。
- 作为用户，我能**单条编辑**某首歌的标题/艺术家/专辑/年份/流派/音轨号并保存。
- 作为用户，我能**多选批量**修改同一字段（如统一专辑名、流派）。
- 作为用户，我能**查看/替换/导出封面**，并让封面出现在浏览与编辑界面。
- 作为用户，我能**查看/写入歌词**（.lrc 或内嵌）。
- 作为用户，我能对某首歌**自动刮削匹配**元数据与封面，并从候选结果中选择。
- 作为用户，我能看到**批量任务的进度**和**操作日志**。

### 3.3 典型工作流

```
导入/扫描曲库 → 浏览筛选（缺封面/无标签/格式）→ 批量选中
        → 刮削匹配（选择候选）→ 预览对比 → 应用
        → （可选）重命名整理 / 转码 / 分轨 → 查看日志
```

---

## 4. 功能需求（全量对标 + 分期）

### 4.1 功能矩阵总表

优先级：**P0 = MVP 首版**；**P1 = 增强**；**P2 = 重型/长期**。

| # | 功能 | 阶段 | 说明 |
| --- | --- | --- | --- |
| F1 | 曲库目录配置与扫描（增量） | P0 | 支持多库根目录，增量扫描，进度可见 |
| F2 | 元数据查看（列表 + 详情） | P0 | 全格式核心字段 + 技术参数 |
| F3 | 单条编辑标签 | P0 | 标题/艺术家/专辑/专辑艺术家/年份/音轨/碟号/流派/作曲等 |
| F4 | 批量编辑标签 | P0 | 多选后统一改字段，支持追加/覆盖/正则替换 |
| F5 | 封面查看/替换/删除/导出 | P0 | 内嵌封面 + 同名 cover.jpg 兜底 |
| F6 | 歌词查看/写入 | P0 | 内嵌歌词 + .lrc 边车文件 |
| F7 | 在线刮削匹配（单条/批量） | P0 | 插件式 Provider，候选选择后应用 |
| F8 | 操作系统排序/筛选/搜索 | P0 | 文件名、大小、更新时间、缺失字段筛选 |
| F9 | 操作日志 | P0 | 记录每次写入的前后值与时间 |
| F10 | 音频在线试听（预览） | P1 | HTTP Range 流式播放 |
| F11 | 文件名↔标签互转（拆解/格式化重命名） | P1 | 从文件名补标签 / 按模板重命名 |
| F12 | 批量文本查找替换 | P1 | 清理脏标签、乱码、特殊字符 |
| F13 | 繁简转换 | P1 | 歌名/专辑/艺术家批量转换 |
| F14 | 音乐指纹识别（AcoustID） | P1 | 无标签/文件名混乱歌曲自动识别 |
| F15 | 智能整理（按艺术家/专辑移动分组） | P1 | 移动/重命名文件，支持多级分类模板 |
| F16 | 多源兜底刮削 | P1 | 多 Provider 聚合、优先级与打分 |
| F17 | 歌词翻译 / 双语写入 | P2 | 需外部翻译服务或模型 |
| F18 | 格式转换（ffmpeg） | P2 | 可选模块，检测到 ffmpeg 才启用 |
| F19 | 整轨 CUE/APE/FLAC 分轨 | P2 | 可选模块，依赖 ffmpeg/shntool |
| F20 | 封面批量导出/批量上传替换 | P1 | 批量场景 |
| F21 | 播放统计图表 | P2 | 需配合播放端埋点或读取播放记录 |
| F22 | 多用户与权限 | P2 | 单用户起步，后续加认证与角色 |
| F23 | 移动端适配 | P0 起 | 响应式贯穿，非独立工程 |
| F24 | 网盘挂载曲库兼容 | P1 | 依赖标准文件系统挂载，路径可配置 |

### 4.2 P0（MVP）详细需求

**F1 扫描**
- 支持配置 1..N 个库根目录；扫描采用后台任务，WebSocket/SSE 推送进度。
- 增量扫描：以 `路径 + 修改时间 + 文件大小` 判断是否需要重新读取标签。
- 忽略隐藏文件与常见临时文件；支持扩展名白名单。

**F2/F3/F4 元数据**
- 读取字段（按格式映射，见附录 A）：标题、艺术家、专辑、专辑艺术家、音轨号、碟号、年份/日期、流派、作曲、注释、歌词（内嵌）、封面（内嵌）。
- 技术参数（只读）：时长、码率/模式、采样率、声道、位深、编码器、文件大小、格式。
- 编辑：单条表单保存；批量按"**覆盖 / 仅填充空值 / 追加 / 查找替换**"四种策略写入。
- 写入前生成"变更预览（diff）"，确认后落盘，并写日志。

**F5 封面**
- 读取：优先内嵌（APIC/PICTURE/COVER），其次目录下的 `cover.jpg/folder.jpg/front.jpg`。
- 写入：内嵌封面（可指定类型 front/back 等）、或写入目录同名文件。
- 导出：单条/批量导出为文件。

**F6 歌词**
- 读取：内嵌歌词（USLT/LYRICS/©lyr）→ 同名 `.lrc` 文件。
- 写入：内嵌或 `.lrc`（可选），支持 LRC 时间轴校验与预览。

**F7 刮削**
- Provider 抽象（详见第 9 章）；默认 Provider：MusicBrainz（元数据）+ Cover Art Archive（封面）+ LRCLIB（歌词）。
- 流程：选中曲目 → 生成查询（优先已有标签：专辑+艺术家；兜底文件名解析）→ 拉取候选列表 → 用户逐条/批量选择 → diff 预览 → 应用。
- 支持"仅补全缺失字段"，避免覆盖人工已修正的标签。

**F8 排序/筛选/搜索**
- 排序：文件名、路径、大小、修改时间、时长、音轨号。
- 筛选：有无封面、有无歌词、缺标题/艺术家/专辑、格式、位深、采样率。
- 搜索：标题/艺术家/专辑/文件名模糊匹配。

**F9 日志**
- 记录：操作类型、目标文件、字段、旧值、新值、时间、结果、来源（手动/刮削/批量）。

### 4.3 P1 详细需求（要点）

- **F10 试听**：`GET /api/tracks/{id}/stream` 支持 `Range`，前端用 HTMLAudioElement/WaveSurfer.js。
- **F11 文件名互转**：解析模板如 `%artist% - %title%`，双向转换。
- **F12 查找替换**：支持普通串与正则，可限定字段范围，批量预览。
- **F13 繁简转换**：内置 OpenCC（`opencc-python-reimplemented` 或纯词表）离线转换。
- **F14 指纹**：`fpcalc`（Chromaprint）生成指纹 → AcoustID 查询 → 转 MusicBrainz 匹配。
- **F15 整理**：模板化路径，如 `{albumartist}/{year} - {album}/{track:02d} - {title}`，移动前预览冲突/重名。
- **F16 多源聚合**：并发查询多 Provider，按匹配分排序合并，记录来源。
- **F20 封面批处理**：从文件批量上传并分发到同专辑曲目；批量导出到目录。

### 4.4 P2 详细需求（要点）

- **F17 歌词翻译/双语**：接入可选翻译服务（自建/第三方 API/本地模型），生成双语 LRC。
- **F18 转码**：检测系统 `ffmpeg`，提供 FLAC↔MP3/ALAC/WAV 等转换，任务队列化。
- **F19 分轨**：解析 CUE，按轨切割并写入独立标签，依赖外部工具。
- **F21 统计**：可选，读取 Navidrome/Jellyfin 播放记录或自建轻量埋点。
- **F22 多用户**：登录 + 角色（管理员/只读），首版可用单用户+可选密码。

### 4.5 明确不做 / 延后

- 不提供任何音乐本体下载；仅编辑本地已有文件元数据。
- 不内置需授权的流媒体内容。
- 高风险第三方源不内置，仅以"社区插件"形式存在，默认关闭。

---

## 5. 非功能需求

| 类别 | 要求 |
| --- | --- |
| 性能 | 单目录 5 万曲目扫描可增量；列表接口分页 ≤ 200ms；编辑落盘实时反馈 |
| 并发 | 扫描/刮削/转码走后台任务，可配置并发度，避免打满磁盘与网络 |
| 隐私 | 曲库文件默认不上传第三方；仅刮削时向所选源发送查询字段 |
| 兼容 | 覆盖主流音频格式（附录 A）；主流浏览器（Chrome/Edge/Safari/Firefox 近两年版本） |
| 部署 | 本地 `uvicorn` + `vite dev`；Docker 单容器（前端静态 + 后端 API）或 compose |
| 安全 | 库根目录白名单校验、防路径穿越、上传类型/大小限制；可选密码/Token 鉴权 |
| 可观测 | 结构化日志 + 任务状态表 + 操作审计日志 |
| 可测试 | 后端 pytest（含固定音频 fixture），前端 Vitest；核心逻辑纯函数化 |
| 无障碍 | WCAG AA 对比度、键盘可达、`prefers-reduced-motion` 尊重 |
| 国际化 | 中文优先，预留 i18n（vue-i18n） |

---

## 6. 技术架构

### 6.1 总体架构

```
┌──────────────────────────────────────────────────────────────┐
│                        浏览器 (Vue 3 SPA)                       │
│  资源库浏览 │ 编辑检查器 │ 批量操作台 │ 刮削匹配 │ 设置 │ 日志      │
└───────────────▲───────────────────────────────┬──────────────┘
                │ REST /api/*            WS /ws/events (进度)
┌───────────────┴───────────────────────────────▼──────────────┐
│                     FastAPI 应用层 (async)                     │
│  Routers: library, tracks, tags, covers, lyrics, scrape,      │
│           organize, convert, logs, providers, settings, auth  │
├──────────────────────────────────────────────────────────────┤
│                        服务/领域层                              │
│  Scanner │ TagService │ CoverService │ LyricsService          │
│  ScrapeOrchestrator │ OrganizeService │ TaskQueue │ EventBus  │
├──────────────────────────────────────────────────────────────┤
│                          基础能力层                             │
│  AudioIO(mutagen) │ Provider Plugins │ FFServices(可选)        │
│  DB(SQLite) │ Cache │ Config │ Logging                        │
└──────────────────────────────────────────────────────────────┘
```

### 6.2 后端选型与分层

- **Web 框架**：FastAPI + Uvicorn（异步、类型友好、自动 OpenAPI 文档）。
- **校验/序列化**：Pydantic v2。
- **ORM/DB**：SQLModel（SQLAlchemy + Pydantic）或 SQLAlchemy 2.0 + SQLite（WAL 模式）。
- **迁移**：Alembic。
- **任务系统 P0**：进程内异步任务 + 任务表（轻量、无外部依赖）。P1 可切到 `arq`/Celery（Redis）可选。
- **实时进度**：WebSocket（`/ws/events`）为主，SSE 作为降级。
- **HTTP 客户端**：httpx（异步、连接池、超时、重试）。
- **配置**：pydantic-settings + `.env` + `config.yaml`。

### 6.3 音频处理层

- **核心库**：**mutagen**（纯 Python，无外部依赖），负责读取/写入主流格式标签与封面、歌词。
- **可选重型工具**：`ffmpeg`/`fpcalc`，仅在检测到可执行文件时才启用对应模块（转码、分轨、指纹）。缺失时相关入口隐藏或提示。
- **格式与标签容器映射**：见附录 A。

### 6.4 扫描与任务系统

- 扫描器遍历库根目录 → 对比索引（路径/大小/mtime）→ 只读取变化项 → 更新 DB。
- 所有长任务（扫描、批量写入、刮削、转码、整理）抽象为 `Task`：
  - 状态：`queued/running/succeeded/failed/cancelled`
  - 进度：`processed/total`、当前文件、耗时、错误样本
  - 通过 EventBus → WebSocket 推送。
- 支持取消与失败重试；批量写入具备"预演（dry-run）"能力。

### 6.5 数据存储

- **SQLite**（库索引、任务、日志、设置、Provider 配置）。单文件、零运维，符合"轻量自托管"。
- 大文件/封面不入库：封面落盘到缓存目录或按需从文件流式返回。
- 索引仅为加速，**文件系统为唯一事实来源**（可随时重建）。

### 6.6 前端技术栈

- **框架**：Vue 3（`<script setup>` + Composition API）+ TypeScript。
- **构建**：Vite。
- **路由/状态**：Vue Router + Pinia。
- **样式**：Tailwind CSS v4 + CSS 变量（设计令牌，见第 10 章）。
- **组件库**：优先自研轻组件 + `radix-vue`（无样式、可访问性佳）作为可组合原语；不套用默认主题。
- **数据请求**：`ofetch`/`axios` + TanStack Query for Vue（缓存、重试）可选。
- **音频**：WaveSurfer.js（试听，P1）。
- **图标**：Lucide 或自绘 SVG（统一线宽）。
- **实时**：原生 WebSocket 封装。

### 6.7 目录结构（建议）

```
musictag-lite/
├─ backend/
│  ├─ app/
│  │  ├─ main.py                 # FastAPI 入口
│  │  ├─ api/                    # routers
│  │  │  ├─ library.py tracks.py tags.py covers.py lyrics.py
│  │  │  ├─ scrape.py organize.py convert.py logs.py
│  │  │  ├─ providers.py settings.py auth.py ws.py
│  │  ├─ core/                   # 配置、DB、事件、任务、安全
│  │  │  ├─ config.py db.py events.py tasks.py security.py logging.py
│  │  ├─ services/               # 领域服务
│  │  │  ├─ scanner.py tag_service.py cover_service.py lyrics_service.py
│  │  │  ├─ scrape_orchestrator.py organize_service.py convert_service.py
│  │  ├─ audio/                  # 音频 IO 抽象
│  │  │  ├─ base.py mutagen_io.py formats.py
│  │  ├─ providers/              # 刮削源
│  │  │  ├─ base.py registry.py
│  │  │  └─ builtin/ musicbrainz.py coverart.py lrclib.py acoustid.py
│  │  ├─ extensions/             # 扩展体系（动态加载 / 安装 / 卸载）
│  │  └─ models/                 # DB 模型与 Pydantic schema
│  ├─ extensions/               # 可安装扩展目录（内置 catalog；社区源以扩展形式分发）
│  ├─ tests/
│  ├─ pyproject.toml
│  └─ Dockerfile
├─ frontend/
│  ├─ src/
│  │  ├─ main.ts App.vue
│  │  ├─ router/ stores/ api/
│  │  ├─ views/  (Library, TrackDetail 侧栏, Batch, Scrape, Settings, Logs)
│  │  ├─ components/ (DataTable, Inspector, CoverPicker, LyricsEditor,
│  │  │              ScrapeCompare, TaskCenter, CommandPalette, ...)
│  │  ├─ design/ (tokens.css, theme.ts)
│  │  └─ assets/ (fonts, icons)
│  ├─ index.html
│  ├─ vite.config.ts
│  ├─ tailwind.config.ts
│  └─ package.json
├─ docker/ docker-compose.yml
├─ docs/  (本设计文档及后续文档)
└─ README.md
```

---

## 7. 数据模型

> SQLite 表；仅列关键字段。`Track` 是索引与文件系统快照，文件系统为准。

### 7.1 Track

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | int PK | |
| library_id | FK | 所属库 |
| path | text unique | 绝对路径 |
| dirname | text | 目录 |
| filename | text | 文件名 |
| ext | text | 扩展名 |
| format | text | FLAC/MP3/... |
| size | int | 字节 |
| mtime | datetime | 修改时间 |
| duration | float | 秒 |
| bitrate | int | bps |
| sample_rate | int | Hz |
| channels | int | |
| bit_depth | int | 位深（无损） |
| title/artist/album/album_artist/composer/genre | text | 常用标签 |
| track_no/disc_no | int | |
| year/date | text | |
| comment | text | |
| has_cover | bool | 是否有内嵌封面 |
| cover_mtime | datetime | 封面文件时间（兜底） |
| has_lyrics | bool | |
| tag_status | text | OK/MISSING_TITLE/...（便于筛选） |
| scan_hash | text | 内容/属性指纹（可选） |
| created_at/updated_at | datetime | |

### 7.2 其他表

- **Library**：`id, name, root_path, enabled, scan_mode, created_at`。
- **CoverCache**：`id, track_id, mime, width, height, cached_path, source(embedded/file/scraped)`。
- **LyricsCache / LyricsAsset**：`track_id, format(lrc/embedded), content_ref, source`。
- **ScrapeJob**：`id, scope(单/批量), provider_ids, status, query_json, created_at`。
- **ScrapeCandidate**：`id, job_id, track_id, provider, external_id, score, payload_json, selected`。
- **Task**：`id, type, status, total, processed, message, error, started_at, finished_at`。
- **OperationLog**：`id, track_id, action, field, old_value, new_value, source, result, created_at`。
- **ProviderConfig**：`id, provider_key, enabled, priority, options_json`。
- **Setting**：`key, value_json`。
- **User**（P2）：`id, username, password_hash, role`。

---

## 8. API 设计

统一前缀 `/api`。返回 JSON；错误遵循 `{ "detail": "..." }`；列表统一分页 `?page&page_size&sort&order`。

### 8.1 库与曲目

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/libraries` / POST / PATCH / DELETE | 库管理 |
| POST | `/libraries/{id}/scan` | 触发扫描，返回 task_id |
| GET | `/tracks` | 列表：筛选/排序/分页/搜索 |
| GET | `/tracks/{id}` | 详情（含技术参数与标签） |
| PATCH | `/tracks/{id}` | 单条编辑（body: 字段集合） |
| POST | `/tracks/batch` | 批量编辑（body: ids + field ops + strategy） |
| POST | `/tracks/batch/preview` | 批量变更预演（dry-run diff） |
| GET | `/tracks/{id}/stream` | 音频流（支持 Range，P1） |
| GET | `/tracks/facets` | 聚合计数（格式/年份/艺术家等），用于筛选面板 |

### 8.2 封面 / 歌词

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/tracks/{id}/cover` | 返回封面二进制（可带 `?size=`） |
| PUT | `/tracks/{id}/cover` | 上传/替换（multipart） |
| DELETE | `/tracks/{id}/cover` | 删除内嵌封面 |
| POST | `/covers/batch-export` | 批量导出封面到目录 |
| GET | `/tracks/{id}/lyrics` | 返回歌词（内嵌优先，其次同名 `.lrc` / `.nilyric`） |
| PUT | `/tracks/{id}/lyrics` | 写入歌词文本（内嵌 / `.lrc` / 两者） |
| POST | `/tracks/{id}/lyrics/word` | 抓取逐字歌词写入内嵌 / `.nilyric` / `.lrc`；译文 `translation=none\|source\|ai`（默认 `source`，AI 需显式选择） |

### 8.3 刮削

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/providers` | 列出已注册 Provider 及启用状态 |
| PATCH | `/providers/{key}` | 启用/优先级/选项 |
| POST | `/scrape/search` | 输入 track_id 或查询词 → 候选列表 |
| POST | `/scrape/apply` | 应用选中的候选（可仅补空值） |
| POST | `/scrape/jobs` | 批量刮削任务 |
| GET | `/scrape/jobs/{id}` | 任务详情与结果 |

### 8.4 整理 / 转换 / 日志 / 设置 / 实时

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/organize/preview` | 按模板预演重命名/移动 |
| POST | `/organize/apply` | 执行整理 |
| POST | `/convert` | 转码任务（P2，需 ffmpeg） |
| GET | `/logs` | 操作日志查询 |
| GET/PATCH | `/settings` | 应用设置 |
| GET | `/extensions` | 列出已安装扩展与可安装（内置目录）扩展 |
| POST | `/extensions/catalog/{key}/install` | 从内置目录一键安装扩展 |
| POST | `/extensions/install` | 上传扩展 zip 安装 |
| DELETE | `/extensions/{key}` | 卸载扩展（注销 Provider 并清理配置） |
| GET/PATCH | `/settings/api-token` | 对外 API 令牌（查看 / 启停 / 重新生成） |
| GET | `/open/*` | 对外 API：核心功能白名单（浏览 + 匹配 + 单条写入），Token 鉴权；不含管理类接口 |
| POST | `/auth/login` / `/auth/logout` | 鉴权（可选启用） |
| WS | `/ws/events` | 任务与进度事件推送 |

**事件消息示例**

```json
{ "type": "task.progress", "task_id": 42, "kind": "scan",
  "status": "running", "processed": 1234, "total": 5600,
  "current": "/music/a.flac" }
```

---

## 9. 在线刮削插件架构

### 9.1 Provider 接口

所有刮削源实现统一接口，按能力声明可用性：

```python
class MetadataProvider(Protocol):
    key: str                      # 唯一标识，如 "musicbrainz"
    name: str                     # 展示名
    capabilities: set[str]        # {"metadata","cover","lyrics","fingerprint"}

    async def search(self, q: ScrapeQuery) -> list[Candidate]: ...
    async def fetch(self, external_id: str) -> AlbumBundle: ...
    async def fetch_cover(self, external_id: str) -> CoverBytes | None: ...
    async def fetch_lyrics(self, q: ScrapeQuery) -> Lyrics | None: ...
    async def identify(self, fingerprint: str, duration: int) -> list[Candidate]: ...  # 可选
```

- `ScrapeQuery`：`title, artist, album, track_no, duration, filename_hint, fingerprint`。
- `Candidate`：`provider, external_id, title, artist, album, year, track_no, score, cover_url`。
- `AlbumBundle`：规范化后的元数据集合。

### 9.2 内置（默认启用，开放合规）

| Provider | 能力 | 说明 |
| --- | --- | --- |
| **MusicBrainz** | metadata | WS/2 API；需设置 User-Agent；限速 1 req/s，带缓存 |
| **Cover Art Archive** | cover | `coverartarchive.org/release/{mbid}` |
| **LRCLIB** | lyrics | 开放歌词 API，无需 Key，支持精确/模糊查询 |
| **AcoustID** | fingerprint | 需申请 API Key（P1），用于指纹识别 |

### 9.3 可插拔机制

- Provider 以模块形式注册到 `registry`：**内置源**随核心代码集成（`providers/builtin`），
  **社区/高风险源**以**可安装扩展**形式分发（`backend/extensions/<key>/`，含 `extension.json`
  清单），运行时从 `<DATA_DIR>/extensions/<key>/` 动态加载；用户可一键安装/卸载。
- `extension.json` 清单声明 key / name / version / providers；Provider 类属性声明能力与默认开闭状态。
- 用户可在设置页启用/禁用、调整优先级；多源聚合时按匹配分排序并标注来源。
- **网络层统一出口**：所有 Provider 经同一 httpx 客户端，集中处理超时/重试/代理/限流/磁盘缓存。

### 9.4 匹配与打分（简述）

- 查询构造优先级：`已有标签(专辑+艺术家+标题)` → `文件名解析` → `指纹`。
- 打分维度：标题相似度、艺术家一致性、专辑一致性、时长接近度、音轨号一致性、来源可信度。
- **原唱优先**：弱化"平台搜索名次"（名次高 ≠ 原唱）；艺术家权重较高且**明显不符时降级**；
  标题/专辑含「翻唱 / 伴奏 / 纯音乐 / live / remix…」等版本标记时降级；时长差异过大时降级。
- 默认策略：**高置信自动应用仅补空值**；低于阈值的进入人工确认。

### 9.5 合规与免责

- 项目默认仅启用**开放数据源**；不内置任何未授权内容接口。
- 社区插件由用户自行选择与承担合规责任；文档明确风险提示。
- 不下载音乐本体；刮削数据仅用于本地元数据整理。
- 建议项目声明：GPL/MIT 等开源许可 + 使用条款免责声明（可参考通用做法）。

---

## 10. UI/UX 设计（品牌产品风）

### 10.1 视觉方向决策简报

- **表面类型**：操作型 Web 应用（Editor/Inspector + 数据表格 + 任务中心）。**偏重可用密度与状态可见性**，而非营销页的视觉奇观。
- **方向**：品牌产品风（Branded product-led）——有明确品牌色、封面驱动配色、消费者音乐产品的质感，但保持工具的高信息密度。
- **概念种子（Concept seed）**：**"唱片墙 + 工作台"**。左侧是可视化的音乐（封面网格），右侧是精密的工作台（检查器/表单/任务）。封面是唯一的大面积图像来源，界面其余部分克制。
- **反复出现的母题（Motif）**：**"封面取色"**——当前选中曲目/专辑的主色会被提取，用于高亮、进度、选中态与"正在编辑"条，让界面随内容呼吸。
- **一个克制的风险**：**封面驱动的动态强调色**（而非固定强调色）——既有辨识度，又不破坏工具稳定性。
- **禁止的默认**：紫色→粉色渐变、Inter/Space Grotesk 主字体、三卡片套路、`rounded-2xl` 全局滥用、默认 shadcn 主题原样照搬、emoji 项目符号、占位图。

### 10.2 设计令牌（Design Tokens）

**色彩（深色优先，暖色墨底）**

| 令牌 | 值（深色） | 用途 |
| --- | --- | --- |
| `--bg` | `oklch(0.16 0.012 40)` | 页面底色（暖近黑，非纯黑） |
| `--surface` | `oklch(0.21 0.014 40)` | 卡片/表格/面板 |
| `--surface-2` | `oklch(0.25 0.014 40)` | 悬浮/次级面板 |
| `--border` | `oklch(0.31 0.012 40)` | 分隔线/边框 |
| `--text` | `oklch(0.95 0.006 60)` | 主文本 |
| `--text-muted` | `oklch(0.72 0.012 50)` | 次要文本/元数据 |
| `--brand` | `#FF5A36` | 品牌主色（暖朱橙 Ember） |
| `--brand-600` | `#E8431F` | 悬停/按下 |
| `--accent-dynamic` | 运行时注入 | 由封面提取的主色 |
| `--success` | `#3FBF7F` | 成功/已完成 |
| `--warning` | `#F5B301` | 警示/待处理 |
| `--danger` | `#F0524B` | 危险/错误 |
| `--info` | `#5B9DF5` | 信息 |

**浅色主题**：底色 `#FAF7F2`（暖白），文本 `oklch(0.24 0.02 40)`，边框降透明度；品牌色不变。

**字体**

- 拉丁 Display/标题：**Clash Display** 或 **Bricolage Grotesque**（有性格，替代 Inter）。
- CJK 显示：**MiSans** / **HarmonyOS Sans SC**。
- 正文/UI：**Satoshi** / **General Sans** + HarmonyOS Sans SC 回退。
- 等技术数据（码率/采样率/大小/代码）：**JetBrains Mono**。
- 全部 `font-display: swap`，本地或 Fontshare/CDN 自托管。

**字号阶梯**：`12 / 13 / 14 / 16 / 20 / 24 / 32 / 40`，行高 1.4–1.6。

**间距**：4px 基准（4/8/12/16/24/32/48）。**圆角**：控件 8px、卡片 12px、标签 pill。**阴影**：暖色调、低扩散、仅浮层使用。**动效**：`cubic-bezier(0.2,0.8,0.2,1)`，时长 120–240ms。

### 10.3 信息架构与导航

```
顶部：Logo │ 全局搜索(⌘K) │ 扫描状态 │ 任务中心 │ 主题切换 │ 设置
左侧栏（可折叠）：
  资源库（封面网格/表格）│ 筛选收藏（缺封面/无标签/重复）
  刮削中心 │ 整理/转换 │ 任务与日志 │ 设置
主区域：内容视图（网格/表格/详情检查器）
底部（可选）：迷你播放条（试听 + 封面取色）
```

### 10.4 关键界面布局

1. **资源库浏览**（核心）
   - 视图切换：**封面网格** / **紧凑表格**。
   - 表格列：封面缩略、标题、艺术家、专辑、时长、格式、码率、标签状态（徽标）、修改时间。
   - 顶部工具条：搜索、筛选 chips、排序、批量选择。
   - 多选后底部升起**粘性批量操作条**（改字段/刮削/加封面/导出/整理）。
   - 选中行/卡片用 `--accent-dynamic` 高亮描边。

2. **曲目详情检查器**（右侧滑入 Slide-over）
   - 区块：封面 + 试听；基础标签表单；技术参数（mono）；歌词编辑；来源与日志。
   - 底部：保存 / 保存并下一条 / 重置。支持键盘 `J/K` 上下曲、`⌘S` 保存。

3. **刮削匹配页**
   - 左侧：待处理曲目队列；右侧：候选列表（可多源）。
   - 候选卡片显示来源、匹配分、字段差异 **diff**（当前 vs 候选，绿/红）。
   - 操作：应用选中 / 仅补空值 / 应用全部高置信。

4. **任务中心 / 日志**
   - 运行中任务卡片：进度条、已处理/总数、当前文件、暂停/取消。
   - 日志表格：时间、文件、字段、旧值→新值、来源、结果。

5. **设置**
   - 库路径管理、Provider 开关与优先级、外部工具检测（ffmpeg/fpcalc）、路径模板、主题与语言、鉴权。

### 10.5 组件清单（前端）

`AppShell`、`SideNav`、`TopBar`、`CommandPalette`(⌘K)、`CoverGrid`、`TrackTable`(虚拟滚动)、`SelectionBar`、`InspectorPanel`、`TagForm`、`CoverPicker`、`LyricsEditor`、`ScrapeCompare`、`DiffBadge`、`TaskCenter`、`LogTable`、`Toast`、`ConfirmDialog`、`EmptyState`、`MiniPlayer`。

### 10.6 交互与动效预算（克制，2–4 个签名交互）

1. **检查器滑入**：右侧 Slide-over + 背景轻微模糊，150–200ms。
2. **封面取色强调**：选中/播放时从封面提取主色注入 `--accent-dynamic`，用于高亮与进度（渐变过渡 ~240ms）。
3. **⌘K 命令面板**：任意页快速跳转/执行（扫描、刮削、切换视图）。
4. **粘性批量操作条**：多选时底部升起，展示已选数量与批量动作。

> 明确**不**使用：Lenis 平滑滚动、自定义光标、滚动钉住、3D tilt 等营销页动效。全部动效尊重 `prefers-reduced-motion`。

### 10.7 响应式与无障碍

- **断点**：移动 <768 / 平板 768–1024 / 桌面 >1024。移动端表格降级为卡片列表；侧栏改为抽屉；检查器全屏化。
- 工具栏/表格在窄屏**区域内横向滚动**，绝不产生页面级横向溢出。
- 语义化标签、可见 `:focus-visible` 焦点环、AA 对比度、可键盘完成全流程操作。

---

## 11. 部署方案

### 11.1 本地开发

```bash
# 后端
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000

# 前端
cd frontend
npm install
npm run dev        # Vite dev server，代理 /api 到 8000
```

### 11.2 Docker（单镜像，推荐）

- 多阶段构建：Node 构建前端静态资源 → Python 运行时镜像，FastAPI 同时托管 `/api` 与前端静态文件。
- 挂载：`/music`（曲库只读或读写）、`/data`（SQLite/配置/缓存）。
- 端口：`8000`。

```yaml
# docker/docker-compose.yml
services:
  musictag-lite:
    image: musictag-lite:latest
    container_name: musictag-lite
    ports: ["8000:8000"]
    environment:
      - APP_SECRET_KEY=${APP_SECRET_KEY:?set a unique key}
      - MUSIC_ROOT=/music
      - DATA_DIR=/data
    volumes:
      - /path/to/your/music:/music:rw
      - ./data:/data
    restart: unless-stopped
```

> 说明：P0 核心不需要 ffmpeg；如需转码/分轨/指纹，可在镜像中附加或挂载 ffmpeg，并通过设置页检测启用。

---

## 12. 开发路线图（分期里程碑）

| 阶段 | 目标 | 主要内容 |
| --- | --- | --- |
| **M0 脚手架** | 跑通骨架 | 前后端工程、API 契约、DB 迁移、Docker 最小镜像 |
| **M1 MVP（P0）** | 能看能改能刮 | 库配置与扫描、列表/详情、单条+批量编辑、封面、歌词、MusicBrainz/CAA/LRCLIB 刮削、日志、任务进度 |
| **M2 增强（P1）** | 效率与整理 | 试听、文件名互转、查找替换、繁简转换、智能整理、多源兜底、封面批处理、指纹识别 |
| **M3 重型（P2）** | 进阶能力 | 歌词翻译/双语、ffmpeg 转码、CUE 分轨、播放统计、多用户与权限 |
| **M4 打磨** | 体验与生态 | 移动端优化、i18n、插件市场（社区源）、性能与可访问性打磨 |

**验收基线（M1）**：给定一个含 1000 首混合格式的目录，可完成扫描 → 筛选"无封面" → 批量刮削并应用 → 单条编辑落盘 → 导出封面，全程有进度与日志，且不安装 ffmpeg。

---

## 13. 风险与合规

| 风险 | 影响 | 应对 |
| --- | --- | --- |
| 各格式标签容器差异大 | 写入错误/损坏文件 | 用 mutagen 统一抽象；写入前备份关键字段；充分单测 fixture |
| 刮削源限速/变更 | 匹配失败率上升 | 缓存 + 限速 + 多源兜底 + 可插拔替换 |
| 第三方音乐源版权/合规 | 法律风险 | 默认仅开放源；高风险源以社区插件形式、默认关闭并免责 |
| 大曲库性能 | 扫描慢/卡顿 | 增量扫描、分页、虚拟滚动、后台任务 |
| 文件写入安全 | 数据丢失 | dry-run 预览、操作日志、可选"写入前备份" |
| 路径穿越 | 安全漏洞 | 严格校验路径位于库根目录内 |
| 依赖膨胀导致"又变重" | 违背初衷 | 核心零 ffmpeg；重型能力做成可选模块；依赖最小化 |

---

## 14. 后续扩展方向

- 播放端联动：对接 Navidrome/Jellyfin API 读取播放记录与收藏。
- 重复曲目检测（音频指纹 / 标签相似度）。
- WebDAV / S3 挂载曲库（远程存储后端抽象）。
- 插件市场：一键安装社区 Provider。
- 移动端 PWA 与离线缓存。
- 多语言与主题市场。

---

## 附录 A · 格式与标签容器映射

| 格式 | mutagen 模块 | 标签容器 | 封面 | 歌词 |
| --- | --- | --- | --- | --- |
| MP3 | `mutagen.id3` | ID3v2.3/2.4 | APIC | USLT |
| FLAC | `mutagen.flac` | Vorbis Comment | PICTURE | Vorbis `LYRICS` |
| OGG Vorbis | `mutagen.oggvorbis` | Vorbis Comment | METADATA_BLOCK_PICTURE | `LYRICS` |
| Opus | `mutagen.oggopus` | Vorbis Comment | METADATA_BLOCK_PICTURE | `LYRICS` |
| M4A/MP4 | `mutagen.mp4` | iTunes MP4 | `covr` | `©lyr` |
| WMA/ASF | `mutagen.asf` | ASF | WM/Picture | (受限) |
| APE | `mutagen.apev2` | APEv2 | APEv2 `Cover Art` | `Lyrics` |
| WavPack | `mutagen.wavpack` | APEv2 | 同上 | 同上 |
| WAV | `mutagen.wave` | ID3/INFO | ID3 APIC | ID3 USLT |
| AIFF | `mutagen.aiff` | ID3 | APIC | USLT |
| DSF | `mutagen.dsf` | ID3 | APIC | USLT |
| Musepack | `mutagen.musepack` | APEv2 | APEv2 | APEv2 |
| TrueAudio | `mutagen.tta` | ID3 | APIC | USLT |

> DFF 等未列举格式以"只读/不保证写入"处理，UI 明确标注支持等级。

## 附录 B · 术语表

- **刮削（Scrape）**：从在线数据源获取并补全元数据/封面/歌词。
- **Provider**：刮削数据源插件。
- **指纹（Fingerprint）**：基于音频内容的声学指纹（Chromaprint），用于无标签匹配。
- **边车文件（Sidecar）**：与音频同名的 `cover.jpg` / `xxx.lrc`。
- **dry-run**：只预览变更、不真正写盘。

---

_本文档为设计提案，落地时可据实际依赖与排期调整字段与优先级。_
