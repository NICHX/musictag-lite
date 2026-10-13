<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

import CoverLightbox from '@/components/CoverLightbox.vue'
import SeekBar from '@/components/SeekBar.vue'
import { coverApi, filenameApi, logsApi, lyricsApi, scrapeApi, systemApi, trackApi } from '@/api/endpoints'
import type {
  OperationLog,
  ParseFilenameResponse,
  Track,
  WordLyricLine,
  WordLyricsTarget,
  WordLyricsTranslation,
} from '@/api/types'
import { extractAccent } from '@/lib/accent'
import { formatBitrate, formatDateTime, formatDuration, formatSize } from '@/lib/format'
import { useUiStore } from '@/stores/ui'

const props = defineProps<{ trackId: number | null }>()
const emit = defineEmits<{ close: []; saved: [track: Track] }>()

const ui = useUiStore()

/** 宽屏改为居中弹窗，窄屏保留右侧抽屉（宽屏下贴边抽屉既挡内容又费眼力）。 */
const wide = ref(false)
let mediaQuery: MediaQueryList | null = null
function syncWide(): void {
  wide.value = mediaQuery?.matches ?? false
}
onMounted(() => {
  mediaQuery = window.matchMedia('(min-width: 1024px)')
  syncWide()
  mediaQuery.addEventListener('change', syncWide)
})
onUnmounted(() => mediaQuery?.removeEventListener('change', syncWide))

/** 封面放大查看 */
const coverZoom = ref(false)

/** 歌词来源（内嵌 / 同名文件 / 逐字）——分开呈现，避免只显示「有无歌词」。 */
const lyricsSourceLabel = computed(() => {
  const value = track.value
  if (!value) return '—'
  const parts: string[] = []
  if (value.has_embedded_lyrics) parts.push('内嵌')
  if (value.has_lyrics_file) parts.push('同名文件')
  if (value.has_word_lyrics) parts.push('逐字')
  return parts.length ? parts.join(' + ') : '—'
})

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
const logs = ref<OperationLog[]>([])
const loading = ref(false)
const saving = ref(false)
const uploading = ref(false)
const message = ref<string | null>(null)
const error = ref<string | null>(null)
const coverVersion = ref(0)
const coverBroken = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const parsing = ref(false)
const parsed = ref<ParseFilenameResponse | null>(null)
const aiAvailable = ref(false)

// ---- 歌词：逐字（含译文）预览 + 写入 ----
const wordLyrics = ref<WordLyricLine[] | null>(null)
const wordSource = ref<string | null>(null)
const wordLoading = ref(false)
const savingWord = ref(false)
/** 最终歌词写入目标（内嵌 / 同名边车） */
const writeTargets = ref<'both-nilyric' | 'both-lrc' | 'embedded' | 'nilyric' | 'lrc'>(
  'both-nilyric',
)
/** 译文来源：默认「数据源自带」——不会调用 AI、不产生费用 */
const writeTranslation = ref<WordLyricsTranslation>('source')
const WRITE_TARGET_MAP: Record<string, WordLyricsTarget[]> = {
  'both-nilyric': ['embedded', 'nilyric'],
  'both-lrc': ['embedded', 'lrc'],
  embedded: ['embedded'],
  nilyric: ['nilyric'],
  lrc: ['lrc'],
}

let capabilitiesPromise: Promise<void> | null = null

// ---- 试听（F10）----
const audioEl = ref<HTMLAudioElement | null>(null)
const playing = ref(false)
const currentTime = ref(0)
const duration = ref(0)
const streamError = ref<string | null>(null)

const streamUrl = computed(() => (track.value ? `/api/tracks/${track.value.id}/stream` : ''))

function clock(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return '0:00'
  const total = Math.floor(seconds)
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
}

function togglePlay(): void {
  const element = audioEl.value
  if (!element) return
  if (element.paused) void element.play().catch(() => undefined)
  else element.pause()
}

function seekTo(value: number): void {
  currentTime.value = value
  if (audioEl.value) audioEl.value.currentTime = value
}

function resetPlayer(): void {
  playing.value = false
  currentTime.value = 0
  duration.value = 0
  streamError.value = null
}

function ensureCapabilities(): Promise<void> {
  if (!capabilitiesPromise) {
    capabilitiesPromise = systemApi
      .capabilities()
      .then((caps) => {
        aiAvailable.value = caps.ai
      })
      .catch(() => {
        aiAvailable.value = false
      })
  }
  return capabilitiesPromise
}

