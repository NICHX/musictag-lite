<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { coverApi, logsApi, lyricsApi, trackApi } from '@/api/endpoints'
import type { OperationLog, Track } from '@/api/types'
import { extractAccent } from '@/lib/accent'
import { formatBitrate, formatDateTime, formatDuration, formatSize } from '@/lib/format'
import { useUiStore } from '@/stores/ui'

const props = defineProps<{ trackId: number | null }>()
const emit = defineEmits<{ close: []; saved: [track: Track] }>()

const ui = useUiStore()

const TAGS: { key: string; label: string; mono?: boolean }[] = [
  { key: 'title', label: '标题' },
  { key: 'artist', label: '艺术家' },
  { key: 'album', label: '专辑' },
  { key: 'album_artist', label: '专辑艺术家' },
  { key: 'genre', label: '流派' },
  { key: 'year', label: '年份' },
  { key: 'track_no', label: '音轨号', mono: true },
  { key: 'disc_no', label: '碟号', mono: true },
  { key: 'composer', label: '作曲' },
  { key: 'comment', label: '注释' },
]

const track = ref<Track | null>(null)
const form = ref<Record<string, string>>({})
const lyrics = ref('')
const lyricsSource = ref<string | null>(null)
const logs = ref<OperationLog[]>([])
const loading = ref(false)
const saving = ref(false)
const savingLyrics = ref(false)
const uploading = ref(false)
const message = ref<string | null>(null)
const error = ref<string | null>(null)
const coverVersion = ref(0)
const coverBroken = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

const coverUrl = computed(() =>
  track.value ? `${coverApi.url(track.value.id)}?v=${coverVersion.value}` : '',
)

async function load(id: number): Promise<void> {
  loading.value = true
  error.value = null
  message.value = null
  coverBroken.value = false
  try {
    const data = await trackApi.get(id)
    track.value = data
    form.value = Object.fromEntries(
      TAGS.map((tag) => [tag.key, data[tag.key as keyof Track] == null ? '' : String(data[tag.key as keyof Track])]),
    )
    coverVersion.value += 1

    const [lyric, logPage] = await Promise.all([
      lyricsApi.get(id).catch(() => null),
      logsApi.list({ track_id: id, page_size: 10 }).catch(() => null),
    ])
    lyrics.value = lyric?.content ?? ''
    lyricsSource.value = lyric?.source ?? null
    logs.value = logPage?.items ?? []

    if (data.has_cover) {
      const accent = await extractAccent(coverApi.url(id))
      ui.useAccent(accent)
    } else {
      ui.useAccent(null)
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : '加载失败'
  } finally {
    loading.value = false
  }
}

function close(): void {
  ui.useAccent(null)
  emit('close')
}

async function save(): Promise<void> {
  if (!track.value) return
  saving.value = true
  error.value = null
  message.value = null
  try {
    const payload: Record<string, unknown> = {}
    for (const tag of TAGS) {
      const value = (form.value[tag.key] ?? '').trim()
      payload[tag.key] = value === '' ? null : value
    }
    const updated = await trackApi.update(track.value.id, payload)
    track.value = updated
    message.value = '已保存并落盘'
    emit('saved', updated)
  } catch (e) {
    error.value = e instanceof Error ? e.message : '保存失败'
  } finally {
    saving.value = false
  }
}

async function saveLyrics(): Promise<void> {
  if (!track.value) return
  savingLyrics.value = true
  error.value = null
  message.value = null
  try {
    await lyricsApi.put(track.value.id, lyrics.value, 'embedded')
    track.value = { ...track.value, has_lyrics: true }
    lyricsSource.value = 'embedded'
    message.value = '歌词已写入内嵌'
    emit('saved', track.value)
  } catch (e) {
    error.value = e instanceof Error ? e.message : '歌词写入失败'
  } finally {
    savingLyrics.value = false
  }
}

async function onFileChange(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file || !track.value) return
  uploading.value = true
  error.value = null
  try {
    await coverApi.upload(track.value.id, file)
    track.value = { ...track.value, has_cover: true }
    coverVersion.value += 1
    coverBroken.value = false
    message.value = '封面已替换'
    emit('saved', track.value)
  } catch (e) {
    error.value = e instanceof Error ? e.message : '封面写入失败'
  } finally {
    uploading.value = false
    input.value = ''
  }
}

