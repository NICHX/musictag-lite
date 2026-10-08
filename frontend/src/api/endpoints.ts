/** 按领域组织的 API 调用（对应设计文档 §8）。 */

import { api } from './client'
import type {
  AISettings,
  AISettingsUpdate,
  BatchEditRequest,
  BatchPreviewResponse,
  Candidate,
  Capabilities,
  CoverMeta,
  Library,
  LyricsRead,
  OperationLog,
  Page,
  ParseFilenameResponse,
  Provider,
  ScrapeApplyResponse,
  ScrapeSearchResponse,
  Task,
  TaskAccepted,
  Track,
  TrackFacets,
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
}

export const libraryApi = {
  list: () => api.get<Library[]>('/libraries'),
  create: (body: { name: string; root_path: string }) => api.post<Library>('/libraries', body),
  remove: (id: number) => api.delete<void>(`/libraries/${id}`),
  scan: (id: number) => api.post<TaskAccepted>(`/libraries/${id}/scan`),
}

export const trackApi = {
  list: (query: TrackQuery = {}) => api.get<Page<Track>>('/tracks', query),
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
}

export const lyricsApi = {
  get: (trackId: number) => api.get<LyricsRead>(`/tracks/${trackId}/lyrics`),
  put: (trackId: number, content: string, target: 'embedded' | 'lrc' | 'both' = 'embedded') =>
    api.put<LyricsRead>(`/tracks/${trackId}/lyrics`, {
      content,
      format: 'lrc',
      target,
      validate_lrc: false,
    }),
}

export const scrapeApi = {
  search: (body: { track_id?: number; providers?: string[]; limit?: number }) =>
    api.post<ScrapeSearchResponse>('/scrape/search', body),
  apply: (body: {
    track_id: number
    candidate_ids: string[]
    /** 选中的候选本身：后端以此为准，避免按 id 重新 fetch 造成 release 漂移 */
    candidates?: Candidate[]
    only_missing?: boolean
    apply_cover?: boolean
    apply_lyrics?: boolean
  }) => api.post<ScrapeApplyResponse>('/scrape/apply', body),
  list: (candidate: Candidate) => `${candidate.provider}:${candidate.external_id}`,
}

export const logsApi = {
  list: (query: { page?: number; page_size?: number; track_id?: number; source?: string } = {}) =>
    api.get<Page<OperationLog>>('/logs', query),
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

export const systemApi = {
  capabilities: () => api.get<Capabilities>('/capabilities'),
}

/** AI 辅助配置（密钥脱敏；更新时省略 api_key 表示不修改） */
export const aiApi = {
  get: () => api.get<AISettings>('/settings/ai'),
  update: (body: AISettingsUpdate) => api.patch<AISettings>('/settings/ai', body),
}
