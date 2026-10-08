import { describe, expect, it } from 'vitest'

import { changedFields, planChanges } from './scrapePlan'

const current = { title: '16号爱人', artist: '容祖儿', album: null, year: null }
const candidate = { title: '16号爱人', artist: '容祖儿', album: 'Bi-Heart', year: '2005' }

describe('planChanges', () => {
  it('只列出真正会变化的字段（相同字段不出现）', () => {
    const plan = planChanges(current, candidate, false)
    expect(plan.map((item) => item.key)).toEqual(['album', 'year'])
    expect(plan[0]).toMatchObject({ from: '∅', to: 'Bi-Heart', blocked: false })
  })

  it('仅补空值时，已有值会被标记为跳过', () => {
    const existing = { ...current, album: '旧专辑' }
    const plan = planChanges(existing, candidate, true)
    expect(plan.find((item) => item.key === 'album')?.blocked).toBe(true)
    expect(plan.find((item) => item.key === 'year')?.blocked).toBe(false)
  })

  it('未选候选时返回空清单', () => {
    expect(planChanges(current, null, false)).toEqual([])
  })
})

describe('changedFields', () => {
  it('返回候选卡上用于提示差异的字段', () => {
    expect(changedFields(current, candidate).map((item) => item.label)).toEqual(['专辑', '年份'])
  })

  it('完全一致时为空', () => {
    expect(changedFields(candidate, candidate)).toEqual([])
  })
})
