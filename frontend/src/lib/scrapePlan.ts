/** 刮削预演：算出应用候选后究竟会写入哪些字段。
 *
 * 后端在 apply 时按「仅补空值 / 字段白名单」决定是否覆盖，这里用同样的规则做**事前**预演，
 * 让用户在点「应用」之前就能看到 old → new 的完整清单，并逐字段勾选。
 *
 * 取值对候选做 payload 回退：部分字段（如音轨号）只在 payload 里出现。
 */

export type PlanField = {
  key: string
  label: string
  from: string
  to: string
  /** 因「仅补空值」而会被跳过的字段 */
  blocked: boolean
}

/** 逐字段勾选所需的完整行（含未变化字段）。 */
export type PlanRow = PlanField & { changed: boolean }

/** 刮削可写入的标签字段（与后端 bundle 可提供的字段对齐）。 */
export const PLAN_FIELDS: { key: string; label: string }[] = [
  { key: 'title', label: '标题' },
  { key: 'artist', label: '艺术家' },
  { key: 'album', label: '专辑' },
  { key: 'year', label: '年份' },
  { key: 'track_no', label: '音轨号' },
]

export type FieldBag = Record<string, unknown> | null | undefined

function text(value: unknown): string {
  return value === null || value === undefined || value === '' ? '∅' : String(value)
}

/** 读取字段值：优先顶层属性，缺失时回退候选 payload。 */
function pick(bag: FieldBag, key: string): unknown {
  if (!bag) return null
  const direct = bag[key]
  if (direct !== undefined && direct !== null && direct !== '') return direct
  const payload = bag.payload as Record<string, unknown> | undefined
  return payload?.[key] ?? direct ?? null
}

/** 逐字段行：含未变化项，供工作台并排对比与勾选。 */
export function fieldRows(
  current: FieldBag,
  candidate: FieldBag,
  onlyMissing: boolean,
  fields = PLAN_FIELDS,
): PlanRow[] {
  if (!candidate) return []
  return fields.map((field) => {
    const from = text(pick(current, field.key))
    const to = text(pick(candidate, field.key))
    const changed = from !== to
    return {
      key: field.key,
      label: field.label,
      from,
      to,
      changed,
      blocked: !changed || (onlyMissing && from !== '∅'),
    }
  })
}

/** 与当前值不同、且（在仅补空值模式下）真正会被写入的字段。 */
export function planChanges(
  current: FieldBag,
  candidate: FieldBag,
  onlyMissing: boolean,
  fields = PLAN_FIELDS,
): PlanField[] {
  return fieldRows(current, candidate, onlyMissing, fields)
    .filter((row) => row.changed)
    .map(({ key, label, from, to, blocked }) => ({ key, label, from, to, blocked }))
}

/** 候选与当前所有不同的字段（忽略策略，用于候选卡上的差异标记）。 */
export function changedFields(current: FieldBag, candidate: FieldBag, fields = PLAN_FIELDS): PlanField[] {
  if (!candidate) return []
  return fields
    .filter((field) => text(pick(current, field.key)) !== text(pick(candidate, field.key)))
    .map((field) => ({
      key: field.key,
      label: field.label,
      from: text(pick(current, field.key)),
      to: text(pick(candidate, field.key)),
      blocked: false,
    }))
}
