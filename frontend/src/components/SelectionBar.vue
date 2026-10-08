<script setup lang="ts">
import { ref } from 'vue'

import { trackApi } from '@/api/endpoints'
import type { BatchEditOp } from '@/api/types'

const props = defineProps<{ ids: number[] }>()
const emit = defineEmits<{ clear: []; done: [] }>()

const FIELDS = [
  { key: 'title', label: '标题' },
  { key: 'artist', label: '艺术家' },
  { key: 'album', label: '专辑' },
  { key: 'album_artist', label: '专辑艺术家' },
  { key: 'genre', label: '流派' },
  { key: 'year', label: '年份' },
  { key: 'track_no', label: '音轨号' },
  { key: 'disc_no', label: '碟号' },
  { key: 'comment', label: '注释' },
]

const field = ref('album')
const strategy = ref<'overwrite' | 'fill_empty' | 'append' | 'replace'>('overwrite')
const value = ref('')
const find = ref('')
const replace = ref('')
const useRegex = ref(false)
const preview = ref<string | null>(null)
const busy = ref(false)
const error = ref<string | null>(null)

function buildOps(): BatchEditOp[] {
  if (strategy.value === 'replace') {
    return [{ field: field.value, op: 'replace', find: find.value, replace: replace.value, use_regex: useRegex.value }]
  }
  return [{ field: field.value, op: 'set', value: value.value }]
}

async function runPreview(): Promise<void> {
  busy.value = true
  error.value = null
  preview.value = null
  try {
    const result = await trackApi.batchPreview({
      ids: props.ids,
      ops: buildOps(),
      strategy: strategy.value,
    })
    preview.value = `将修改 ${result.changed} / 共 ${result.total} 首`
  } catch (e) {
    error.value = e instanceof Error ? e.message : '预演失败'
  } finally {
    busy.value = false
  }
}

async function apply(): Promise<void> {
  busy.value = true
  error.value = null
  preview.value = null
  try {
    await trackApi.batchApply({ ids: props.ids, ops: buildOps(), strategy: strategy.value })
    emit('done')
    emit('clear')
  } catch (e) {
    error.value = e instanceof Error ? e.message : '应用失败'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="sticky bottom-0 z-30 border-t border-border bg-surface/95 px-3 py-2.5 backdrop-blur md:px-4">
    <div class="mx-auto flex w-full max-w-6xl flex-wrap items-center gap-2">
      <span class="rounded-full bg-brand/15 px-2.5 py-1 text-xs font-medium text-brand">
        已选 {{ ids.length }} 首
      </span>

      <select
        v-model="field"
        class="rounded-control border border-border bg-bg px-2 py-1 text-xs text-text outline-none focus:border-brand"
        aria-label="目标字段"
      >
        <option v-for="item in FIELDS" :key="item.key" :value="item.key">{{ item.label }}</option>
      </select>

      <select
        v-model="strategy"
        class="rounded-control border border-border bg-bg px-2 py-1 text-xs text-text outline-none focus:border-brand"
        aria-label="写入策略"
      >
        <option value="overwrite">覆盖</option>
        <option value="fill_empty">仅填空</option>
        <option value="append">追加</option>
        <option value="replace">查找替换</option>
      </select>

      <template v-if="strategy === 'replace'">
        <input
          v-model="find"
          placeholder="查找"
          class="w-24 rounded-control border border-border bg-bg px-2 py-1 font-mono text-xs text-text outline-none focus:border-brand"
        />
        <input
          v-model="replace"
          placeholder="替换为"
          class="w-24 rounded-control border border-border bg-bg px-2 py-1 font-mono text-xs text-text outline-none focus:border-brand"
        />
        <label class="flex items-center gap-1 text-xs text-muted">
          <input v-model="useRegex" type="checkbox" /> 正则
        </label>
      </template>
      <input
        v-else
        v-model="value"
        placeholder="新值"
        class="min-w-32 flex-1 rounded-control border border-border bg-bg px-2 py-1 text-xs text-text outline-none focus:border-brand sm:max-w-60"
      />

      <button
        type="button"
        class="rounded-control border border-border px-2.5 py-1 text-xs text-muted transition-colors hover:text-text disabled:opacity-50"
        :disabled="busy"
        @click="runPreview"
      >
        预演
      </button>
      <button
        type="button"
        class="rounded-control bg-brand px-3 py-1 text-xs font-medium text-bg transition-colors hover:bg-brand-600 disabled:opacity-50"
        :disabled="busy"
        @click="apply"
      >
        应用
      </button>

      <span v-if="preview" class="text-xs text-success">{{ preview }}</span>
      <span v-if="error" class="text-xs text-danger">{{ error }}</span>

      <button
        type="button"
        class="ml-auto rounded-control border border-border px-2.5 py-1 text-xs text-muted transition-colors hover:text-text"
        @click="emit('clear')"
      >
        取消选择
      </button>
    </div>
  </div>
</template>
