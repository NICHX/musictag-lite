<script setup lang="ts">
import { onMounted, ref } from 'vue'

import EmptyState from '@/components/EmptyState.vue'
import { api } from '@/api/client'
import type { OperationLog, Page } from '@/api/types'

const logs = ref<OperationLog[]>([])
const loading = ref(true)
const error = ref<string | null>(null)

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const page = await api.get<Page<OperationLog>>('/logs', { page: 1, page_size: 50 })
    logs.value = page.items
  } catch (e) {
    error.value = e instanceof Error ? e.message : '加载失败'
  } finally {
    loading.value = false
  }
}

function formatTime(value: string): string {
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

onMounted(load)
</script>

<template>
  <section class="mx-auto w-full max-w-6xl px-4 py-6 md:px-6">
    <header class="flex items-center justify-between gap-3">
      <div>
        <h1 class="font-display text-2xl font-semibold tracking-tight">操作日志</h1>
        <p class="mt-1 text-sm text-muted">记录每次写入的字段、前后值与来源</p>
      </div>
      <button
        type="button"
        class="rounded-control border border-border px-3 py-1.5 text-sm text-muted transition-colors hover:border-brand/60 hover:text-text"
        @click="load"
      >
        刷新
      </button>
    </header>

    <p v-if="error" class="mt-4 rounded-control border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
      {{ error }}
    </p>

    <div class="mt-5 rounded-card border border-border bg-surface">
      <p v-if="loading" class="px-4 py-10 text-center text-sm text-muted">加载中…</p>
      <EmptyState
        v-else-if="!logs.length"
        title="暂无操作记录"
        description="单条/批量编辑、刮削应用与封面写入都会在此留痕（M1 起产生数据）。"
      />
      <div v-else class="overflow-x-auto">
        <table class="w-full border-collapse text-sm">
          <thead>
            <tr class="border-b border-border text-left text-xs text-muted">
              <th class="px-3 py-2 font-medium">时间</th>
              <th class="px-3 py-2 font-medium">曲目</th>
              <th class="px-3 py-2 font-medium">操作</th>
              <th class="px-3 py-2 font-medium">字段</th>
              <th class="px-3 py-2 font-medium">旧值 → 新值</th>
              <th class="px-3 py-2 font-medium">来源</th>
              <th class="px-3 py-2 font-medium">结果</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="log in logs" :key="log.id" class="border-b border-border/60 hover:bg-surface-2">
              <td class="whitespace-nowrap px-3 py-2 font-mono text-xs text-muted">{{ formatTime(log.created_at) }}</td>
              <td class="px-3 py-2 font-mono text-xs text-muted">{{ log.track_id ?? '—' }}</td>
              <td class="px-3 py-2">{{ log.action }}</td>
              <td class="px-3 py-2 text-muted">{{ log.field ?? '—' }}</td>
              <td class="px-3 py-2 text-muted">{{ log.old_value ?? '∅' }} → {{ log.new_value ?? '∅' }}</td>
              <td class="px-3 py-2 text-muted">{{ log.source }}</td>
              <td class="px-3 py-2 text-muted">{{ log.result }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>
