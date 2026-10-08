import { describe, expect, it } from 'vitest'

import { ORGANIZE_STATUS, buildApplyPlan } from './organize'
import type { OrganizePreviewItem } from '@/api/types'

function item(partial: Partial<OrganizePreviewItem>): OrganizePreviewItem {
  return {
    track_id: 1,
    source: '/music/a.flac',
    target: '/music/A/a.flac',
    status: 'ok',
    reason: null,
    sidecars: [],
    ...partial,
  }
}

describe('buildApplyPlan', () => {
  it('只提交可执行且目标非空的条目', () => {
    const plan = buildApplyPlan([
      item({ track_id: 1, status: 'ok', target: '/music/A/1.flac' }),
      item({ track_id: 2, status: 'conflict', reason: '目标已存在' }),
      item({ track_id: 3, status: 'unchanged' }),
      item({ track_id: 4, status: 'ok', target: null }),
    ])
    expect(plan).toEqual([{ track_id: 1, target: '/music/A/1.flac' }])
  })

  it('没有可执行项时返回空计划', () => {
    expect(buildApplyPlan([item({ status: 'invalid' })])).toEqual([])
  })
})

describe('ORGANIZE_STATUS', () => {
  it('覆盖全部状态且有展示文案', () => {
    expect(Object.keys(ORGANIZE_STATUS).sort()).toEqual(['conflict', 'invalid', 'ok', 'unchanged'])
    for (const value of Object.values(ORGANIZE_STATUS)) {
      expect(value.label).toBeTruthy()
      expect(value.className).toContain('text-')
    }
  })
})
