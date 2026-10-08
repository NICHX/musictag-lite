<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import EmptyState from '@/components/EmptyState.vue'
import { providerApi, scrapeApi, trackApi } from '@/api/endpoints'
import type { Candidate, Track } from '@/api/types'
import { useLibraryStore } from '@/stores/library'
import { useTaskStore } from '@/stores/tasks'

const route = useRoute()
const store = useLibraryStore()
const tasks = useTaskStore()

const DIFF_FIELDS: { key: string; label: string }[] = [
  { key: 'title', label: '标题' },
  { key: 'artist', label: '艺术家' },
  { key: 'album', label: '专辑' },
  { key: 'year', label: '年份' },
]

const selectedTrackId = ref<number | null>(null)
const candidates = ref<Candidate[]>([])
const chosenUid = ref<string | null>(null)
const providerNames = ref<Record<string, string>>({})
const searching = ref(false)
const applying = ref(false)
const error = ref<string | null>(null)
const result = ref<string | null>(null)

const onlyMissing = ref(true)
const applyCover = ref(true)
const applyLyrics = ref(false)

const currentTrack = computed<Track | null>(
  () => store.tracks.find((track) => track.id === selectedTrackId.value) ?? null,
)

async function loadTracks(): Promise<void> {
  store.query.page_size = 200
  await store.loadTracks()
}

async function search(): Promise<void> {
  if (!selectedTrackId.value) {
    error.value = '请先选择一首曲目'
    return
  }
  searching.value = true
  error.value = null
  result.value = null
  candidates.value = []
  chosenUid.value = null
  try {
    const response = await scrapeApi.search({ track_id: selectedTrackId.value, limit: 10 })
    candidates.value = response.candidates
    if (candidates.value.length) chosenUid.value = scrapeApi.list(candidates.value[0])
    if (!candidates.value.length) result.value = '没有找到候选，试试先补全标题/艺术家。'
  } catch (e) {
    error.value = e instanceof Error ? e.message : '搜索失败'
  } finally {
    searching.value = false
  }
}

async function apply(): Promise<void> {
  if (!selectedTrackId.value || !chosenUid.value) return
  applying.value = true
  error.value = null
  result.value = null
  try {
    const response = await scrapeApi.apply({
      track_id: selectedTrackId.value,
      candidate_ids: [chosenUid.value],
      only_missing: onlyMissing.value,
      apply_cover: applyCover.value,
      apply_lyrics: applyLyrics.value,
    })
    const parts = [`字段：${response.applied_fields.join('、') || '无'}`]
    if (response.cover_applied) parts.push('封面已写入')
    if (response.lyrics_applied) parts.push('歌词已写入')
    result.value = `应用完成 · ${parts.join(' · ')}`
    tasks.connect()
    void tasks.refresh()
    await loadTracks()
    void trackApi.get(selectedTrackId.value)
  } catch (e) {
    error.value = e instanceof Error ? e.message : '应用失败'
  } finally {
    applying.value = false
  }
}

function valueOf(track: Track | null, field: string): string {
  if (!track) return '∅'
  const raw = (track as unknown as Record<string, unknown>)[field]
  return raw == null || raw === '' ? '∅' : String(raw)
}

function candidateValue(candidate: Candidate, field: string): string {
  const raw = (candidate as unknown as Record<string, unknown>)[field]
  return raw == null || raw === '' ? '∅' : String(raw)
}

function changed(candidate: Candidate, field: string): boolean {
  return valueOf(currentTrack.value, field) !== candidateValue(candidate, field)
}

onMounted(async () => {
  const [providers] = await Promise.all([providerApi.list().catch(() => []), store.loadLibraries()])
  providerNames.value = Object.fromEntries(providers.map((item) => [item.key, item.name]))
  await loadTracks()
  const fromQuery = Number(route.query.track)
  if (fromQuery && store.tracks.some((track) => track.id === fromQuery)) {
    selectedTrackId.value = fromQuery
    await search()
  }
})
</script>

