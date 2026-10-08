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
