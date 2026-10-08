import { describe, expect, it } from 'vitest'

import { rgbToHsl, vividAccent } from '@/lib/accent'

describe('封面取色', () => {
  it('rgbToHsl 基础换算', () => {
    expect(rgbToHsl(255, 0, 0)).toEqual({ h: 0, s: 1, l: 0.5 })
    expect(rgbToHsl(0, 0, 0)).toEqual({ h: 0, s: 0, l: 0 })
    expect(rgbToHsl(255, 255, 255)).toEqual({ h: 0, s: 0, l: 1 })
    const green = rgbToHsl(0, 255, 0)
    expect(Math.round(green.h)).toBe(120)
  })

  it('vividAccent 输出合法 hsl 并把低饱和色拉起来', () => {
    expect(vividAccent(120, 120, 120)).toMatch(/^hsl\(\d+ \d+% \d+%\)$/)
    const grey = vividAccent(128, 128, 128)
    expect(grey).toContain('45%')
  })

  it('vividAccent 保持色相', () => {
    // 偏红 → 色相接近 0
    expect(vividAccent(200, 40, 40)).toMatch(/^hsl\((3[0-5]?|[0-9]) /)
  })
})