async function parseName(useAi: boolean): Promise<void> {
  if (!track.value) return
  parsing.value = true
  error.value = null
  message.value = null
  parsed.value = null
  try {
    parsed.value = await filenameApi.parse(track.value.id, useAi, false)
  } catch (e) {
    error.value = e instanceof Error ? e.message : '解析失败'
  } finally {
    parsing.value = false
  }
}

async function applyParsed(): Promise<void> {
  if (!track.value || !parsed.value) return
  const id = track.value.id
  parsing.value = true
  error.value = null
  try {
    const result = await filenameApi.parse(id, parsed.value.source === 'ai', true)
    parsed.value = null
    message.value = result.applied ? '已按文件名写入标签' : '无需修改'
    await load(id)
    if (track.value) emit('saved', track.value)
  } catch (e) {
    error.value = e instanceof Error ? e.message : '写入失败'
  } finally {
    parsing.value = false
  }
}

function fillForm(): void {
  if (!parsed.value) return
  for (const [key, value] of Object.entries(parsed.value.fields)) {
    if (value !== null && value !== undefined && key in form.value) {
      form.value[key] = String(value)
    }
  }
  parsed.value = null
  message.value = '已填入表单，确认后点保存'
}

const coverUrl = computed(() =>
  track.value ? `${coverApi.url(track.value.id)}?v=${coverVersion.value}` : '',
)