<template>
  <section class="mx-auto w-full max-w-6xl px-4 py-6 md:px-6">
    <header>
      <h1 class="font-display text-2xl font-semibold tracking-tight">刮削中心</h1>
      <p class="mt-1 text-sm text-muted">插件式数据源：MusicBrainz · Cover Art Archive · LRCLIB（开放、可插拔）</p>
    </header>

    <div class="mt-5 flex flex-wrap items-center gap-2">
      <select
        v-model.number="selectedTrackId"
        class="min-w-60 rounded-control border border-border bg-surface px-2.5 py-1.5 text-sm text-text outline-none focus:border-brand"
        aria-label="选择曲目"
      >
        <option :value="null">选择一首曲目…</option>
        <option v-for="track in store.tracks" :key="track.id" :value="track.id">
          {{ track.title || track.filename }} — {{ track.artist || '未知' }}
        </option>
      </select>
      <button
        type="button"
        class="rounded-control bg-brand px-3.5 py-1.5 text-sm font-medium text-bg transition-colors hover:bg-brand-600 disabled:opacity-50"
        :disabled="searching || !selectedTrackId"
        @click="search"
      >
        {{ searching ? '搜索中…' : '搜索候选' }}
      </button>
      <label class="flex items-center gap-1.5 text-xs text-muted">
        <input v-model="onlyMissing" type="checkbox" /> 仅补空值
      </label>
      <label class="flex items-center gap-1.5 text-xs text-muted">
        <input v-model="applyCover" type="checkbox" /> 同时写封面
      </label>
      <label class="flex items-center gap-1.5 text-xs text-muted">
        <input v-model="applyLyrics" type="checkbox" /> 同时写歌词
      </label>
    </div>

    <p v-if="error" class="mt-3 rounded-control border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
      {{ error }}
    </p>
    <p v-if="result" class="mt-3 rounded-control border border-success/40 bg-success/10 px-3 py-2 text-sm text-success">
      {{ result }}
    </p>

    <div class="mt-5 grid gap-5 lg:grid-cols-[1fr_1.4fr]">
      <!-- 当前曲目 -->
      <div class="rounded-card border border-border bg-surface p-4">
        <h2 class="text-xs font-medium uppercase tracking-wide text-muted">当前曲目</h2>
        <dl v-if="currentTrack" class="mt-3 space-y-2 text-sm">
          <div class="flex gap-3">
            <dt class="w-16 shrink-0 text-xs text-muted">文件名</dt>
            <dd class="min-w-0 truncate font-mono text-xs" :title="currentTrack.filename">
              {{ currentTrack.filename }}
            </dd>
          </div>
          <div v-for="field in DIFF_FIELDS" :key="field.key" class="flex gap-3">
            <dt class="w-16 shrink-0 text-xs text-muted">{{ field.label }}</dt>
            <dd class="min-w-0 truncate">{{ valueOf(currentTrack, field.key) }}</dd>
          </div>
          <div class="flex gap-3">
            <dt class="w-16 shrink-0 text-xs text-muted">音轨号</dt>
            <dd class="font-mono">{{ valueOf(currentTrack, 'track_no') }}</dd>
          </div>
        </dl>
        <p v-else class="mt-3 text-sm text-muted">尚未选择曲目。</p>
      </div>

      <!-- 候选 -->
      <div class="rounded-card border border-border bg-surface p-4">
        <h2 class="text-xs font-medium uppercase tracking-wide text-muted">
          候选（{{ candidates.length }}）
        </h2>

        <EmptyState
          v-if="!candidates.length"
          title="暂无候选"
          description="选择一首曲目后点击「搜索候选」，结果会按匹配分排序并展示字段差异。"
        />

        <ul v-else class="mt-3 space-y-3">
          <li
            v-for="candidate in candidates"
            :key="scrapeApi.list(candidate)"
            class="cursor-pointer rounded-card border p-3 transition-colors"
            :class="chosenUid === scrapeApi.list(candidate) ? 'border-brand' : 'border-border hover:border-brand/50'"
            @click="chosenUid = scrapeApi.list(candidate)"
          >
            <div class="flex items-center gap-2">
              <span class="rounded-full border border-border px-2 py-0.5 text-[11px] text-muted">
                {{ providerNames[candidate.provider] ?? candidate.provider }}
              </span>
              <span class="font-mono text-[11px] text-muted">
                {{ Math.round(candidate.score * 100) }} 分
              </span>
              <span class="ml-auto text-sm">{{ candidate.title || '—' }}</span>
            </div>
            <div class="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
              <div v-for="field in DIFF_FIELDS" :key="field.key" class="flex gap-2">
                <span class="w-12 shrink-0 text-muted">{{ field.label }}</span>
                <span
                  class="min-w-0 truncate"
                  :class="changed(candidate, field.key) ? 'text-success' : 'text-muted'"
                >
                  {{ candidateValue(candidate, field.key) }}
                </span>
              </div>
            </div>
          </li>
        </ul>

        <div v-if="candidates.length" class="mt-4 flex justify-end">
          <button
            type="button"
            class="rounded-control bg-brand px-4 py-1.5 text-sm font-medium text-bg transition-colors hover:bg-brand-600 disabled:opacity-50"
            :disabled="applying || !chosenUid"
            @click="apply"
          >
            {{ applying ? '应用中…' : '应用选中候选' }}
          </button>
        </div>
      </div>
    </div>
  </section>
</template>
