<script setup lang="ts">
import { onMounted } from 'vue'

import EmptyState from '@/components/EmptyState.vue'
import { useTaskStore } from '@/stores/tasks'

const tasks = useTaskStore()

const statusLabels: Record<string, string> = {
  queued: '排队中',
  running: '进行中',
  succeeded: '已完成',
  failed: '失败',
  cancelled: '已取消',
}

onMounted(() => {
  void tasks.refresh()
})
</script>

<template>
  <section class="mx-auto w-full max-w-6xl px-4 py-6 md:px-6">
    <header class="flex items-center justify-between gap-3">
      <div>
        <h1 class="font-display text-2xl font-semibold tracking-tight">任务与日志</h1>
        <p class="mt-1 text-sm text-muted">
          实时通道 {{ tasks.connected ? '已连接' : '未连接' }} · 共 {{ tasks.tasks.length }} 条任务
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

    <div class="mt-5 rounded-card border border-border bg-surface">
      <EmptyState
        v-if="!tasks.tasks.length"
        title="暂无任务"
        description="扫描、批量编辑与刮削任务的进度会通过 /ws/events 实时推送到这里。"
      />
      <ul v-else class="divide-y divide-border/60">
        <li v-for="task in tasks.tasks" :key="task.id" class="flex items-center gap-4 px-4 py-3 text-sm">
          <span class="font-mono text-xs text-muted">#{{ task.id }}</span>
          <span class="w-28 shrink-0">{{ task.type }}</span>
          <div class="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-2">
            <div
              class="h-full bg-accent transition-[width] duration-200"
              :style="{ width: task.total ? `${Math.round((task.processed / task.total) * 100)}%` : '0%' }"
            />
          </div>
          <span class="w-20 text-right font-mono text-xs text-muted">{{ task.processed }}/{{ task.total }}</span>
          <span class="w-20 text-right text-xs text-muted">{{ statusLabels[task.status] ?? task.status }}</span>
        </li>
      </ul>
    </div>
  </section>
</template>
