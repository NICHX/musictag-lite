import { defineStore } from 'pinia'
import { ref } from 'vue'

import { api, openEventSocket } from '@/api/client'
import type { Task } from '@/api/types'

interface TaskProgressEvent {
  type?: string
  task_id?: number
  status?: string
  processed?: number
  total?: number
  current?: string | null
}

export const useTaskStore = defineStore('tasks', () => {
  const tasks = ref<Task[]>([])
  const connected = ref(false)
  const lastEvent = ref<Record<string, unknown> | null>(null)
  let socket: WebSocket | null = null

  async function refresh(): Promise<void> {
    tasks.value = await api.get<Task[]>('/tasks', { limit: 50 })
  }

  function connect(): void {
    if (socket) return
    socket = openEventSocket((event) => {
      lastEvent.value = event
      if (event.type === 'hello') {
        connected.value = true
        return
      }
      const progress = event as TaskProgressEvent
      if ((progress.type === 'task.progress' || progress.type === 'task.started') && progress.task_id) {
        applyEvent(progress)
      }
    })
    socket.addEventListener('close', () => {
      connected.value = false
      socket = null
    })
  }

  function applyEvent(event: TaskProgressEvent): void {
    const existing = tasks.value.find((task) => task.id === event.task_id)
    if (existing) {
      if (event.status) existing.status = event.status
      if (typeof event.processed === 'number') existing.processed = event.processed
      if (typeof event.total === 'number') existing.total = event.total
    } else {
      // 新任务：拉取一次完整列表以补齐字段
      void refresh()
    }
  }

  function disconnect(): void {
    socket?.close()
    socket = null
    connected.value = false
  }

  return { tasks, connected, lastEvent, refresh, connect, disconnect }
})
