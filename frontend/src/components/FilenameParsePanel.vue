<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'

import EmptyState from '@/components/EmptyState.vue'
import { filenameBatchApi, systemApi } from '@/api/endpoints'
import type { ParseFilenameBatchResponse } from '@/api/types'
import { useLibraryStore } from '@/stores/library'
import { useTaskStore } from '@/stores/tasks'
import { useUiStore } from '@/stores/ui'

const store = useLibraryStore()
const tasks = useTaskStore()
const ui = useUiStore()

const DIFF_LABELS: Record<string, string> = {
  title: '标题',
  artist: '艺术家',
  album: '专辑',
  track_no: '音轨号',
}

const STATUS: Record<string, { label: string; className: string }> = {
  ok: { label: '可写入', className: 'border-success/40 text-success' },
  unchanged: { label: '无变更', className: 'border-border text-muted' },
  invalid: { label: '无结果', className: 'border-warning/40 text-warning' },
}

const strategy = ref<'fill_empty' | 'overwrite'>('fill_empty')
const useAi = ref(false)
const aiAvailable = ref(false)
const result = ref<ParseFilenameBatchResponse | null>(null)
const busy = ref(false)
const error = ref<string | null>(null)
const notice = ref<string | null>(null)

const selectedIds = computed(() => [...store.selectedIds])
const hasSelection = computed(() => store.selectedCount > 0)

function text(value: unknown): string {
  return value === null || value === undefined || value === '' ? '∅' : String(value)
}

function parsedSummary(item: ParseFilenameBatchResponse['items'][number]): string {
  const parts = [
    item.fields.title,
    item.fields.artist,
    item.fields.album,
    item.fields.track_no != null ? `#${item.fields.track_no}` : null,
  ]
  const filled = parts.filter((value) => value !== null && value !== '')
  return filled.length ? filled.join(' · ') : '—'
}

async function runPreview(): Promise<void> {
  if (!hasSelection.value) return
  busy.value = true
  error.value = null
  notice.value = null
  try {
    result.value = await filenameBatchApi.preview({
      ids: selectedIds.value,
      use_ai: useAi.value,
      strategy: strategy.value,
    })
  } catch (e) {
    error.value = e instanceof Error ? e.message : '预演失败'
    result.value = null
  } finally {
    busy.value = false
  }
}

async function runApply(): Promise<void> {
  if (!result.value || result.value.changed === 0) return
  busy.value = true
  error.value = null
  notice.value = null
  try {
    const task = await filenameBatchApi.apply({
      ids: selectedIds.value,
      use_ai: useAi.value,
      strategy: strategy.value,
    })
    notice.value = `已提交解析写入任务 #${task.task_id}（${result.value.changed} 首），进度见任务中心`
    tasks.connect()
    void tasks.refresh()
    ui.toggleTaskCenter(true)
    result.value = null
    store.clearSelection()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '提交失败'
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  try {
    aiAvailable.value = (await systemApi.capabilities()).ai
  } catch {
    aiAvailable.value = false
  }
})
</script>

