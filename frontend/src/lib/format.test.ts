import { describe, expect, it } from 'vitest'

import { baseName, formatBitrate, formatDateTime, formatDuration, formatSize } from '@/lib/format'

describe('格式化工具', () => {
  it('formatDuration', () => {
    expect(formatDuration(225)).toBe('3:45')
    expect(formatDuration(9)).toBe('0:09')
    expect(formatDuration(null)).toBe('—')
    expect(formatDuration(0)).toBe('—')
  })

  it('formatBitrate', () => {
    expect(formatBitrate(320000)).toBe('320 kbps')
    expect(formatBitrate(1411200)).toBe('1.4 Mbps')
    expect(formatBitrate(null)).toBe('—')
  })

  it('formatSize', () => {
    expect(formatSize(512)).toBe('512 B')
    expect(formatSize(1536)).toBe('1.5 KB')
    expect(formatSize(5 * 1024 * 1024)).toBe('5.0 MB')
    expect(formatSize(0)).toBe('—')
  })

  it('formatDateTime 处理非法输入', () => {
    expect(formatDateTime('not-a-date')).toBe('—')
    expect(formatDateTime(null)).toBe('—')
  })

  it('baseName 取路径末段', () => {
    expect(baseName('/music/Adele/21/01.flac')).toBe('01.flac')
    expect(baseName('a.flac')).toBe('a.flac')
  })
})
