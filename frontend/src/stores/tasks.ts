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
  message?: string | null
}

export const useTaskStore = defineStore('tasks', () => {
  const tasks = ref<Task[]>([])
  const connected = ref(false)
  const lastEvent = ref<Record<string, unknown> | null>(null)
  /** 最近一次完成的任务事件；`completed` 为其计数（供各视图 watch 后刷新）。 */
  const lastFinished = ref<TaskProgressEvent | null>(null)
  const completed = ref(0)
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
      const evt = event as TaskProgressEvent
      if (evt.type === 'task.finished' && evt.task_id) {
        applyEvent(evt)
        lastFinished.value = evt
        completed.value += 1
        void refresh()
        return
      }
      if ((evt.type === 'task.progress' || evt.type === 'task.started') && evt.task_id) {
        applyEvent(evt)
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
      if (event.current !== undefined) existing.current = event.current
      if (event.message !== undefined) existing.message = event.message
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

  return { tasks, connected, lastEvent, lastFinished, completed, refresh, connect, disconnect }
})
