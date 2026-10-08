import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError, apiGet, apiSend } from '@/api/client'

function fakeResponse(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 204 ? 'No Content' : 'OK',
    headers: { get: (key: string) => headers[key] ?? null },
    json: async () => body,
  } as unknown as Response
}

describe('REST 客户端', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('拼接 /api 前缀与查询参数，跳过空值', async () => {
    const fetchMock = vi.fn().mockResolvedValue(fakeResponse({ items: [] }))
    vi.stubGlobal('fetch', fetchMock)

    await apiGet('/tracks', { page: 2, q: 'jazz', has_cover: true, skip: null, missing: undefined })

    const url = fetchMock.mock.calls[0]?.[0] as string
    expect(url).toContain('/api/tracks?')
    expect(url).toContain('page=2')
    expect(url).toContain('q=jazz')
    expect(url).toContain('has_cover=true')
    expect(url).not.toContain('skip')
    expect(url).not.toContain('missing')
  })

  it('POST 时序列化 JSON 请求体', async () => {
    const fetchMock = vi.fn().mockResolvedValue(fakeResponse({ id: 1 }, 201))
    vi.stubGlobal('fetch', fetchMock)

    await apiSend('POST', '/libraries', { name: '库', root_path: '/music' })

    const init = fetchMock.mock.calls[0]?.[1] as RequestInit
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({ name: '库', root_path: '/music' })
  })

  it('错误响应抛出 ApiError 并携带里程碑头', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(fakeResponse({ detail: '该接口将在 M1 实现' }, 501, { 'X-Milestone': 'M1' })),
    )

    const error = await apiGet('/scrape/search').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).status).toBe(501)
    expect((error as ApiError).milestone).toBe('M1')
    expect((error as ApiError).message).toBe('该接口将在 M1 实现')
  })

  it('204 响应返回 undefined', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(fakeResponse(null, 204)))
    await expect(apiSend('DELETE', '/libraries/1')).resolves.toBeUndefined()
  })
})
