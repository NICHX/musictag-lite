<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'

import EmptyState from '@/components/EmptyState.vue'
import { api } from '@/api/client'
import type { Library, Page, Track } from '@/api/types'

type FilterKey = 'all' | 'no-cover' | 'no-lyrics' | 'incomplete'

const libraries = ref<Library[]>([])
const tracks = ref<Track[]>([])
const total = ref(0)
const loading = ref(true)
const error = ref<string | null>(null)
const keyword = ref('')
const filter = ref<FilterKey>('all')

const filters: { key: FilterKey; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'no-cover', label: '缺封面' },
  { key: 'no-lyrics', label: '无歌词' },
  { key: 'incomplete', label: '缺标签' },
]

function buildParams(): Record<string, string | number | boolean> {
  const params: Record<string, string | number | boolean> = { page: 1, page_size: 50, sort: 'filename' }
  const q = keyword.value.trim()
  if (q) params.q = q
  if (filter.value === 'no-cover') params.has_cover = false
  if (filter.value === 'no-lyrics') params.has_lyrics = false
  if (filter.value === 'incomplete') params.tag_status = 'MISSING_TAGS'
  return params
}

async function loadTracks(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const page = await api.get<Page<Track>>('/tracks', buildParams())
    tracks.value = page.items
    total.value = page.total
  } catch (e) {
    error.value = e instanceof Error ? e.message : '加载失败'
  } finally {
    loading.value = false
  }
}

async function load(): Promise<void> {
  try {
    libraries.value = await api.get<Library[]>('/libraries')
  } catch (e) {
    error.value = e instanceof Error ? e.message : '加载失败'
  }
  await loadTracks()
}

function selectFilter(key: FilterKey): void {
  filter.value = key
  void loadTracks()
}

const hasLibraries = computed(() => libraries.value.length > 0)

function formatDuration(seconds: number | null): string {
  if (!seconds) return '—'
  const minutes = Math.floor(seconds / 60)
  const rest = Math.floor(seconds % 60)
  return `${minutes}:${String(rest).padStart(2, '0')}`
}

function formatBitrate(bitrate: number | null): string {
  return bitrate ? `${Math.round(bitrate / 1000)} kbps` : '—'
}

function initial(track: Track): string {
  return (track.title || track.filename || '?').trim().charAt(0).toUpperCase()
}

onMounted(load)
</script>

<template>
  <section class="mx-auto w-full max-w-6xl px-4 py-6 md:px-6">
    <header class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 class="font-display text-2xl font-semibold tracking-tight">资源库</h1>
        <p class="mt-1 text-sm text-muted">
          共 {{ total }} 首 · {{ libraries.length }} 个库
        </p>
      </div>
      <form class="flex items-center gap-2" @submit.prevent="loadTracks">
        <label class="sr-only" for="library-search">搜索曲目</label>
        <input
          id="library-search"
          v-model="keyword"
          type="search"
          placeholder="标题 / 艺术家 / 专辑 / 文件名"
          class="w-56 rounded-control border border-border bg-surface px-3 py-1.5 text-sm text-text outline-none placeholder:text-muted focus:border-brand"
        />
        <button
          type="submit"
          class="rounded-control bg-brand px-3 py-1.5 text-sm font-medium text-bg transition-colors hover:bg-brand-600"
        >
          搜索
        </button>
      </form>
    </header>

    <div class="mt-4 flex flex-wrap items-center gap-2">
      <button
        v-for="item in filters"
        :key="item.key"
        type="button"
        class="rounded-full border px-3 py-1 text-xs transition-colors"
        :class="
          filter === item.key
            ? 'border-brand bg-brand/10 text-brand'
            : 'border-border text-muted hover:border-brand/50 hover:text-text'
        "
        @click="selectFilter(item.key)"
      >
        {{ item.label }}
      </button>
      <span class="ml-auto text-xs text-muted">扫描与批量操作将在 M1 开放</span>
    </div>

    <p v-if="error" class="mt-4 rounded-control border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
      {{ error }}
    </p>

    <div class="mt-5 rounded-card border border-border bg-surface">
      <p v-if="loading" class="px-4 py-10 text-center text-sm text-muted">加载中…</p>

      <EmptyState
        v-else-if="!hasLibraries"
        title="还没有音乐库"
        description="先在设置里添加一个音乐库根目录，才能扫描并管理曲目。"
      >
        <RouterLink
          to="/settings"
          class="inline-flex items-center gap-1.5 rounded-control bg-brand px-3.5 py-2 text-sm font-medium text-bg transition-colors hover:bg-brand-600"
        >
          前往设置
        </RouterLink>
      </EmptyState>

      <EmptyState
        v-else-if="!tracks.length"
        title="这个库里还没有曲目"
        description="目录扫描（含增量）将在 M1 实现，届时这里会展示曲目列表与封面墙。"
      />

      <div v-else class="overflow-x-auto">
        <table class="w-full border-collapse text-sm">
          <thead>
            <tr class="border-b border-border text-left text-xs text-muted">
              <th class="w-14 px-3 py-2 font-medium">封面</th>
              <th class="px-3 py-2 font-medium">标题</th>
              <th class="px-3 py-2 font-medium">艺术家</th>
              <th class="px-3 py-2 font-medium">专辑</th>
              <th class="px-3 py-2 font-medium">时长</th>
              <th class="px-3 py-2 font-medium">格式</th>
              <th class="px-3 py-2 font-medium">码率</th>
              <th class="px-3 py-2 font-medium">状态</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="track in tracks" :key="track.id" class="border-b border-border/60 hover:bg-surface-2">
              <td class="px-3 py-2">
                <span
                  class="grid h-9 w-9 place-items-center rounded-control bg-surface-2 font-mono text-xs text-muted"
                  aria-hidden="true"
                >
                  {{ initial(track) }}
                </span>
              </td>
              <td class="px-3 py-2">{{ track.title || '—' }}</td>
              <td class="px-3 py-2 text-muted">{{ track.artist || '—' }}</td>
              <td class="px-3 py-2 text-muted">{{ track.album || '—' }}</td>
              <td class="px-3 py-2 font-mono text-xs text-muted">{{ formatDuration(track.duration) }}</td>
              <td class="px-3 py-2">{{ track.format || '—' }}</td>
              <td class="px-3 py-2 font-mono text-xs text-muted">{{ formatBitrate(track.bitrate) }}</td>
              <td class="px-3 py-2">
                <span class="rounded-full border border-border px-2 py-0.5 text-[11px] text-muted">
                  {{ track.tag_status }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>