<template>
  <div>
    <div class="rounded-card border border-border bg-surface p-4">
      <div class="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
        <span class="text-xs text-muted">写入策略</span>
        <label class="flex items-center gap-2">
          <input v-model="strategy" type="radio" value="fill_empty" name="parse-strategy" />
          仅填空（不覆盖已有标签）
        </label>
        <label class="flex items-center gap-2">
          <input v-model="strategy" type="radio" value="overwrite" name="parse-strategy" />
          覆盖
        </label>
        <label
          class="ml-auto flex items-center gap-2"
          :title="aiAvailable ? '' : 'AI 未配置，可在设置中启用'"
        >
          <input v-model="useAi" type="checkbox" :disabled="!aiAvailable" />
          AI 解析
        </label>
      </div>

      <div class="mt-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          class="rounded-control bg-brand px-3.5 py-2 text-sm font-medium text-bg transition-colors hover:bg-brand-600 disabled:opacity-50"
          :disabled="busy || !hasSelection"
          @click="runPreview"
        >
          {{ busy ? '处理中…' : '预演' }}
        </button>
        <span v-if="hasSelection" class="text-xs text-muted">已选 {{ store.selectedCount }} 首</span>
        <RouterLink v-else to="/library" class="text-xs text-brand hover:underline">
          先去资源库多选曲目
        </RouterLink>
      </div>
    </div>

    <p v-if="notice" class="mt-3 rounded-control border border-info/40 bg-info/10 px-3 py-2 text-sm text-info">
      {{ notice }}
    </p>
    <p v-if="error" class="mt-3 rounded-control border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
      {{ error }}
    </p>

    <div v-if="!hasSelection && !result" class="mt-5 rounded-card border border-border bg-surface">
      <EmptyState
        title="尚未选择曲目"
        description="到资源库勾选要按文件名解析的曲目，再回来预演与写入。"
      >
        <RouterLink
          to="/library"
          class="inline-flex items-center rounded-control bg-brand px-3.5 py-2 text-sm font-medium text-bg transition-colors hover:bg-brand-600"
        >
          前往资源库
        </RouterLink>
      </EmptyState>
    </div>

    <div v-else-if="result" class="mt-5 overflow-hidden rounded-card border border-border bg-surface">
      <div class="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-border px-4 py-3 text-sm">
        <span class="text-success">可写入 {{ result.changed }}</span>
        <span class="text-muted">无变更 {{ result.unchanged }}</span>
        <span class="text-warning">无结果 {{ result.invalid }}</span>
        <button
          type="button"
          class="ml-auto rounded-control bg-brand px-3 py-1.5 text-xs font-medium text-bg transition-colors hover:bg-brand-600 disabled:opacity-50"
          :disabled="busy || result.changed === 0"
          @click="runApply"
        >
          确认写入{{ result.changed ? `（${result.changed}）` : '' }}
        </button>
      </div>

      <div class="overflow-x-auto">
        <table class="w-full border-collapse text-sm">
          <thead>
            <tr class="border-b border-border text-left text-xs text-muted">
              <th class="px-3 py-2 font-medium">状态</th>
              <th class="px-3 py-2 font-medium">文件</th>
              <th class="px-3 py-2 font-medium">解析结果</th>
              <th class="px-3 py-2 font-medium">将写入</th>
              <th class="px-3 py-2 font-medium">说明</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in result.items" :key="item.track_id" class="border-b border-border/60">
              <td class="px-3 py-2">
                <span
                  class="rounded-full border px-2 py-0.5 text-[11px]"
                  :class="STATUS[item.status].className"
                >
                  {{ STATUS[item.status].label }}
                </span>
              </td>
              <td class="px-3 py-2">
                <span
                  class="block max-w-[16rem] truncate font-mono text-xs text-muted"
                  :title="item.path"
                >
                  {{ item.path }}
                </span>
              </td>
              <td class="px-3 py-2 text-muted">{{ parsedSummary(item) }}</td>
              <td class="px-3 py-2">
                <div v-if="item.diffs.length" class="flex flex-col gap-0.5">
                  <span v-for="diff in item.diffs" :key="diff.field" class="font-mono text-xs">
                    <span class="text-muted">{{ DIFF_LABELS[diff.field] ?? diff.field }}</span>
                    <span class="text-danger"> {{ text(diff.old_value) }}</span>
                    <span class="text-muted"> → </span>
                    <span class="text-success">{{ text(diff.new_value) }}</span>
                  </span>
                </div>
                <span v-else class="text-xs text-muted">—</span>
              </td>
              <td class="px-3 py-2 text-xs text-muted">
                <span v-if="item.source === 'ai'" class="text-brand">AI</span>
                <span v-else>启发式</span>
                <span v-if="item.note"> · {{ item.note }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
