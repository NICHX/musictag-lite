/** 轻量 REST 客户端：统一 /api 前缀、查询参数与错误处理。 */

const BASE = '/api'

export class ApiError extends Error {
  status: number
  milestone?: string

  constructor(message: string, status: number, milestone?: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.milestone = milestone
  }
}

type QueryValue = string | number | boolean | null | undefined

function buildUrl(path: string, params?: Record<string, QueryValue>): string {
  const url = new URL(`${BASE}${path}`, window.location.origin)
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value === null || value === undefined) continue
      url.searchParams.set(key, String(value))
    }
  }
  return url.pathname + url.search
}

async function parseError(response: Response): Promise<ApiError> {
  let detail = response.statusText
  try {
    const body = (await response.json()) as { detail?: string }
    if (body?.detail) detail = body.detail
  } catch {
    /* 非 JSON 错误体，忽略 */
  }
  return new ApiError(detail, response.status, response.headers.get('X-Milestone') ?? undefined)
}

export async function apiGet<T>(
  path: string,
  params?: Record<string, QueryValue>,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(buildUrl(path, params), {
    headers: { Accept: 'application/json' },
    ...init,
  })
  if (!response.ok) throw await parseError(response)
  return (await response.json()) as T
}

export async function apiSend<T>(
  method: 'POST' | 'PATCH' | 'PUT' | 'DELETE',
  path: string,
  body?: unknown,
): Promise<T> {
  const response = await fetch(buildUrl(path), {
    method,
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!response.ok) throw await parseError(response)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const api = {
  get: apiGet,
  post: <T>(path: string, body?: unknown) => apiSend<T>('POST', path, body),
  patch: <T>(path: string, body?: unknown) => apiSend<T>('PATCH', path, body),
  put: <T>(path: string, body?: unknown) => apiSend<T>('PUT', path, body),
  delete: <T>(path: string) => apiSend<T>('DELETE', path),
}

/** 与后端 /ws/events 建立连接。 */
export function openEventSocket(onEvent: (event: Record<string, unknown>) => void): WebSocket {
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const socket = new WebSocket(`${protocol}://${window.location.host}/ws/events`)
  socket.addEventListener('message', (message) => {
    try {
      onEvent(JSON.parse(message.data as string) as Record<string, unknown>)
    } catch {
      /* 忽略非法消息 */
    }
  })
  return socket
}
