<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'

import EmptyState from '@/components/EmptyState.vue'
import { organizeApi } from '@/api/endpoints'
import type { OrganizePreviewResponse } from '@/api/types'
import {
  DEFAULT_ORGANIZE_TEMPLATE,
  ORGANIZE_FIELDS,
  ORGANIZE_STATUS,
  buildApplyPlan,
  insertField,
} from '@/lib/organize'
import { useLibraryStore } from '@/stores/library'
import { useTaskStore } from '@/stores/tasks'
import { useUiStore } from '@/stores/ui'

const store = useLibraryStore()
const tasks = useTaskStore()
const ui = useUiStore()

const template = ref(DEFAULT_ORGANIZE_TEMPLATE)
const move = ref(false)
const result = ref<OrganizePreviewResponse | null>(null)
const busy = ref(false)
const error = ref<string | null>(null)
const notice = ref<string | null>(null)

const selectedIds = computed(() => [...store.selectedIds])
const hasSelection = computed(() => store.selectedCount > 0)
const plan = computed(() => (result.value ? buildApplyPlan(result.value.items) : []))

function addField(key: string): void {
  template.value = insertField(template.value, key === 'track' ? 'track:02d' : key)
}

async function runPreview(): Promise<void> {
  if (!hasSelection.value) return
  busy.value = true
  error.value = null
  notice.value = null
  try {
    result.value = await organizeApi.preview({
      ids: selectedIds.value,
      template: template.value,
      move: move.value,
    })
  } catch (e) {
    error.value = e instanceof Error ? e.message : '预演失败'
    result.value = null
  } finally {
    busy.value = false
  }
}

async function runApply(): Promise<void> {
  const items = plan.value
  if (!items.length) return
  busy.value = true
  error.value = null
  notice.value = null
  try {
    const task = await organizeApi.apply({
      ids: selectedIds.value,
      template: template.value,
      move: move.value,
      plan: items,
    })
    notice.value = `已提交整理任务 #${task.task_id}（执行 ${items.length} 项），进度见任务中心`
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

onMounted(() => {
  void store.load()
})
</script>

<template>
  <section class="mx-auto flex min-h-full w-full max-w-6xl flex-col px-4 py-6 md:px-6">
    <header>
      <h1 class="font-display text-2xl font-semibold tracking-tight">智能整理</h1>
      <p class="mt-1 text-sm text-muted">
        按模板把文件名改为「标签」的组合：仅重命名（同级）或移动到分组目录，落盘前先预演。
      </p>
    </header>

    <div class="mt-5 rounded-card border border-border bg-surface p-4">
      <label class="block text-xs font-medium text-muted" for="organize-template">路径模板</label>
      <input
        id="organize-template"
        v-model="template"
        spellcheck="false"
        class="mt-1.5 w-full rounded-control border border-border bg-bg px-3 py-2 font-mono text-sm text-text outline-none placeholder:text-muted focus:border-brand"
        placeholder="{albumartist}/{year} - {album}/{track:02d} - {title}"
      />

      <div class="mt-3 flex flex-wrap items-center gap-1.5">
        <span class="text-xs text-muted">插入字段</span>
        <button
          v-for="field in ORGANIZE_FIELDS"
          :key="field.key"
          type="button"
          class="rounded-full border border-border px-2.5 py-0.5 font-mono text-[11px] text-muted transition-colors hover:border-brand/50 hover:text-text"
          @click="addField(field.key)"
        >
          {{ field.key }}
        </button>
      </div>

      <div class="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
        <span class="text-xs text-muted">模式</span>
        <label class="flex items-center gap-2">
          <input v-model="move" type="radio" :value="false" name="organize-mode" />
          仅重命名（同目录）
        </label>
        <label class="flex items-center gap-2">
          <input v-model="move" type="radio" :value="true" name="organize-mode" />
          移动到分组目录
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
        description="到资源库勾选要整理的曲目，再回来设置模板并预演。"
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
        <span class="text-success">可执行 {{ result.ok }}</span>
        <span class="text-danger">冲突 {{ result.conflicts }}</span>
        <span class="text-muted">未变化 {{ result.unchanged }}</span>
        <span class="text-warning">无效 {{ result.invalid }}</span>
        <button
          type="button"
          class="ml-auto rounded-control bg-brand px-3 py-1.5 text-xs font-medium text-bg transition-colors hover:bg-brand-600 disabled:opacity-50"
          :disabled="busy || plan.length === 0"
          @click="runApply"
        >
          确认执行{{ plan.length ? `（${plan.length}）` : '' }}
        </button>
      </div>

      <div class="overflow-x-auto">
        <table class="w-full border-collapse text-sm">
          <thead>
            <tr class="border-b border-border text-left text-xs text-muted">
              <th class="px-3 py-2 font-medium">状态</th>
              <th class="px-3 py-2 font-medium">当前路径</th>
              <th class="w-8 px-1 py-2" aria-hidden="true"></th>
              <th class="px-3 py-2 font-medium">目标路径</th>
              <th class="px-3 py-2 font-medium">说明</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in result.items" :key="item.track_id" class="border-b border-border/60">
              <td class="px-3 py-2">
                <span
                  class="rounded-full border px-2 py-0.5 text-[11px]"
                  :class="ORGANIZE_STATUS[item.status].className"
                >
                  {{ ORGANIZE_STATUS[item.status].label }}
                </span>
              </td>
              <td class="px-3 py-2">
                <span class="block max-w-[22rem] truncate font-mono text-xs text-muted" :title="item.source">
                  {{ item.source }}
                </span>
              </td>
              <td class="px-1 py-2 text-center text-muted">→</td>
              <td class="px-3 py-2">
                <span
                  class="block max-w-[22rem] truncate font-mono text-xs"
                  :class="item.status === 'ok' ? 'text-text' : 'text-muted'"
                  :title="item.target ?? ''"
                >
                  {{ item.target ?? '—' }}
                </span>
              </td>
              <td class="px-3 py-2 text-xs text-muted">
                <span v-if="item.reason" class="text-warning">{{ item.reason }}</span>
                <span v-else-if="item.sidecars.length">随带 {{ item.sidecars.length }} 个边车文件</span>
                <span v-else>—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>
