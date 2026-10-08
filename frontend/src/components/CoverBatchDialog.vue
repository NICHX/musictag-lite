<script setup lang="ts">
import { computed, ref } from 'vue'

import { coverApi } from '@/api/endpoints'
import type { CoverAssignment, CoverBatchMatch } from '@/api/types'
import { useTaskStore } from '@/stores/tasks'
import { useUiStore } from '@/stores/ui'

const props = defineProps<{ ids: number[] }>()
const emit = defineEmits<{ close: []; done: [] }>()

const tasks = useTaskStore()
const ui = useUiStore()

const files = ref<File[]>([])
const matches = ref<CoverBatchMatch[]>([])
const albums = ref<{ label: string; track_ids: number[] }[]>([])
const allTrackIds = ref<number[]>([])
const choices = ref<Record<number, string>>({})
const busy = ref(false)
const error = ref<string | null>(null)
const notice = ref<string | null>(null)

const STATUS: Record<string, { label: string; className: string }> = {
  ok: { label: '已匹配', className: 'border-success/40 text-success' },
  ambiguous: { label: '歧义', className: 'border-warning/40 text-warning' },
  unmatched: { label: '未命中', className: 'border-danger/40 text-danger' },
}

const MATCH_LABEL: Record<string, string> = {
  stem: '同名匹配',
  album: '专辑模板命中',
  album_name: '专辑名命中',
}

function resolvedIds(index: number): number[] {
  const choice = choices.value[index] ?? 'none'
  if (choice === 'none') return []
  if (choice === 'all') return allTrackIds.value
  if (choice === 'auto') return matches.value.find((m) => m.index === index)?.track_ids ?? []
  if (choice.startsWith('album:')) {
    const label = choice.slice('album:'.length)
    return albums.value.find((item) => item.label === label)?.track_ids ?? []
  }
  return []
}

const assignments = computed<CoverAssignment[]>(() =>
  files.value
    .map((_file, index) => ({ index, track_ids: resolvedIds(index) }))
    .filter((item) => item.track_ids.length > 0),
)
const targetCount = computed(() =>
  assignments.value.reduce((sum, item) => sum + item.track_ids.length, 0),
)

async function onFiles(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  files.value = Array.from(input.files ?? [])
  matches.value = []
  choices.value = {}
  notice.value = null
  error.value = null
  if (!files.value.length) return

  busy.value = true
  try {
    const result = await coverApi.batchPreview({
      ids: props.ids,
      filenames: files.value.map((file) => file.name),
    })
    matches.value = result.matches
    albums.value = result.albums
    allTrackIds.value = result.all_track_ids
    const next: Record<number, string> = {}
    for (const match of result.matches) {
      next[match.index] = match.status === 'ok' ? 'auto' : 'none'
    }
    choices.value = next
  } catch (e) {
    error.value = e instanceof Error ? e.message : '匹配失败'
  } finally {
    busy.value = false
  }
}

