<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

import EmptyState from '@/components/EmptyState.vue'
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

const tasks = useTaskStore()

const filter = ref<'all' | 'active' | 'succeeded' | 'failed'>('all')
const cancelling = ref<number | null>(null)
const now = ref(Date.now())
let timer: ReturnType<typeof setInterval> | null = null

const visible = computed(() =>
  tasks.tasks.filter((task) => {
    if (filter.value === 'all') return true
    if (filter.value === 'active') return isActiveTask(task.status)
    return task.status === filter.value
  }),
)

const counts = computed(() => ({
  all: tasks.tasks.length,
  active: tasks.tasks.filter((task) => isActiveTask(task.status)).length,
  succeeded: tasks.tasks.filter((task) => task.status === 'succeeded').length,
  failed: tasks.tasks.filter((task) => task.status === 'failed').length,
}))

const FILTERS = [
  { key: 'all', label: '全部' },
  { key: 'active', label: '进行中' },
  { key: 'succeeded', label: '已完成' },
  { key: 'failed', label: '失败' },
] as const

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

onMounted(() => {
  void tasks.refresh()
  timer = setInterval(() => {
    now.value = Date.now()
  }, 1000)
})
onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <section class="mx-auto w-full max-w-[110rem] px-4 py-6 md:px-6">
    <header class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 class="font-display text-2xl font-semibold tracking-tight">任务与日志</h1>
        <p class="mt-1 text-sm text-muted">
          实时通道 {{ tasks.connected ? '已连接' : '未连接' }} · 共 {{ counts.all }} 条任务
        </p>
      </div>
      <button
        type="button"
        class="rounded-control border border-border px-3 py-1.5 text-sm text-muted transition-colors hover:border-brand/60 hover:text-text"
        @click="tasks.refresh()"
      >
        刷新
      </button>
    </header>

    <div class="mt-4 flex flex-wrap items-center gap-2">
      <button
        v-for="item in FILTERS"
        :key="item.key"
        type="button"
        class="rounded-full border px-3 py-1 text-xs transition-colors"
        :class="
          filter === item.key
            ? 'border-brand bg-brand/10 text-brand'
            : 'border-border text-muted hover:border-brand/50 hover:text-text'
        "
        @click="filter = item.key"
      >
        {{ item.label }} {{ counts[item.key] }}
      </button>
    </div>

    <div class="mt-4 rounded-card border border-border bg-surface">
      <EmptyState
        v-if="!visible.length"
        title="暂无任务"
        description="扫描、批量编辑、刮削与逐字歌词任务的进度与逐条明细会通过 /ws/events 实时推送到这里。"
      />
      <ul v-else class="divide-y divide-border/60">
        <li v-for="task in visible" :key="task.id" class="px-4 py-3">
          <div class="flex flex-wrap items-center gap-x-3 gap-y-2">
            <span class="min-w-0 flex-1 truncate text-sm font-medium">{{ taskTypeLabel(task.type) }}</span>
            <span
              class="shrink-0 rounded-full border px-2 py-0.5 text-[11px]"
              :class="taskStatusTone(task.status)"
            >
              {{ taskStatusLabel(task.status) }}
            </span>
            <span class="shrink-0 font-mono text-[11px] text-muted">#{{ task.id }}</span>
            <span class="shrink-0 font-mono text-[11px] text-muted">{{ elapsed(task) }}</span>
            <button
              v-if="isActiveTask(task.status)"
              type="button"
              class="shrink-0 rounded-control border border-border px-2 py-0.5 text-[11px] text-muted transition-colors hover:border-danger/60 hover:text-danger disabled:opacity-50"
              :disabled="cancelling === task.id"
              @click="cancel(task.id)"
            >
              {{ cancelling === task.id ? '取消中…' : '取消' }}
            </button>
          </div>

          <div class="mt-2 flex items-center gap-2">
            <div class="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-surface-2">
              <div
                class="h-full rounded-full bg-brand transition-[width] duration-200"
                :style="{ width: `${taskPercent(task.processed, task.total)}%` }"
              />
            </div>
            <span class="w-24 shrink-0 text-right font-mono text-[11px] text-muted">
              {{ task.processed }}/{{ task.total || '—' }}
            </span>
          </div>

          <p
            v-if="task.message"
            class="mt-2 break-all text-xs"
            :class="task.status === 'failed' ? 'text-danger' : 'text-muted'"
          >
            {{ task.message }}
          </p>
          <p v-if="task.error" class="mt-1 break-all text-xs text-danger">{{ task.error }}</p>
        </li>
      </ul>
    </div>
  </section>
</template>
