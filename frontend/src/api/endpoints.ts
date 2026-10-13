/** 按领域组织的 API 调用（对应设计文档 §8）。 */

import { api } from './client'
import type {
  AISettings,
  AISettingsUpdate,
  AcoustIDSettings,
  AcoustIDSettingsUpdate,
  ApiToken,
  ApiTokenUpdate,
  BatchEditRequest,
  BatchPreviewResponse,
  Candidate,
  Capabilities,
  CoverAssignment,
  CoverBatchPreviewResponse,
  CoverMeta,
  Extension,
  ExtensionsResponse,
  Library,
  LyricsRead,
  OperationLog,
  OrganizeApplyRequest,
  OrganizePreviewResponse,
  OrganizeRequest,
  Page,
  ParseFilenameBatchRequest,
  ParseFilenameBatchResponse,
  ParseFilenameResponse,
  Provider,
  ScrapeApplyResponse,
  ScrapeSearchResponse,
  Task,
  TaskAccepted,
  Track,
  TrackFacets,
  TrackIds,
  WordLyricsResponse,
  WordLyricsTarget,
  WordLyricsTranslation,
} from './types'

export type TrackQuery = {
  page?: number
  page_size?: number
  sort?: string
  order?: 'asc' | 'desc'
  q?: string
  library_id?: number
  format?: string
  tag_status?: string
  has_cover?: boolean
  has_lyrics?: boolean
  has_word_lyrics?: boolean
}

export const libraryApi = {
  list: () => api.get<Library[]>('/libraries'),
  create: (body: { name: string; root_path: string }) => api.post<Library>('/libraries', body),
  remove: (id: number) => api.delete<void>(`/libraries/${id}`),
  scan: (id: number) => api.post<TaskAccepted>(`/libraries/${id}/scan`),
}

export const trackApi = {
  list: (query: TrackQuery = {}) => api.get<Page<Track>>('/tracks', query),
  /** 当前筛选命中的全部 id（不分页），用于「选择全部」批量操作。 */
  ids: (query: TrackQuery = {}) => api.get<TrackIds>('/tracks/ids', query),
  get: (id: number) => api.get<Track>(`/tracks/${id}`),
  update: (id: number, values: Record<string, unknown>) => api.patch<Track>(`/tracks/${id}`, values),
  facets: () => api.get<TrackFacets>('/tracks/facets'),
  batchPreview: (body: BatchEditRequest) => api.post<BatchPreviewResponse>('/tracks/batch/preview', body),
  batchApply: (body: BatchEditRequest) => api.post<TaskAccepted>('/tracks/batch', body),
}

export const coverApi = {
  /** 直接可用的封面图片地址（无封面时返回 404）。 */
  url: (trackId: number) => `/api/tracks/${trackId}/cover`,
  upload: async (trackId: number, file: File, kind = 'front'): Promise<CoverMeta> => {
    const form = new FormData()
    form.append('file', file)
    const response = await fetch(`/api/tracks/${trackId}/cover?kind=${kind}`, {
      method: 'PUT',
      body: form,
    })
    if (!response.ok) {
      let detail = response.statusText
      try {
        detail = ((await response.json()) as { detail?: string }).detail ?? detail
      } catch {
        /* 忽略非 JSON */
      }
      throw new Error(detail)
    }
    return (await response.json()) as CoverMeta
  },
  remove: (trackId: number) => api.delete<{ removed: boolean }>(`/tracks/${trackId}/cover`),
  /** F20：仅凭文件名在所选曲目内匹配（dry-run，不写盘） */
  batchPreview: (body: { ids: number[]; filenames: string[] }) =>
    api.post<CoverBatchPreviewResponse>('/covers/batch-preview', body),
  /** F20：按确认的指派批量写入内嵌封面（multipart） */
  batchReplace: async (files: File[], assignments: CoverAssignment[]): Promise<TaskAccepted> => {
    const form = new FormData()
    for (const file of files) form.append('files', file)
    form.append('assignments', JSON.stringify(assignments))
    const response = await fetch('/api/covers/batch-replace', { method: 'POST', body: form })
    if (!response.ok) {
      let detail = response.statusText
      try {
        detail = ((await response.json()) as { detail?: string }).detail ?? detail
      } catch {
        /* 忽略非 JSON */
      }
      throw new Error(detail)
    }
    return (await response.json()) as TaskAccepted
  },
}

