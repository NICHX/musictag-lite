/** 整理（F15 / F11）：模板字段、状态展示与执行计划构造。 */

import type { OrganizePlanItem, OrganizePreviewItem, OrganizeStatus } from '@/api/types'

/** 模板可用字段（与后端 TEMPLATE_FIELDS 对齐）。 */
export const ORGANIZE_FIELDS: { key: string; label: string }[] = [
  { key: 'albumartist', label: '专辑艺术家' },
  { key: 'artist', label: '艺术家' },
  { key: 'album', label: '专辑' },
  { key: 'year', label: '年份' },
  { key: 'track', label: '音轨号' },
  { key: 'disc', label: '碟号' },
  { key: 'title', label: '标题' },
  { key: 'genre', label: '流派' },
  { key: 'composer', label: '作曲' },
]

export const DEFAULT_ORGANIZE_TEMPLATE = '{albumartist}/{year} - {album}/{track:02d} - {title}'

export const ORGANIZE_STATUS: Record<OrganizeStatus, { label: string; className: string }> = {
  ok: { label: '可执行', className: 'border-success/40 text-success' },
  conflict: { label: '冲突', className: 'border-danger/40 text-danger' },
  unchanged: { label: '未变化', className: 'border-border text-muted' },
  invalid: { label: '无效', className: 'border-warning/40 text-warning' },
}

/** 只提交「可执行」且目标非空的条目，作为用户确认的落盘计划。 */
export function buildApplyPlan(items: OrganizePreviewItem[]): OrganizePlanItem[] {
  return items
    .filter((item) => item.status === 'ok' && item.target)
    .map((item) => ({ track_id: item.track_id, target: item.target as string }))
}

/** 在模板光标位置插入占位符（无光标信息时追加到末尾）。 */
export function insertField(template: string, field: string): string {
  return `${template}{${field}}`
}