async function removeCover(): Promise<void> {
  if (!track.value) return
  try {
    await coverApi.remove(track.value.id)
    coverVersion.value += 1
    track.value = { ...track.value, has_cover: false }
    coverBroken.value = true
    message.value = '内嵌封面已删除'
    emit('saved', track.value)
  } catch (e) {
    error.value = e instanceof Error ? e.message : '删除失败'
  }
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') close()
  else if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 's') {
    event.preventDefault()
    void save()
  }
}

watch(
  () => props.trackId,
  (id) => {
    if (id != null) void load(id)
  },
  { immediate: true },
)
</script>

<template>
  <div class="fixed inset-0 z-40 bg-black/50" aria-hidden="true" @click="close" />
  <aside
    class="fixed inset-y-0 right-0 z-50 flex w-full max-w-xl flex-col border-l border-border bg-surface"
    aria-label="曲目检查器"
    @keydown="onKeydown"
  >
    <header class="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
      <div class="min-w-0">
        <h2 class="truncate text-sm font-medium">{{ track?.title || track?.filename || '曲目详情' }}</h2>
        <p class="truncate font-mono text-[11px] text-muted">{{ track?.path }}</p>
      </div>
      <button
        type="button"
        class="grid h-8 w-8 place-items-center rounded-control text-muted hover:bg-surface-2 hover:text-text"
        aria-label="关闭"
        @click="close"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="h-4 w-4">
          <path d="M6 6l12 12M18 6 6 18" stroke-linecap="round" />
        </svg>
      </button>
    </header>

    <div class="flex-1 overflow-y-auto px-4 py-4">
      <p v-if="loading" class="py-10 text-center text-sm text-muted">加载中…</p>
      <template v-else-if="track">
        <p v-if="error" class="mb-3 rounded-control border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
          {{ error }}
        </p>
        <p
          v-if="message"
          class="mb-3 rounded-control border border-success/40 bg-success/10 px-3 py-2 text-sm text-success"
        >
          {{ message }}
        </p>

        <!-- 封面 -->
        <div class="flex gap-4">
          <div class="h-32 w-32 shrink-0 overflow-hidden rounded-card border border-border bg-surface-2">
            <img
              v-if="!coverBroken"
              :src="coverUrl"
              alt="封面"
              class="h-full w-full object-cover"
              @error="coverBroken = true"
            />
            <div v-else class="grid h-full w-full place-items-center text-muted" aria-hidden="true">
              <svg viewBox="0 0 64 64" fill="none" class="h-12 w-12">
                <circle cx="32" cy="32" r="26" stroke="currentColor" stroke-width="1.5" />
                <circle cx="32" cy="32" r="9" stroke="currentColor" stroke-width="1.5" />
                <circle cx="32" cy="32" r="2.5" fill="currentColor" />
              </svg>
            </div>
          </div>
          <div class="flex flex-col gap-2">
            <input ref="fileInput" type="file" accept="image/*" class="hidden" @change="onFileChange" />
            <button
              type="button"
              class="rounded-control bg-brand px-3 py-1.5 text-sm font-medium text-bg transition-colors hover:bg-brand-600 disabled:opacity-50"
              :disabled="uploading"
              @click="fileInput?.click()"
            >
              {{ uploading ? '上传中…' : '替换封面' }}
            </button>
            <button
              type="button"
              class="rounded-control border border-border px-3 py-1.5 text-sm text-muted transition-colors hover:border-danger/60 hover:text-danger"
              @click="removeCover"
            >
              删除内嵌封面
            </button>
            <RouterLink
              :to="{ name: 'scrape', query: { track: track.id } }"
              class="rounded-control border border-border px-3 py-1.5 text-center text-sm text-muted transition-colors hover:border-brand/60 hover:text-text"
            >
              在线刮削
            </RouterLink>
          </div>
        </div>

        <!-- 标签表单 -->
        <h3 class="mt-6 text-xs font-medium uppercase tracking-wide text-muted">标签</h3>
        <div class="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label v-for="tag in TAGS" :key="tag.key" class="flex flex-col gap-1 text-xs text-muted">
            {{ tag.label }}
            <input
              v-model="form[tag.key]"
              :class="tag.mono ? 'font-mono' : ''"
              type="text"
              class="rounded-control border border-border bg-bg px-2.5 py-1.5 text-sm text-text outline-none focus:border-brand"
            />
          </label>
        </div>

        <!-- 技术参数 -->
        <h3 class="mt-6 text-xs font-medium uppercase tracking-wide text-muted">技术参数</h3>
        <dl class="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 font-mono text-xs sm:grid-cols-3">
          <div><dt class="text-muted">格式</dt><dd>{{ track.format || '—' }}</dd></div>
          <div><dt class="text-muted">时长</dt><dd>{{ formatDuration(track.duration) }}</dd></div>
          <div><dt class="text-muted">码率</dt><dd>{{ formatBitrate(track.bitrate) }}</dd></div>
          <div><dt class="text-muted">采样率</dt><dd>{{ track.sample_rate ? `${track.sample_rate} Hz` : '—' }}</dd></div>
          <div><dt class="text-muted">声道</dt><dd>{{ track.channels ?? '—' }}</dd></div>
          <div><dt class="text-muted">位深</dt><dd>{{ track.bit_depth ? `${track.bit_depth} bit` : '—' }}</dd></div>
          <div><dt class="text-muted">大小</dt><dd>{{ formatSize(track.size) }}</dd></div>
          <div><dt class="text-muted">状态</dt><dd>{{ track.tag_status }}</dd></div>
          <div class="col-span-2 sm:col-span-1"><dt class="text-muted">修改时间</dt><dd>{{ formatDateTime(track.mtime) }}</dd></div>
        </dl>

        <!-- 歌词 -->
        <div class="mt-6 flex items-center justify-between">
          <h3 class="text-xs font-medium uppercase tracking-wide text-muted">
            歌词<span v-if="lyricsSource" class="ml-1 normal-case text-muted">（来源：{{ lyricsSource }}）</span>
          </h3>
          <button
            type="button"
            class="rounded-control border border-border px-2.5 py-1 text-xs text-muted transition-colors hover:border-brand/60 hover:text-text disabled:opacity-50"
            :disabled="savingLyrics"
            @click="saveLyrics"
          >
            {{ savingLyrics ? '写入中…' : '写入内嵌' }}
          </button>
        </div>
        <textarea
          v-model="lyrics"
          rows="6"
          placeholder="[00:01.00] 支持 LRC 时间轴"
          class="mt-2 w-full rounded-control border border-border bg-bg px-3 py-2 font-mono text-xs text-text outline-none focus:border-brand"
        />

        <!-- 最近操作 -->
        <h3 class="mt-6 text-xs font-medium uppercase tracking-wide text-muted">最近操作</h3>
        <ul v-if="logs.length" class="mt-2 divide-y divide-border/60 text-xs">
          <li v-for="log in logs" :key="log.id" class="flex items-center gap-2 py-1.5 text-muted">
            <span class="font-mono">{{ formatDateTime(log.created_at) }}</span>
            <span class="text-text">{{ log.action }}</span>
            <span v-if="log.field" class="font-mono">{{ log.field }}</span>
            <span class="truncate">{{ log.old_value ?? '∅' }} → {{ log.new_value ?? '∅' }}</span>
          </li>
        </ul>
        <p v-else class="mt-2 text-xs text-muted">暂无操作记录。</p>
      </template>
    </div>

    <footer class="flex items-center justify-end gap-2 border-t border-border px-4 py-3">
      <span class="mr-auto text-[11px] text-muted">⌘S 保存 · Esc 关闭</span>
      <button
        type="button"
        class="rounded-control border border-border px-3 py-1.5 text-sm text-muted transition-colors hover:text-text"
        @click="close"
      >
        关闭
      </button>
      <button
        type="button"
        class="rounded-control bg-brand px-4 py-1.5 text-sm font-medium text-bg transition-colors hover:bg-brand-600 disabled:opacity-50"
        :disabled="saving || loading"
        @click="save"
      >
        {{ saving ? '保存中…' : '保存' }}
      </button>
    </footer>
  </aside>
</template>