export const lyricsApi = {
  /** 读取歌词：内嵌优先，其次同名 .lrc / .nilyric */
  get: (trackId: number) => api.get<LyricsRead>(`/tracks/${trackId}/lyrics`),
  put: (trackId: number, content: string, target: 'embedded' | 'lrc' | 'both' = 'embedded') =>
    api.put<LyricsRead>(`/tracks/${trackId}/lyrics`, {
      content,
      format: 'lrc',
      target,
      validate_lrc: false,
    }),
  /**
   * 抓取逐字歌词并写入所选目标（内嵌 / 同名 .nilyric / 同名 .lrc）。
   * translation：none=不写译文；source=仅数据源自带（默认，免费）；ai=显式调用 AI 生成（可能产生费用）。
   */
  saveWordLyrics: (
    trackId: number,
    targets: WordLyricsTarget[] = ['embedded', 'nilyric'],
    translation: WordLyricsTranslation = 'source',
    translateTarget: 'zh' | 'en' | 'ja' = 'zh',
  ) =>
    api.post<LyricsRead>(`/tracks/${trackId}/lyrics/word`, {
      targets,
      translation,
      translate_target: translateTarget,
    }),
}

export const scrapeApi = {
  search: (body: {
    track_id?: number
    /** 自定义搜索条件（不传 track_id 时生效）：用于手动检索/已下架歌曲 */
    query?: {
      title?: string
      artist?: string
      album?: string
      track_no?: number
      duration?: number
      filename_hint?: string
    }
    providers?: string[]
    limit?: number
  }) => api.post<ScrapeSearchResponse>('/scrape/search', body),
  apply: (body: {
    track_id: number
    candidate_ids: string[]
    /** 选中的候选本身：后端以此为准，避免按 id 重新 fetch 造成 release 漂移 */
    candidates?: Candidate[]
    only_missing?: boolean
    /** 标签字段白名单（逐字段勾选）；省略=写入候选提供的全部字段 */
    fields?: string[]
    apply_cover?: boolean
    apply_lyrics?: boolean
    /** 同时抓取逐字歌词并写入内嵌 + .lrc/.nilyric 边车文件 */
    write_word_lyrics?: boolean
  }) => api.post<ScrapeApplyResponse>('/scrape/apply', body),
  list: (candidate: Candidate) => `${candidate.provider}:${candidate.external_id}`,
  /** F14：指纹识别（fpcalc → AcoustID → 回填 MusicBrainz），需已配置 Key */
  fingerprint: (trackId: number) =>
    api.post<ScrapeSearchResponse>('/scrape/fingerprint', { track_id: trackId }),
  /** 批量刮削：对每首取最高分候选，达阈值自动应用（仅补空值 + 封面 + 歌词/逐字歌词） */
  jobs: (body: {
    ids: number[]
    providers?: string[]
    only_missing?: boolean
    apply_lyrics?: boolean
    write_word_lyrics?: boolean
  }) => api.post<TaskAccepted>('/scrape/jobs', body),
  /** 逐字歌词（只读预览，不落盘）；优先读本地 .nilyric */
  wordLyrics: (trackId: number) =>
    api.get<WordLyricsResponse>(`/scrape/word-lyrics/${trackId}`),
  /** 批量抓取逐字歌词并写入（内嵌 / 同名边车，默认 内嵌 + .nilyric） */
  wordLyricsBatch: (ids: number[], targets: WordLyricsTarget[] = ['embedded', 'nilyric']) =>
    api.post<TaskAccepted>('/scrape/word-lyrics', { ids, targets }),
}