async function apply(): Promise<void> {
  if (!assignments.value.length) return
  busy.value = true
  error.value = null
  try {
    const task = await coverApi.batchReplace(files.value, assignments.value)
    notice.value = `已提交封面写入任务 #${task.task_id}（${targetCount.value} 首）`
    tasks.connect()
    void tasks.refresh()
    ui.toggleTaskCenter(true)
    emit('done')
    emit('close')
  } catch (e) {
    error.value = e instanceof Error ? e.message : '提交失败'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div
    class="fixed inset-0 z-50 flex items-start justify-center bg-black/60 p-4 md:items-center"
    role="dialog"
    aria-modal="true"
    aria-label="封面批量替换"
    @click.self="emit('close')"
  >
    <div class="flex max-h-[88vh] w-full max-w-3xl flex-col overflow-hidden rounded-card border border-border bg-surface">
      <header class="flex items-center gap-3 border-b border-border px-4 py-3">
        <h2 class="text-sm font-medium">封面批量替换</h2>
        <span class="text-xs text-muted">已选 {{ ids.length }} 首 · 按文件名在所选曲目内匹配</span>
        <button
          type="button"
          class="ml-auto rounded-control px-2 py-1 text-xs text-muted transition-colors hover:text-text"
          @click="emit('close')"
        >
          关闭
        </button>
      </header>

      <div class="flex-1 overflow-y-auto px-4 py-4">
        <label class="block text-xs font-medium text-muted" for="cover-batch-files">选择图片（可多选）</label>
        <input
          id="cover-batch-files"
          type="file"
          accept="image/*"
          multiple
          class="mt-1.5 block w-full text-sm text-muted file:mr-3 file:rounded-control file:border file:border-border file:bg-bg file:px-3 file:py-1.5 file:text-sm file:text-text"
          @change="onFiles"
        />

        <p v-if="notice" class="mt-3 rounded-control border border-info/40 bg-info/10 px-3 py-2 text-sm text-info">
          {{ notice }}
        </p>
        <p v-if="error" class="mt-3 rounded-control border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
          {{ error }}
        </p>

        <p v-if="!files.length" class="mt-4 text-sm text-muted">
          选择图片后会自动匹配：先按「与音频同名」，再按「{专辑艺术家} - {专辑}」，最后按「专辑名」。
        </p>

        <div v-else class="mt-4 overflow-hidden rounded-card border border-border">
          <table class="w-full border-collapse text-sm">
            <thead>
              <tr class="border-b border-border text-left text-xs text-muted">
                <th class="px-3 py-2 font-medium">图片</th>
                <th class="px-3 py-2 font-medium">匹配</th>
                <th class="px-3 py-2 font-medium">目标</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="match in matches" :key="match.index" class="border-b border-border/60">
                <td class="px-3 py-2">
                  <span class="block max-w-[16rem] truncate font-mono text-xs" :title="match.filename">
                    {{ match.filename }}
                  </span>
                </td>
                <td class="px-3 py-2">
                  <span
                    class="rounded-full border px-2 py-0.5 text-[11px]"
                    :class="STATUS[match.status].className"
                  >
                    {{ STATUS[match.status].label }}
                  </span>
                  <span v-if="match.match" class="ml-2 text-xs text-muted">
                    {{ MATCH_LABEL[match.match] }}
                  </span>
                </td>
                <td class="px-3 py-2">
                  <select
                    v-model="choices[match.index]"
                    class="w-full rounded-control border border-border bg-bg px-2 py-1 text-xs text-text outline-none focus:border-brand"
                    :aria-label="`目标：${match.filename}`"
                  >
                    <option v-if="match.status === 'ok'" value="auto">
                      自动匹配（{{ match.track_ids.length }} 首）
                    </option>
                    <option value="none">忽略</option>
                    <option value="all">所选全部（{{ allTrackIds.length }} 首）</option>
                    <option v-for="album in albums" :key="album.label" :value="`album:${album.label}`">
                      专辑：{{ album.label }}（{{ album.track_ids.length }}）
                    </option>
                  </select>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <footer class="flex items-center gap-3 border-t border-border px-4 py-3">
        <span class="text-xs text-muted">将写入 {{ assignments.length }} 张图 · 覆盖 {{ targetCount }} 首</span>
        <button
          type="button"
          class="ml-auto rounded-control border border-border px-3 py-1.5 text-sm text-muted transition-colors hover:text-text"
          @click="emit('close')"
        >
          取消
        </button>
        <button
          type="button"
          class="rounded-control bg-brand px-3.5 py-1.5 text-sm font-medium text-bg transition-colors hover:bg-brand-600 disabled:opacity-50"
          :disabled="busy || assignments.length === 0"
          @click="apply"
        >
          {{ busy ? '处理中…' : '确认写入' }}
        </button>
      </footer>
    </div>
  </div>
</template>