async function load(id: number): Promise<void> {
  loading.value = true
  error.value = null
  message.value = null
  coverBroken.value = false
  parsed.value = null
  wordLyrics.value = null
  wordSource.value = null
  resetPlayer()
  void ensureCapabilities()
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

/** 逐字歌词预览（只读，不落盘）。 */
async function toggleWordLyrics(): Promise<void> {
  if (wordLyrics.value) {
    wordLyrics.value = null
    wordSource.value = null
    return
  }
  if (!track.value) return
  wordLoading.value = true
  error.value = null
  try {
    const result = await scrapeApi.wordLyrics(track.value.id)
    wordSource.value = result.source
    if (result.available) {
      wordLyrics.value = result.lines
    } else if (result.word_sources?.length) {
      // 已启用支持逐字的源，只是这首歌没匹配到——避免误导用户去重复启用
      error.value = '未找到逐字歌词（已启用的歌词源未匹配到）'
    } else {
      error.value = '未找到逐字歌词（需在「设置 → 刮削源」启用支持逐字的源，如酷狗）'
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : '获取逐字歌词失败'
  } finally {
    wordLoading.value = false
  }
}

/** 抓取逐字歌词（含数据源 / AI 译文）并写入所选目标。 */
async function saveWordLyrics(): Promise<void> {
  if (!track.value) return
  savingWord.value = true
  error.value = null
  message.value = null
  try {
    const targets = WRITE_TARGET_MAP[writeTargets.value] ?? ['embedded', 'nilyric']
    const result = await lyricsApi.saveWordLyrics(
      track.value.id,
      targets,
      writeTranslation.value,
    )
    if (result.content) lyrics.value = result.content
    track.value = { ...track.value, has_lyrics: true, has_word_lyrics: true }
    message.value = `已写入逐字歌词${writeTranslation.value === 'none' ? '' : '（含译文）'}`
    emit('saved', track.value)
  } catch (e) {
    error.value = e instanceof Error ? e.message : '写入失败'
  } finally {
    savingWord.value = false
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
    class="fixed z-50 flex flex-col border-border bg-surface"
    :class="
      wide
        ? 'left-1/2 top-1/2 max-h-[88vh] w-[min(46rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-card border shadow-2xl'
        : 'inset-y-0 right-0 w-full max-w-xl border-l'
    "
    role="dialog"
    aria-modal="true"
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

    <div class="min-h-0 flex-1 overflow-y-auto px-4 py-4">
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
          <button
            type="button"
            class="h-32 w-32 shrink-0 overflow-hidden rounded-card border border-border bg-surface-2"
            :class="track.has_cover && !coverBroken ? 'cursor-zoom-in' : 'cursor-default'"
            :title="track.has_cover && !coverBroken ? '点击放大封面' : ''"
            :aria-label="track.has_cover && !coverBroken ? '放大封面' : '封面'"
            @click="track.has_cover && !coverBroken && (coverZoom = true)"
          >
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
          </button>
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

        <!-- 试听（HTTP Range 流式，无需 ffmpeg） -->
        <div class="mt-4 flex items-center gap-3 rounded-card border border-border bg-surface-2 px-3 py-2">
          <button
            type="button"
            class="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-brand text-bg transition-colors hover:bg-brand-600 disabled:opacity-50"
            :aria-label="playing ? '暂停' : '播放'"
            @click="togglePlay"
          >
            <svg v-if="!playing" viewBox="0 0 24 24" fill="currentColor" class="ml-0.5 h-4 w-4">
              <path d="M8 5.14v13.72L19 12 8 5.14Z" />
            </svg>
            <svg v-else viewBox="0 0 24 24" fill="currentColor" class="h-4 w-4">
              <path d="M7 5h4v14H7zM13 5h4v14h-4z" />
            </svg>
          </button>

          <span class="w-9 shrink-0 text-right font-mono text-[11px] text-muted">
            {{ clock(currentTime) }}
          </span>
          <SeekBar
            :current="currentTime"
            :duration="duration"
            :disabled="!duration"
            @seek="seekTo"
          />
          <span class="w-9 shrink-0 font-mono text-[11px] text-muted">
            {{ clock(duration) }}
          </span>

          <audio
            ref="audioEl"
            :src="streamUrl"
            preload="metadata"
            class="hidden"
            @loadedmetadata="duration = audioEl?.duration ?? 0"
            @timeupdate="currentTime = audioEl?.currentTime ?? 0"
            @play="playing = true"
            @pause="playing = false"
            @ended="playing = false"
            @error="streamError = '该格式无法在浏览器内直接播放（未安装 ffmpeg，属预期限制）'"
          />
        </div>
        <p v-if="streamError" class="mt-1.5 text-[11px] text-muted">{{ streamError }}</p>

        <!-- 文件名解析（仅手动触发；预览后确认再写入） -->
        <div class="mt-5 rounded-card border border-border bg-surface-2 px-3 py-3">
          <div class="flex flex-wrap items-center gap-2">
            <span class="mr-auto text-xs text-muted">从文件名推断标签</span>
            <button
              type="button"
              class="rounded-control border border-border px-2.5 py-1 text-xs text-muted transition-colors hover:border-brand/60 hover:text-text disabled:opacity-50"
              :disabled="parsing || loading"
              @click="parseName(false)"
            >
              {{ parsing ? '解析中…' : '按文件名解析' }}
            </button>
            <button
              v-if="aiAvailable"
              type="button"
              class="rounded-control border border-brand/50 px-2.5 py-1 text-xs text-brand transition-colors hover:bg-brand/10 disabled:opacity-50"
              :disabled="parsing || loading"
              @click="parseName(true)"
            >
              AI 解析
            </button>
          </div>

          <div v-if="parsed" class="mt-3 border-t border-border/60 pt-3 text-xs">
            <p class="text-muted">
              来源：{{ parsed.source === 'ai' ? 'AI' : '本地规则' }} · 置信度
              {{ Math.round(parsed.confidence * 100) }}%<span v-if="parsed.note"> · {{ parsed.note }}</span>
            </p>
            <ul v-if="parsed.diffs.length" class="mt-2 space-y-1">
              <li v-for="diff in parsed.diffs" :key="diff.field" class="flex items-center gap-2">
                <span class="w-14 shrink-0 font-mono text-muted">{{ diff.field }}</span>
                <span class="min-w-0 truncate text-muted">{{ diff.old_value ?? '∅' }}</span>
                <span class="shrink-0 text-muted">→</span>
                <span class="min-w-0 truncate text-text">{{ diff.new_value ?? '∅' }}</span>
              </li>
            </ul>
            <p v-else class="mt-2 text-muted">解析结果与现有标签一致，无需修改。</p>
            <div class="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                class="rounded-control bg-brand px-3 py-1 text-xs font-medium text-bg transition-colors hover:bg-brand-600 disabled:opacity-50"
                :disabled="parsing || !parsed.diffs.length"
                @click="applyParsed"
              >
                写入文件
              </button>
              <button
                type="button"
                class="rounded-control border border-border px-3 py-1 text-xs text-muted transition-colors hover:text-text disabled:opacity-50"
                :disabled="parsing || !parsed.diffs.length"
                @click="fillForm"
              >
                填入表单
              </button>
              <button
                type="button"
                class="rounded-control px-3 py-1 text-xs text-muted transition-colors hover:text-text"
                @click="parsed = null"
              >
                取消
              </button>
            </div>
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
          <div><dt class="text-muted">歌词</dt><dd>{{ lyricsSourceLabel }}</dd></div>
          <div class="col-span-2 sm:col-span-1"><dt class="text-muted">修改时间</dt><dd>{{ formatDateTime(track.mtime) }}</dd></div>
        </dl>

        <!-- 歌词：抓取逐字（含译文）→ 写入内嵌 / 同名边车 -->
        <div class="mt-6">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <h3 class="text-xs font-medium uppercase tracking-wide text-muted">歌词</h3>
            <div class="flex flex-wrap items-center gap-1.5">
              <button
                type="button"
                class="rounded-control border border-border px-2.5 py-1 text-xs text-muted transition-colors hover:border-brand/60 hover:text-text disabled:opacity-50"
                :disabled="wordLoading || loading"
                title="从数据源预览逐字歌词（只读，不写入）"
                @click="toggleWordLyrics"
              >
                {{ wordLoading ? '获取中…' : wordLyrics ? '收起预览' : '预览逐字' }}
              </button>
              <select
                v-model="writeTargets"
                class="rounded-control border border-border bg-bg px-2 py-1 text-xs text-text outline-none focus:border-brand disabled:opacity-50"
                :disabled="savingWord || loading"
                aria-label="歌词写入位置"
                title="写入位置"
              >
                <option value="both-nilyric">内嵌 + .nilyric</option>
                <option value="both-lrc">内嵌 + .lrc</option>
                <option value="embedded">仅内嵌</option>
                <option value="nilyric">仅 .nilyric</option>
                <option value="lrc">仅 .lrc</option>
              </select>
              <select
                v-model="writeTranslation"
                class="rounded-control border border-border bg-bg px-2 py-1 text-xs text-text outline-none focus:border-brand disabled:opacity-50"
                :disabled="savingWord || loading"
                aria-label="译文来源"
                title="译文来源：数据源自带免费；AI 生成可能产生费用，需显式选择"
              >
                <option value="none">无译文</option>
                <option value="source">译文·数据源</option>
                <option value="ai" :disabled="!aiAvailable">
                  译文·AI{{ aiAvailable ? '' : '（未配置）' }}
                </option>
              </select>
              <button
                type="button"
                class="rounded-control bg-brand px-3 py-1 text-xs font-medium text-bg transition-colors hover:bg-brand-600 disabled:opacity-50"
                :disabled="savingWord || loading"
                title="抓取逐字歌词并写入所选位置"
                @click="saveWordLyrics"
              >
                {{ savingWord ? '写入中…' : '抓取并写入' }}
              </button>
            </div>
          </div>

          <!-- 逐字 + 译文 预览（只读，不落盘） -->
          <div
            v-if="wordLyrics"
            class="mt-2 max-h-60 overflow-y-auto rounded-control border border-border bg-bg p-2.5 text-xs"
          >
            <p class="mb-1.5 text-[11px] text-muted">逐字预览 · 来源：{{ wordSource || '—' }}</p>
            <div v-for="(line, i) in wordLyrics" :key="i" class="flex gap-2 py-0.5">
              <span class="shrink-0 font-mono text-[10px] text-muted">{{ clock(line.start / 1000) }}</span>
              <span class="min-w-0 flex-1 leading-relaxed">
                <span
                  v-for="(word, j) in line.words"
                  :key="j"
                  class="rounded hover:bg-surface-2"
                  :title="`+${word.offset}ms · ${word.duration}ms`"
                  >{{ word.text }}</span
                >
              </span>
            </div>
          </div>

          <!-- 当前歌词（只读） -->
          <pre
            v-if="lyrics"
            class="mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-control border border-border bg-bg p-2.5 font-mono text-[11px] leading-relaxed text-muted"
          >{{ lyrics }}</pre>
        </div>

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

  <CoverLightbox
    v-if="coverZoom && track && track.has_cover"
    :track-id="track.id"
    :title="track.title"
    :artist="track.artist"
    @close="coverZoom = false"
  />
</template>
