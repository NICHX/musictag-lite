<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'

import { taskApi } from '@/api/endpoints'
import {
  formatElapsed,
  isActiveTask,
  taskPercent,
  taskStatusLabel,
  taskStatusTone,
  taskTypeLabel,
} from '@/lib/taskMeta'
import { useTaskStore } from '@/stores/tasks'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const tasks = useTaskStore()

const cancelling = ref<number | null>(null)
const now = ref(Date.now())
let timer: ReturnType<typeof setInterval> | null = null

/** 运行中的任务排前面，其余按 id 倒序。 */
const ordered = computed(() =>
  [...tasks.tasks].sort((a, b) => {
    const activeDiff = Number(isActiveTask(b.status)) - Number(isActiveTask(a.status))
    return activeDiff !== 0 ? activeDiff : b.id - a.id
  }),
)

function elapsed(task: (typeof tasks.tasks)[number]): string {
  return formatElapsed(task, now.value)
}

async function cancel(id: number): Promise<void> {
  cancelling.value = id
  try {
    await taskApi.cancel(id)
    await tasks.refresh()
  } finally {
    cancelling.value = null
  }
}

watch(
  () => ui.taskCenterOpen,
  (open) => {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
    if (!open) return
    void tasks.refresh()
    now.value = Date.now()
    timer = setInterval(() => {
      now.value = Date.now()
    }, 1000)
  },
  { immediate: true },
)

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <div
    v-if="ui.taskCenterOpen"
    class="fixed inset-0 z-40 bg-black/50"
    aria-hidden="true"
    @click="ui.toggleTaskCenter(false)"
  />

  <aside
    class="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l border-border bg-surface transition-transform duration-200"
    :class="ui.taskCenterOpen ? 'translate-x-0' : 'translate-x-full'"
    aria-label="任务中心"
  >
    <header class="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
      <div class="flex min-w-0 items-center gap-2">
        <h2 class="text-sm font-medium">任务中心</h2>
        <span
          class="shrink-0 rounded-full border px-2 py-0.5 text-[11px]"
          :class="tasks.connected ? 'border-success/40 text-success' : 'border-border text-muted'"
        >
          {{ tasks.connected ? '实时已连接' : '实时未连接' }}
        </span>
      </div>
      <div class="flex shrink-0 items-center gap-1">
        <button
          type="button"
          class="rounded-control border border-border px-2.5 py-1 text-xs text-muted transition-colors hover:text-text"
          @click="tasks.refresh()"
        >
          刷新
        </button>
        <button
          type="button"
          class="grid h-8 w-8 place-items-center rounded-control text-muted transition-colors hover:bg-surface-2 hover:text-text"
          aria-label="关闭"
          @click="ui.toggleTaskCenter(false)"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="h-4 w-4">
            <path d="M6 6l12 12M18 6 6 18" stroke-linecap="round" />
          </svg>
        </button>
      </div>
    </header>

    <div class="flex-1 overflow-y-auto overscroll-contain p-3">
      <p v-if="!ordered.length" class="px-2 py-10 text-center text-sm text-muted">
        暂无任务。扫描、批量编辑、刮削与逐字歌词的进度会实时显示在这里。
      </p>

      <ul v-else class="flex flex-col gap-2">
        <li
          v-for="task in ordered"
          :key="task.id"
          class="rounded-card border p-3"
          :class="isActiveTask(task.status) ? 'border-brand/30 bg-bg' : 'border-border bg-bg'"
        >
          <div class="flex items-center justify-between gap-2">
            <span class="min-w-0 truncate text-sm font-medium">{{ taskTypeLabel(task.type) }}</span>
            <span
              class="shrink-0 rounded-full border px-2 py-0.5 text-[11px]"
              :class="taskStatusTone(task.status)"
            >
              {{ taskStatusLabel(task.status) }}
            </span>
          </div>

          <div class="mt-2 flex items-center gap-2">
            <div class="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-surface-2">
              <div
                class="h-full rounded-full bg-brand transition-[width] duration-200"
                :style="{ width: `${taskPercent(task.processed, task.total)}%` }"
              />
            </div>
            <span class="shrink-0 font-mono text-[11px] text-muted">
              {{ task.processed }}/{{ task.total || '—' }} · {{ taskPercent(task.processed, task.total) }}%
            </span>
          </div>

          <!-- 明细：当前条目与逐条结果（进度条之外的关键信息） -->
          <p
            v-if="task.message"
            class="mt-2 line-clamp-2 break-all text-xs"
            :class="task.status === 'failed' ? 'text-danger' : 'text-muted'"
            :title="task.message"
          >
            {{ task.message }}
          </p>
          <p v-if="task.error" class="mt-1 line-clamp-2 break-all text-xs text-danger" :title="task.error">
            {{ task.error }}
          </p>

          <div class="mt-2 flex items-center justify-between gap-2 text-[11px] text-muted">
            <span class="truncate font-mono">#{{ task.id }} · {{ elapsed(task) }}</span>
            <button
              v-if="isActiveTask(task.status)"
              type="button"
              class="shrink-0 rounded-control border border-border px-2 py-0.5 transition-colors hover:border-danger/60 hover:text-danger disabled:opacity-50"
              :disabled="cancelling === task.id"
              @click="cancel(task.id)"
            >
              {{ cancelling === task.id ? '取消中…' : '取消' }}
            </button>
          </div>
        </li>
      </ul>
    </div>
  </aside>
</template>
