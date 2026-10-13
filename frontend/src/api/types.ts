/** 与后端 Pydantic schema 对应的前端类型（对应设计文档 §7/§8）。 */

export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  pages: number
}

export interface Library {
  id: number
  name: string
  root_path: string
  enabled: boolean
  scan_mode: string
  created_at: string
  track_count: number
}

export interface Track {
  id: number
  library_id: number
  path: string
  dirname: string
  filename: string
  ext: string
  format: string
  size: number
  mtime: string
  duration: number | null
  bitrate: number | null
  sample_rate: number | null
  channels: number | null
  bit_depth: number | null
  title: string | null
  artist: string | null
  album: string | null
  album_artist: string | null
  composer: string | null
  genre: string | null
  track_no: number | null
  disc_no: number | null
  year: string | null
  date: string | null
  comment: string | null
  has_cover: boolean
  cover_mtime: string | null
  has_lyrics: boolean
  has_embedded_lyrics: boolean
  has_lyrics_file: boolean
  has_word_lyrics: boolean
  tag_status: string
  created_at: string
  updated_at: string
}

export interface TrackFacets {
  formats: Record<string, number>
  years: Record<string, number>
  artists: Record<string, number>
  tag_status: Record<string, number>
  has_cover: Record<string, number>
  has_lyrics: Record<string, number>
  has_word_lyrics: Record<string, number>
}

/** 当前筛选命中的全部曲目 id（用于「选择全部」跨页批量操作）。 */
export interface TrackIds {
  ids: number[]
  total: number
}

export interface Provider {
  key: string
  name: string
  capabilities: string[]
  enabled: boolean
  priority: number
  options: Record<string, unknown>
}

export interface Task {
  id: number
  type: string
  status: string
  total: number
  processed: number
  message: string | null
  /** 当前正在处理的条目（仅实时事件携带，REST 列表不含） */
  current?: string | null
  error: string | null
  started_at: string | null
  finished_at: string | null
  created_at: string
}

export interface OperationLog {
  id: number
  track_id: number | null
  action: string
  field: string | null
  old_value: string | null
  new_value: string | null
  source: string
  result: string
  created_at: string
}

export interface Health {
  status: string
  name: string
  version: string
  environment: string
  ffmpeg: boolean
}

export interface TaskAccepted {
  task_id: number
  status: string
}

export interface FieldDiff {
  field: string
  old_value: unknown
  new_value: unknown
}

export interface TrackDiff {
  track_id: number
  path: string
  changes: FieldDiff[]
}

export interface BatchPreviewResponse {
  total: number
  changed: number
  items: TrackDiff[]
}

export interface BatchEditOp {
  field: string
  op: 'set' | 'fill_empty' | 'append' | 'replace' | 'zh_convert'
  value?: unknown
  find?: string | null
  replace?: string | null
  use_regex?: boolean
  direction?: 's2t' | 't2s' | null
}

export interface BatchEditRequest {
  ids: number[]
  ops: BatchEditOp[]
  strategy: 'overwrite' | 'fill_empty' | 'append' | 'replace'
  dry_run?: boolean
}

/** 整理（F15 / F11 的「标签→文件名」分支） */
export type OrganizeStatus = 'ok' | 'unchanged' | 'conflict' | 'invalid'

export interface OrganizePreviewItem {
  track_id: number
  source: string
  target: string | null
  status: OrganizeStatus
  reason: string | null
  sidecars: string[]
}

export interface OrganizePreviewResponse {
  total: number
  ok: number
  conflicts: number
  unchanged: number
  invalid: number
  items: OrganizePreviewItem[]
}

export interface OrganizeRequest {
  ids: number[]
  template: string
  /** false=同级重命名（F11）；true=移动到分组目录（F15） */
  move: boolean
}

export interface OrganizePlanItem {
  track_id: number
  target: string
}

export interface OrganizeApplyRequest extends OrganizeRequest {
  /** 用户确认的 old→new 计划；后端以它为准执行 */
  plan?: OrganizePlanItem[]
}

export interface CoverMeta {
  track_id: number
  available: boolean
  source: 'embedded' | 'file' | 'scraped' | null
  mime: string | null
}

