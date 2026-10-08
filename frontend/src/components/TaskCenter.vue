<script setup lang="ts">
import { computed } from 'vue'

import { useTaskStore } from '@/stores/tasks'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const tasks = useTaskStore()

const statusLabels: Record<string, string> = {
  queued: '排队中',
  running: '进行中',
  succeeded: '已完成',
  failed: '失败',
  cancelled: '已取消',
}

const statusTone: Record<string, string> = {
  queued: 'text-muted',
  running: 'text-accent',
  succeeded: 'text-success',
  failed: 'text-danger',
  cancelled: 'text-muted',
}

function percent(processed: number, total: number): number {
  if (!total) return 0
  return Math.min(100, Math.round((processed / total) * 100))
}

const hasTasks = computed(() => tasks.tasks.length > 0)
</script>

<template>
  <div
    v-if="ui.taskCenterOpen"
    class="fixed inset-0 z-40 bg-black/50"
    aria-hidden="true"
    @click="ui.toggleTaskCenter(false)"
  />

  <aside
    class="fixed inset-y-0 right-0 z-50 flex w-full max-w-sm flex-col border-l border-border bg-surface transition-transform duration-200"
    :class="ui.taskCenterOpen ? 'translate-x-0' : 'translate-x-full'"
    aria-label="任务中心"
  >
    <header class="flex items-center justify-between border-b border-border px-4 py-3">
      <h2 class="text-sm font-medium">任务中心</h2>
      <div class="flex items-center gap-2">
        <span class="text-[11px] text-muted">{{ tasks.connected ? '实时已连接' : '实时未连接' }}</span>
        <button
          type="button"
          class="grid h-8 w-8 place-items-center rounded-control text-muted hover:bg-surface-2 hover:text-text"
          aria-label="关闭"
          @click="ui.toggleTaskCenter(false)"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="h-4 w-4">
            <path d="M6 6l12 12M18 6 6 18" stroke-linecap="round" />
          </svg>
        </button>
      </div>
    </header>

    <div class="flex-1 overflow-y-auto p-3">
      <p v-if="!hasTasks" class="px-2 py-10 text-center text-sm text-muted">
        暂无任务。扫描、批量编辑与刮削的进度会实时显示在这里。
      </p>
      <ul v-else class="flex flex-col gap-2">
        <li v-for="task in tasks.tasks" :key="task.id" class="rounded-card border border-border bg-bg p-3">
          <div class="flex items-center justify-between gap-2">
            <span class="font-mono text-xs text-muted">#{{ task.id }} · {{ task.type }}</span>
            <span class="text-xs" :class="statusTone[task.status] ?? 'text-muted'">
              {{ statusLabels[task.status] ?? task.status }}
            </span>
          </div>
          <div class="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-2">
            <div
              class="h-full rounded-full bg-accent transition-[width] duration-200"
              :style="{ width: `${percent(task.processed, task.total)}%` }"
            />
          </div>
          <div class="mt-1.5 flex justify-between font-mono text-[11px] text-muted">
            <span>{{ task.processed }} / {{ task.total || '—' }}</span>
            <span v-if="task.message" class="truncate pl-2">{{ task.message }}</span>
          </div>
        </li>
      </ul>
    </div>
  </aside>
</template>
