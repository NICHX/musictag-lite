import { describe, expect, it } from 'vitest'

import { applyTheme, loadTheme, persistTheme, resetAccent, setAccent } from '@/design/theme'

describe('主题工具', () => {
  it('把主题写入 data-theme 属性', () => {
    const el = document.createElement('div')
    applyTheme('light', el)
    expect(el.dataset.theme).toBe('light')
    applyTheme('dark', el)
    expect(el.dataset.theme).toBe('dark')
  })

  it('注入与恢复封面驱动强调色', () => {
    const el = document.createElement('div')
    setAccent('#0891b2', el)
    expect(el.style.getPropertyValue('--accent-dynamic')).toBe('#0891b2')
    resetAccent(el)
    expect(el.style.getPropertyValue('--accent-dynamic')).toBe('')
  })

  it('主题持久化可读回', () => {
    persistTheme('light')
    expect(loadTheme()).toBe('light')
    persistTheme('dark')
    expect(loadTheme()).toBe('dark')
  })
})
