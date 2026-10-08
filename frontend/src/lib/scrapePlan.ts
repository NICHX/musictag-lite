/** 刮削预演：算出应用候选后究竟会写入哪些字段。
 *
 * 后端在 apply 时会按「仅补空值」策略决定是否覆盖，这里用同样的规则做**事前**预演，
 * 让用户在点「应用」之前就能看到 old → new 的完整清单。
 */

export type PlanField = {
  key: string
  label: string
  from: string
  to: string
  /** 因「仅补空值」而会被跳过的字段 */
  blocked: boolean
}

export const PLAN_FIELDS: { key: string; label: string }[] = [
  { key: 'title', label: '标题' },
  { key: 'artist', label: '艺术家' },
  { key: 'album', label: '专辑' },
  { key: 'year', label: '年份' },
]

export type FieldBag = Record<string, unknown> | null | undefined

function text(value: unknown): string {
  return value === null || value === undefined || value === '' ? '∅' : String(value)
}

/** 与当前值不同、且（在仅补空值模式下）真正会被写入的字段。 */
export function planChanges(
  current: FieldBag,
  candidate: FieldBag,
  onlyMissing: boolean,
  fields = PLAN_FIELDS,
): PlanField[] {
  if (!candidate) return []
  const plan: PlanField[] = []
  for (const field of fields) {
    const from = text(current?.[field.key])
    const to = text(candidate[field.key])
    if (from === to) continue
    plan.push({ key: field.key, label: field.label, from, to, blocked: onlyMissing && from !== '∅' })
  }
  return plan
}

/** 候选与当前所有不同的字段（忽略策略，用于候选卡上的差异标记）。 */
export function changedFields(current: FieldBag, candidate: FieldBag, fields = PLAN_FIELDS): PlanField[] {
  if (!candidate) return []
  return fields
    .filter((field) => text(current?.[field.key]) !== text(candidate[field.key]))
    .map((field) => ({
      key: field.key,
      label: field.label,
      from: text(current?.[field.key]),
      to: text(candidate[field.key]),
      blocked: false,
    }))
}
