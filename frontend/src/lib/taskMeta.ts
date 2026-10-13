/** 任务的展示元数据：类型/状态中文名、配色与耗时格式化。 */

export const TASK_TYPE_LABELS: Record<string, string> = {
  scan: '扫描曲库',
  scrape: '批量刮削匹配',
  word_lyrics: '批量逐字歌词',
  batch: '批量编辑',
  batch_edit: '批量编辑',
  organize: '整理文件',
  convert: '格式转换',
  cover_batch: '批量封面',
  filename_batch: '文件名解析',
}

export const TASK_STATUS_LABELS: Record<string, string> = {
  queued: '排队中',
  running: '进行中',
  succeeded: '已完成',
  failed: '失败',
  cancelled: '已取消',
}

export function taskTypeLabel(type: string): string {
  return TASK_TYPE_LABELS[type] ?? type
}

export function taskStatusLabel(status: string): string {
  return TASK_STATUS_LABELS[status] ?? status
}

export function taskStatusTone(status: string): string {
  if (status === 'running') return 'border-brand/40 text-brand'
  if (status === 'succeeded') return 'border-success/40 text-success'
  if (status === 'failed') return 'border-danger/40 text-danger'
  return 'border-border text-muted'
}

export function isActiveTask(status: string): boolean {
  return status === 'running' || status === 'queued'
}

export function taskPercent(processed: number, total: number): number {
  if (!total) return 0
  return Math.min(100, Math.round((processed / total) * 100))
}

/** 耗时：优先 started/finished，运行中按 ``nowMs`` 计算。返回如 "12s" / "1m23s"。 */
export function formatElapsed(
  task: { started_at: string | null; finished_at: string | null; created_at: string; status: string },
  nowMs: number = Date.now(),
): string {
  const start = task.started_at ?? task.created_at
  if (!start) return '—'
  const endMs = task.finished_at ? new Date(task.finished_at).getTime() : nowMs
  const seconds = Math.max(0, Math.round((endMs - new Date(start).getTime()) / 1000))
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  return `${minutes}m${String(seconds % 60).padStart(2, '0')}s`
}