export const logsApi = {
  list: (
    query: {
      page?: number
      page_size?: number
      track_id?: number
      source?: string
      result?: string
      q?: string
    } = {},
  ) => api.get<Page<OperationLog>>('/logs', query),
}

export const taskApi = {
  list: (limit = 50) => api.get<Task[]>('/tasks', { limit }),
  get: (id: number) => api.get<Task>(`/tasks/${id}`),
  cancel: (id: number) => api.post<Task>(`/tasks/${id}/cancel`),
}

export const providerApi = {
  list: () => api.get<Provider[]>('/providers'),
  update: (key: string, body: { enabled?: boolean; priority?: number }) =>
    api.patch<Provider>(`/providers/${key}`, body),
}

/** 文件名解析（F11）：use_ai 需后端已配置 AI；apply=false 时仅预览 */
export const filenameApi = {
  parse: (trackId: number, useAi = false, apply = false) =>
    api.post<ParseFilenameResponse>(`/tracks/${trackId}/parse-filename`, {
      use_ai: useAi,
      apply,
    }),
}

/** 整理（F15 / F11 的「标签→文件名」分支）：先预演，确认后按 plan 执行。 */
export const organizeApi = {
  preview: (body: OrganizeRequest) =>
    api.post<OrganizePreviewResponse>('/organize/preview', body),
  apply: (body: OrganizeApplyRequest) => api.post<TaskAccepted>('/organize/apply', body),
}

/** 批量文件名解析（F11 的「文件名→标签」方向） */
export const filenameBatchApi = {
  preview: (body: ParseFilenameBatchRequest) =>
    api.post<ParseFilenameBatchResponse>('/tracks/parse-filename/preview', body),
  apply: (body: ParseFilenameBatchRequest) =>
    api.post<TaskAccepted>('/tracks/parse-filename', body),
}

export const systemApi = {
  capabilities: () => api.get<Capabilities>('/capabilities'),
}

/** AI 辅助配置（密钥脱敏；更新时省略 api_key 表示不修改） */
export const aiApi = {
  get: () => api.get<AISettings>('/settings/ai'),
  update: (body: AISettingsUpdate) => api.patch<AISettings>('/settings/ai', body),
}

/** AcoustID 指纹识别配置（密钥脱敏；更新时省略 api_key 表示不修改） */
export const acoustidApi = {
  get: () => api.get<AcoustIDSettings>('/settings/acoustid'),
  update: (body: AcoustIDSettingsUpdate) =>
    api.patch<AcoustIDSettings>('/settings/acoustid', body),
}

/** 扩展（可安装的刮削源插件）：社区源不再内置，需先安装 */
export const extensionApi = {
  list: () => api.get<ExtensionsResponse>('/extensions'),
  installFromCatalog: (key: string) => api.post<Extension>(`/extensions/catalog/${key}/install`),
  uninstall: (key: string) =>
    api.delete<{ key: string; removed_providers: string[] }>(`/extensions/${key}`),
  /** 上传扩展 zip 安装（zip 内为单一顶层目录，含 extension.json） */
  installZip: async (file: File): Promise<Extension> => {
    const form = new FormData()
    form.append('file', file)
    const response = await fetch('/api/extensions/install', { method: 'POST', body: form })
    if (!response.ok) {
      let detail = response.statusText
      try {
        detail = ((await response.json()) as { detail?: string }).detail ?? detail
      } catch {
        /* 忽略非 JSON */
      }
      throw new Error(detail)
    }
    return (await response.json()) as Extension
  },
}

/** 对外 API 令牌（供外部系统集成的 /api/open/* 接口鉴权） */
export const apiTokenApi = {
  get: () => api.get<ApiToken>('/settings/api-token'),
  update: (body: ApiTokenUpdate) => api.patch<ApiToken>('/settings/api-token', body),
}