/** 封面批量替换（F20） */
export interface CoverBatchMatch {
  index: number
  filename: string
  status: 'ok' | 'ambiguous' | 'unmatched'
  match: 'stem' | 'album' | 'album_name' | null
  track_ids: number[]
  album: string | null
}

export interface CoverAlbumGroup {
  label: string
  track_ids: number[]
}

export interface CoverBatchPreviewResponse {
  matches: CoverBatchMatch[]
  albums: CoverAlbumGroup[]
  all_track_ids: number[]
}

export interface CoverAssignment {
  index: number
  track_ids: number[]
}

export interface LyricsRead {
  track_id: number
  available: boolean
  format: 'lrc' | 'embedded'
  source: string | null
  content: string | null
}

export interface LyricsTranslateResponse {
  track_id: number
  target: string
  content: string
}

/** 逐字歌词（只读预览，不落盘） */
export interface WordLyricWord {
  text: string
  offset: number
  duration: number
}

export interface WordLyricLine {
  start: number
  duration: number
  text: string
  words: WordLyricWord[]
}

export interface WordLyricsResponse {
  track_id: number
  available: boolean
  source: string | null
  lines: WordLyricLine[]
}

export interface Candidate {
  provider: string
  external_id: string
  title: string | null
  artist: string | null
  album: string | null
  year: string | null
  track_no: number | null
  score: number
  cover_url: string | null
  payload: Record<string, unknown>
}

export interface ScrapeSearchResponse {
  track_id: number | null
  candidates: Candidate[]
}

export interface ScrapeApplyResponse {
  track_id: number
  applied_fields: string[]
  cover_applied: boolean
  lyrics_applied: boolean
  /** 是否取到歌词（逐行，原文/译文合并后） */
  lyrics_found: boolean
  /** 是否取到逐字歌词 */
  word_found: boolean
  /** 是否写入了 .lrc / .nilyric 同名歌词文件 */
  lyrics_files_written: boolean
  diffs: FieldDiff[]
}

/** 文件名解析（F11 的文件名 → 标签方向） */
export interface ParsedFields {
  title: string | null
  artist: string | null
  album: string | null
  track_no: number | null
}

export interface ParseFilenameResponse {
  track_id: number
  source: 'heuristic' | 'ai'
  confidence: number
  note: string | null
  fields: ParsedFields
  diffs: FieldDiff[]
  applied: boolean
}

/** 批量文件名解析（F11 的文件名→标签方向） */
export interface ParseFilenameBatchRequest {
  ids: number[]
  use_ai: boolean
  strategy: 'fill_empty' | 'overwrite'
}

export interface ParseFilenameBatchItem {
  track_id: number
  path: string
  source: 'heuristic' | 'ai'
  confidence: number
  note: string | null
  fields: ParsedFields
  diffs: FieldDiff[]
  status: 'ok' | 'unchanged' | 'invalid'
}

export interface ParseFilenameBatchResponse {
  total: number
  changed: number
  unchanged: number
  invalid: number
  items: ParseFilenameBatchItem[]
}

export interface Capabilities {
  ffmpeg: boolean
  fpcalc: boolean
  ai: boolean
  acoustid: boolean
}

/** AI 辅助配置（密钥始终脱敏） */
export interface AISettings {
  enabled: boolean
  base_url: string
  model: string
  has_api_key: boolean
  api_key_masked: string | null
  available: boolean
}

export interface AISettingsUpdate {
  enabled?: boolean
  base_url?: string
  model?: string
  api_key?: string
}

/** AcoustID 指纹识别配置（密钥始终脱敏） */
export interface AcoustIDSettings {
  has_api_key: boolean
  api_key_masked: string | null
  available: boolean
}

export interface AcoustIDSettingsUpdate {
  api_key?: string
}

/** 可编辑字段（与后端 EDITABLE_FIELDS 对齐） */
export type EditableField =
  | 'title'
  | 'artist'
  | 'album'
  | 'album_artist'
  | 'composer'
  | 'genre'
  | 'track_no'
  | 'disc_no'
  | 'year'
  | 'date'
  | 'comment'

