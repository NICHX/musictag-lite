<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import CoverThumb from '@/components/CoverThumb.vue'
import EmptyState from '@/components/EmptyState.vue'
import SeekBar from '@/components/SeekBar.vue'
import { coverApi, providerApi, scrapeApi, systemApi, trackApi } from '@/api/endpoints'
import type { Candidate, Track } from '@/api/types'
import { formatDuration } from '@/lib/format'
import { PLAN_FIELDS, changedFields, fieldRows } from '@/lib/scrapePlan'
import { useTaskStore } from '@/stores/tasks'
import { useUiStore } from '@/stores/ui'

const route = useRoute()
const router = useRouter()
const tasks = useTaskStore()
const ui = useUiStore()

type QueueStatus = 'done' | 'skipped'
type ScopeKey = 'no-cover' | 'incomplete' | 'no-lyrics' | 'no-word' | 'all'

const SCOPES: { key: ScopeKey; label: string }[] = [
  { key: 'no-cover', label: '缺封面' },
  { key: 'incomplete', label: '缺标签' },
  { key: 'no-lyrics', label: '无歌词' },
  { key: 'no-word', label: '无逐字歌词' },
  { key: 'all', label: '全部曲目' },
]

// ---- 队列 ----
const queue = ref<number[]>([])
const tracksById = ref<Record<number, Track>>({})
const index = ref(0)
const status = ref<Record<number, QueueStatus>>({})
const building = ref(false)
const finished = ref(false)
const lastAppliedId = ref<number | null>(null)

const currentId = computed(() => queue.value[index.value] ?? null)
const currentTrack = computed<Track | null>(() =>
  currentId.value == null ? null : (tracksById.value[currentId.value] ?? null),
)
const doneCount = computed(() => queue.value.filter((id) => status.value[id] === 'done').length)
const processedCount = computed(() => queue.value.filter((id) => status.value[id]).length)
const progressPercent = computed(() =>
  queue.value.length ? Math.round((processedCount.value / queue.value.length) * 100) : 0,
)

// ---- 候选与写入计划 ----
const candidates = ref<Candidate[]>([])
const chosenUid = ref<string | null>(null)
/** 按曲目缓存候选结果：队列里来回切换或重访时无需再次请求。 */
const candidateCache = new Map<number, Candidate[]>()
const CACHE_LIMIT = 500
const providerNames = ref<Record<string, string>>({})
const searching = ref(false)
const fingerprinting = ref(false)
const fingerprintReady = ref(false)
const applying = ref(false)
const error = ref<string | null>(null)
const brokenCandidates = ref<Set<string>>(new Set())
const coverVersion = ref(0)

const selectedFields = ref<Record<string, boolean>>({})
const applyCover = ref(true)
const applyLyrics = ref(true)
/** 同时抓逐字歌词并写 .lrc + .nilyric 同名歌词文件 */
const writeLyricsFiles = ref(true)
const lastResult = ref<{
  title: string
  fields: string[]
  cover: boolean
  lyrics: boolean
  filesAttempted: boolean
  wordFound: boolean
  filesWritten: boolean
} | null>(null)
const notice = ref<string | null>(null)
const batching = ref(false)
/** 搜索条件编辑器：就地调整检索词（无需回资源库），也便于匹配已下架歌曲。 */
const queryOpen = ref(false)
const savingQuery = ref(false)
const queryForm = ref({ title: '', artist: '', album: '' })
/** 上一次写入的可撤销快照：标签旧值 + 是否需删除新写入的封面。 */
const lastUndo = ref<{
  trackId: number
  values: Record<string, unknown>
  removeCover: boolean
} | null>(null)

// ---- 试听（HTTP Range 流式，无需 ffmpeg）----
const audioEl = ref<HTMLAudioElement | null>(null)
const playing = ref(false)
const currentTime = ref(0)
const duration = ref(0)
const streamError = ref<string | null>(null)
const streamUrl = computed(() =>
  currentTrack.value ? `/api/tracks/${currentTrack.value.id}/stream` : '',
)

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

const chosenCandidate = computed<Candidate | null>(
  () => candidates.value.find((item) => scrapeApi.list(item) === chosenUid.value) ?? null,
)

/** 逐字段对比行（含未变化项，用于并排展示与勾选）。 */
const rows = computed(() =>
  fieldRows(
    currentTrack.value as unknown as Record<string, unknown> | null,
    chosenCandidate.value as unknown as Record<string, unknown> | null,
    false,
  ),
)
const pendingCount = computed(() => {
  const tags = rows.value.filter((row) => !row.blocked && selectedFields.value[row.key]).length
  const cover = applyCover.value && !!chosenCandidate.value?.cover_url ? 1 : 0
  const lyrics = applyLyrics.value ? 1 : 0
  return tags + cover + lyrics
})
const resultSummary = computed(() => {
  const result = lastResult.value
  if (!result) return ''
  const tagPart = result.fields.length
    ? `标签 ${result.fields.length} 项（${result.fields.map(fieldLabel).join('、')}）`
    : '标签无改动'
  const flags = [`封面 ${result.cover ? '✓' : '×'}`, `歌词 ${result.lyrics ? '✓' : '×'}`]
  if (result.filesAttempted) {
    flags.push(`逐字 ${result.wordFound ? '✓' : '×'}`, `歌词文件 ${result.filesWritten ? '✓' : '×'}`)
  }
  return [tagPart, ...flags].join(' · ')
})

function fieldLabel(key: string): string {
  return PLAN_FIELDS.find((item) => item.key === key)?.label ?? key
}

function scoreTone(score: number): string {
  if (score >= 0.8) return 'text-success'
  if (score >= 0.6) return 'text-text'
  return 'text-muted'
}

function candidateFields(candidate: Candidate) {
  return changedFields(
    currentTrack.value as unknown as Record<string, unknown> | null,
    candidate as unknown as Record<string, unknown>,
  )
}

// ---- 队列构建 ----
async function mapLimit<T, R>(items: T[], limit: number, fn: (item: T) => Promise<R>): Promise<R[]> {
  const results: R[] = []
  for (let start = 0; start < items.length; start += limit) {
    results.push(...(await Promise.all(items.slice(start, start + limit).map(fn))))
  }
  return results
}

async function loadTracks(ids: number[]): Promise<void> {
  const missing = ids.filter((id) => !tracksById.value[id])
  if (!missing.length) return
  const loaded = await mapLimit(missing, 8, (id) => trackApi.get(id).catch(() => null))
  const next = { ...tracksById.value }
  for (const track of loaded) if (track) next[track.id] = track
  tracksById.value = next
}

async function setQueue(ids: number[]): Promise<void> {
  queue.value = [...new Set(ids)]
  index.value = 0
  status.value = {}
  finished.value = false
  candidates.value = []
  chosenUid.value = null
  lastResult.value = null
  error.value = null
  await loadTracks(queue.value)
  if (queue.value.length) await goTo(0)
}

async function buildQueue(scope: ScopeKey): Promise<void> {
  building.value = true
  error.value = null
  notice.value = null
  try {
    const filter = {
      has_cover: scope === 'no-cover' ? false : undefined,
      has_lyrics: scope === 'no-lyrics' ? false : undefined,
      has_word_lyrics: scope === 'no-word' ? false : undefined,
      tag_status: scope === 'incomplete' ? 'MISSING_TAGS' : undefined,
    }
    // 逐页拉取全部符合条件的曲目（单页接口上限 1000），避免只取到前 200 首
    const collected: Track[] = []
    const MAX_TRACKS = 5000
    let pageNo = 1
    while (collected.length < MAX_TRACKS) {
      const page = await trackApi.list({ ...filter, page: pageNo, page_size: 1000 })
      collected.push(...page.items)
      if (pageNo >= page.pages || !page.items.length) break
      pageNo += 1
    }
    if (collected.length >= MAX_TRACKS) {
      notice.value = `曲目较多，队列仅取前 ${MAX_TRACKS} 首（可先用筛选缩小范围）`
    }
    const next = { ...tracksById.value }
    for (const track of collected) next[track.id] = track
    tracksById.value = next
    await setQueue(collected.map((track) => track.id))
  } catch (e) {
    error.value = e instanceof Error ? e.message : '加载失败'
  } finally {
    building.value = false
  }
}

function resetQueue(): void {
  queue.value = []
  tracksById.value = {}
  status.value = {}
  finished.value = false
  lastAppliedId.value = null
  candidates.value = []
  chosenUid.value = null
  lastResult.value = null
  void router.replace({ name: 'scrape' })
}

/** 解析路由中的队列来源：`?ids=1,2,3` 或 `?track=9`。 */
function parseIdList(raw: unknown): number[] {
  return String(raw ?? '')
    .split(',')
    .map((value) => Number(value.trim()))
    .filter((value) => Number.isInteger(value) && value > 0)
}

// ---- 导航 ----
async function goTo(target: number, keepResult = false): Promise<void> {
  if (target < 0 || target >= queue.value.length) return
  index.value = target
  candidates.value = []
  chosenUid.value = null
  selectedFields.value = {}
  finished.value = false
  if (!keepResult) lastResult.value = null
  resetPlayer()
  syncQueryForm()
  await search()
}

function goPrev(): void {
  if (index.value > 0) void goTo(index.value - 1)
}

function goNext(): void {
  if (index.value < queue.value.length - 1) void goTo(index.value + 1)
}

function advance(): void {
  const next = nextUnprocessed(index.value)
  if (next < 0) {
    finished.value = true
    return
  }
  void goTo(next, true)
}

function skip(): void {
  const id = currentId.value
  if (id == null) return
  status.value = { ...status.value, [id]: 'skipped' }
  lastResult.value = null
  advance()
}

function backToLibrary(): void {
  const id = lastAppliedId.value ?? currentId.value
  void router.push({ name: 'library', query: id ? { track: String(id) } : {} })
}

// ---- 搜索 / 应用 ----
function resetPlan(): void {
  const next: Record<string, boolean> = {}
  for (const row of rows.value) next[row.key] = row.changed && !row.blocked
  selectedFields.value = next
  applyCover.value = !!chosenCandidate.value?.cover_url && !currentTrack.value?.has_cover
  applyLyrics.value = true
}

watch(chosenCandidate, () => resetPlan())

async function search(force = false): Promise<void> {
  const id = currentId.value
  if (id == null) return
  if (!force) {
    const cached = candidateCache.get(id)
    if (cached) {
      candidates.value = cached
      chosenUid.value = cached.length ? scrapeApi.list(cached[0]) : null
      void prefetchNext()
      return
    }
  }
  const result = await fetchCandidates({ track_id: id, limit: 10 })
  if (result) storeCandidates(id, result)
  void prefetchNext()
}

/** 发起一次候选检索并落到界面；失败返回 null。 */
async function fetchCandidates(body: Parameters<typeof scrapeApi.search>[0]): Promise<Candidate[] | null> {
  searching.value = true
  error.value = null
  candidates.value = []
  chosenUid.value = null
  try {
    const response = await scrapeApi.search(body)
    candidates.value = response.candidates
    if (response.candidates.length) chosenUid.value = scrapeApi.list(response.candidates[0])
    return response.candidates
  } catch (e) {
    error.value = e instanceof Error ? e.message : '搜索失败'
    return null
  } finally {
    searching.value = false
  }
}

/** 就地调整搜索条件：用编辑后的「标题/艺术家/专辑」手动检索（不走缓存）。 */
async function searchCustom(): Promise<void> {
  const query = {
    title: queryForm.value.title.trim() || undefined,
    artist: queryForm.value.artist.trim() || undefined,
    album: queryForm.value.album.trim() || undefined,
  }
  if (!query.title && !query.artist && !query.album) {
    error.value = '请至少填写标题或艺术家'
    return
  }
  await fetchCandidates({ query, limit: 10 })
}

/** 把编辑后的标签写入文件（修正难匹配曲目的元数据）。 */
async function saveQueryTags(): Promise<void> {
  const id = currentId.value
  if (id == null) return
  savingQuery.value = true
  error.value = null
  try {
    const updated = await trackApi.update(id, {
      title: queryForm.value.title.trim() || null,
      artist: queryForm.value.artist.trim() || null,
      album: queryForm.value.album.trim() || null,
    })
    tracksById.value = { ...tracksById.value, [id]: updated }
    notice.value = '已写入标签，可继续「用这些条件搜索」'
  } catch (e) {
    error.value = e instanceof Error ? e.message : '写入标签失败'
  } finally {
    savingQuery.value = false
  }
}

/** 用当前曲目的标签回填搜索条件。 */
function syncQueryForm(): void {
  const track = currentTrack.value
  queryForm.value = {
    title: track?.title ?? '',
    artist: track?.artist ?? '',
    album: track?.album ?? '',
  }
}

function storeCandidates(id: number, list: Candidate[]): void {
  if (candidateCache.size >= CACHE_LIMIT) candidateCache.clear()
  candidateCache.set(id, list)
}

/** 从 ``from`` 起找下一首尚未处理（未写入/跳过）的队列下标。 */
function nextUnprocessed(from: number): number {
  const total = queue.value.length
  for (let step = 1; step <= total; step++) {
    const i = (from + step) % total
    if (!status.value[queue.value[i]]) return i
  }
  return -1
}

/** 后台预取下一首的候选，切过去时即可瞬时展示（失败的预取会被正式搜索覆盖）。 */
async function prefetchNext(): Promise<void> {
  const i = nextUnprocessed(index.value)
  if (i < 0) return
  const id = queue.value[i]
  if (candidateCache.has(id)) return
  try {
    const response = await scrapeApi.search({ track_id: id, limit: 10 })
    storeCandidates(id, response.candidates)
  } catch {
    /* 预取失败静默忽略 */
  }
}

async function fingerprint(): Promise<void> {
  const id = currentId.value
  if (id == null) return
  fingerprinting.value = true
  error.value = null
  candidates.value = []
  chosenUid.value = null
  try {
    const response = await scrapeApi.fingerprint(id)
    candidates.value = response.candidates
    if (response.candidates.length) chosenUid.value = scrapeApi.list(response.candidates[0])
    else error.value = '指纹未识别出匹配结果'
  } catch (e) {
    error.value = e instanceof Error ? e.message : '指纹识别失败'
  } finally {
    fingerprinting.value = false
  }
}

async function applyCurrent(advanceToNext: boolean): Promise<void> {
  const track = currentTrack.value
  const picked = chosenCandidate.value
  if (!track || !picked) return
  applying.value = true
  error.value = null
  try {
    const fields = rows.value
      .filter((row) => !row.blocked && selectedFields.value[row.key])
      .map((row) => row.key)
    const result = await scrapeApi.apply({
      track_id: track.id,
      candidate_ids: [scrapeApi.list(picked)],
      candidates: [picked],
      only_missing: false,
      fields,
      apply_cover: applyCover.value && !!picked.cover_url,
      apply_lyrics: applyLyrics.value,
      write_lyrics_files: writeLyricsFiles.value,
    })
    // 记录可撤销快照（标签旧值 + 是否需删除「本次新增」的封面）
    const previous: Record<string, unknown> = {}
    for (const diff of result.diffs) previous[diff.field] = diff.old_value
    const removeCover = result.cover_applied && !track.has_cover
    lastUndo.value =
      Object.keys(previous).length || removeCover
        ? { trackId: track.id, values: previous, removeCover }
        : null
    // 本地改写即可（标签字段来自 diffs，封面/歌词来自回执），省去一次往返
    const refreshed: Track = { ...track }
    const patch = refreshed as unknown as Record<string, unknown>
    for (const diff of result.diffs) patch[diff.field] = diff.new_value
    if (result.cover_applied) refreshed.has_cover = true
    if (result.lyrics_applied) refreshed.has_lyrics = true
    tracksById.value = { ...tracksById.value, [track.id]: refreshed }
    coverVersion.value += 1
    status.value = { ...status.value, [track.id]: 'done' }
    lastAppliedId.value = track.id
    lastResult.value = {
      title: refreshed.title || track.filename,
      fields: result.applied_fields,
      cover: result.cover_applied,
      lyrics: result.lyrics_applied,
      filesAttempted: writeLyricsFiles.value,
      wordFound: result.word_found,
      filesWritten: result.lyrics_files_written,
    }
    syncQueryForm()
    if (advanceToNext) advance()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '应用失败'
  } finally {
    applying.value = false
  }
}

/** 一键批量匹配：对整条队列取最高分候选，达阈值自动应用（仅补空值 + 封面）。 */
async function batchMatch(): Promise<void> {
  if (!queue.value.length || batching.value) return
  batching.value = true
  error.value = null
  notice.value = null
  try {
    const task = await scrapeApi.jobs({
      ids: queue.value,
      only_missing: true,
      apply_lyrics: applyLyrics.value,
      write_lyrics_files: writeLyricsFiles.value,
    })
    notice.value = `已启动批量匹配（任务 #${task.task_id}），进度与逐条结果见任务中心`
    tasks.connect()
    void tasks.refresh()
    ui.toggleTaskCenter(true)
  } catch (e) {
    error.value = e instanceof Error ? e.message : '启动批量匹配失败'
  } finally {
    batching.value = false
  }
}

/** 撤销上一次写入：回滚标签字段；若封面是本次新增的则删除。 */
async function undoLast(): Promise<void> {
  const undo = lastUndo.value
  if (!undo) return
  applying.value = true
  error.value = null
  notice.value = null
  try {
    if (Object.keys(undo.values).length) {
      await trackApi.update(undo.trackId, undo.values)
    }
    if (undo.removeCover) {
      await coverApi.remove(undo.trackId)
    }
    const refreshed = await trackApi.get(undo.trackId).catch(() => null)
    const nextStatus = { ...status.value }
    delete nextStatus[undo.trackId]
    status.value = nextStatus
    if (refreshed) tracksById.value = { ...tracksById.value, [undo.trackId]: refreshed }
    coverVersion.value += 1
    lastUndo.value = null
    lastResult.value = null
    notice.value = '已撤销上一次写入'
    const target = queue.value.indexOf(undo.trackId)
    if (target >= 0) await goTo(target)
  } catch (e) {
    error.value = e instanceof Error ? e.message : '撤销失败'
  } finally {
    applying.value = false
  }
}

// ---- 逐字段勾选 ----
function toggleField(key: string): void {
  selectedFields.value = { ...selectedFields.value, [key]: !selectedFields.value[key] }
}

function selectAllFields(): void {
  const next: Record<string, boolean> = {}
  for (const row of rows.value) next[row.key] = !row.blocked
  selectedFields.value = next
}

function selectEmptyFields(): void {
  const next: Record<string, boolean> = {}
  for (const row of rows.value) next[row.key] = !row.blocked && row.from === '∅'
  selectedFields.value = next
}

function clearFields(): void {
  const next: Record<string, boolean> = {}
  for (const row of rows.value) next[row.key] = false
  selectedFields.value = next
}

// ---- 键盘流 ----
function moveSelection(delta: number): void {
  if (!candidates.value.length) return
  const current = candidates.value.findIndex((item) => scrapeApi.list(item) === chosenUid.value)
  const next = Math.min(candidates.value.length - 1, Math.max(0, (current < 0 ? 0 : current) + delta))
  chosenUid.value = scrapeApi.list(candidates.value[next])
}

function onKeydown(event: KeyboardEvent): void {
  const target = event.target as HTMLElement | null
  const tag = target?.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target?.isContentEditable) return
  if (event.metaKey || event.ctrlKey || event.altKey) return
  switch (event.key) {
    case 'ArrowUp':
    case 'k':
      event.preventDefault()
      moveSelection(-1)
      break
    case 'ArrowDown':
    case 'j':
      event.preventDefault()
      moveSelection(1)
      break
    case 'ArrowLeft':
    case 'h':
      event.preventDefault()
      goPrev()
      break
    case 'ArrowRight':
    case 'l':
      event.preventDefault()
      goNext()
      break
    case 'Enter':
      event.preventDefault()
      void applyCurrent(true)
      break
    case 's':
      if (!applying.value) skip()
      break
    case 'r':
      void search(true)
      break
    default:
      if (/^[1-9]$/.test(event.key)) {
        const picked = candidates.value[Number(event.key) - 1]
        if (picked) chosenUid.value = scrapeApi.list(picked)
      }
  }
}

async function applyFromRoute(): Promise<void> {
  const ids = parseIdList(route.query.ids)
  const single = Number(route.query.track)
  if (ids.length) await setQueue(ids)
  else if (Number.isInteger(single) && single > 0) await setQueue([single])
}

// 同页内再次从资源库「批量匹配」进入时，重建队列
watch(
  () => [route.query.ids, route.query.track] as const,
  ([ids, track]) => {
    const list = parseIdList(ids)
    if (list.length) void setQueue(list)
    else if (Number(track) > 0) void setQueue([Number(track)])
  },
)

onMounted(async () => {
  window.addEventListener('keydown', onKeydown)
  const [providers, caps] = await Promise.all([
    providerApi.list().catch(() => []),
    systemApi.capabilities().catch(() => null),
  ])
  providerNames.value = Object.fromEntries(providers.map((item) => [item.key, item.name]))
  fingerprintReady.value = caps?.acoustid ?? false
  await applyFromRoute()
})

onUnmounted(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <section class="mx-auto flex h-full w-full max-w-[110rem] flex-col px-4 py-5 md:px-6">
    <header class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <button
          type="button"
          class="mb-2 inline-flex items-center gap-1.5 text-xs text-muted transition-colors hover:text-text"
          @click="backToLibrary"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" class="h-3.5 w-3.5">
            <path d="M14 6l-6 6 6 6" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
          返回资源库
        </button>
        <h1 class="font-display text-2xl font-semibold tracking-tight">匹配工作台</h1>
        <p class="mt-1 text-sm text-muted">
          逐首确认候选并勾选要写入的字段 · 开放数据源（MusicBrainz · Cover Art Archive · LRCLIB）
        </p>
      </div>

      <div class="flex flex-wrap items-center gap-2">
        <span v-if="queue.length" class="rounded-full border border-border px-2.5 py-1 text-xs text-muted">
          已完成 {{ doneCount }} / {{ queue.length }}
        </span>
        <button
          v-if="queue.length"
          type="button"
          class="rounded-control bg-brand px-3 py-1.5 text-sm font-medium text-bg transition-colors hover:bg-brand-600 disabled:opacity-50"
          :disabled="batching"
          title="对整条队列取最高分候选，达阈值自动应用（仅补空值 + 封面 + 歌词/同名歌词文件）"
          @click="batchMatch"
        >
          {{ batching ? '启动中…' : '一键批量匹配' }}
        </button>
        <button
          v-if="queue.length"
          type="button"
          class="rounded-control border border-border px-3 py-1.5 text-sm text-muted transition-colors hover:text-text"
          @click="resetQueue"
        >
          重新选择范围
        </button>
      </div>
    </header>

    <p
      v-if="queue.length"
      class="mt-3 hidden text-[11px] text-muted md:block"
    >
      快捷键：↑↓ 选候选 · ←→ 换曲目 · 数字键直选 · Enter 应用并下一首 · S 跳过 · R 重搜
    </p>

    <p
      v-if="error"
      class="mt-3 rounded-control border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger"
    >
      {{ error }}
    </p>

    <p
      v-if="notice"
      class="mt-3 rounded-control border border-info/40 bg-info/10 px-3 py-2 text-sm text-info"
    >
      {{ notice }}
    </p>

    <!-- 写入回执 -->
    <div
      v-if="lastResult"
      aria-live="polite"
      class="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-control border border-success/40 bg-success/5 px-3 py-2 text-sm"
    >
      <span class="shrink-0 rounded-full bg-success/15 px-2 py-0.5 text-[11px] text-success">已写入</span>
      <span class="min-w-0 max-w-[16rem] truncate">{{ lastResult.title }}</span>
      <span class="text-xs text-muted">{{ resultSummary }}</span>
      <div class="ml-auto flex shrink-0 items-center gap-2">
        <button
          v-if="lastUndo"
          type="button"
          class="rounded-control border border-border px-2 py-1 text-xs text-muted transition-colors hover:border-warning/60 hover:text-warning disabled:opacity-50"
          :disabled="applying"
          title="回滚标签字段；若封面为本次新增则一并删除"
          @click="undoLast"
        >
          撤销
        </button>
        <button
          type="button"
          class="rounded-control px-2 py-1 text-xs text-muted transition-colors hover:text-text"
          @click="lastResult = null"
        >
          关闭
        </button>
      </div>
    </div>

    <!-- 队列完成 -->
    <div v-if="finished" class="mt-4 rounded-card border border-brand/40 bg-brand/5 p-5">
      <h2 class="font-display text-lg font-medium">队列已完成</h2>
      <p class="mt-1 text-sm text-muted">
        共处理 {{ processedCount }} 首，写入 {{ doneCount }} 首。
      </p>
      <div class="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          class="rounded-control bg-brand px-3.5 py-1.5 text-sm font-medium text-bg transition-colors hover:bg-brand-600"
          @click="backToLibrary"
        >
          返回资源库
        </button>
        <button
          type="button"
          class="rounded-control border border-border px-3.5 py-1.5 text-sm text-muted transition-colors hover:text-text"
          @click="resetQueue"
        >
          再选一批
        </button>
      </div>
    </div>

    <!-- 空队列：选择范围 -->
    <div v-if="!queue.length" class="mt-6 rounded-card border border-border bg-surface p-6">
      <h2 class="font-display text-lg font-medium">选择要匹配的曲目</h2>
      <p class="mt-1 text-sm text-muted">
        在资源库多选曲目后点「批量匹配」，或按下面的范围一键生成队列。
      </p>
      <div class="mt-4 flex flex-wrap gap-2">
        <button
          v-for="scope in SCOPES"
          :key="scope.key"
          type="button"
          class="rounded-control border border-border px-3.5 py-1.5 text-sm text-muted transition-colors hover:border-brand/50 hover:text-text disabled:opacity-50"
          :disabled="building"
          @click="buildQueue(scope.key)"
        >
          {{ scope.label }}
        </button>
      </div>
      <p v-if="building" class="mt-4 text-sm text-muted">加载中…</p>
      <EmptyState
        v-else
        title="还没有待匹配的曲目"
        description="也可以先从资源库选中若干曲目，再点底部的「批量匹配」。"
      />
    </div>

    <!-- 工作台：队列 / 候选 / 匹配详情；lg 起三列并占满一屏（内部各自滚动） -->
    <div
      v-else
      class="mt-5 grid gap-5 lg:min-h-0 lg:flex-1 lg:grid-cols-[minmax(15rem,18rem)_minmax(0,1fr)_minmax(17rem,21rem)]"
    >
      <!-- 队列 -->
      <aside class="flex min-h-0 flex-col gap-3 rounded-card border border-border bg-surface p-3">
        <div class="flex shrink-0 items-center justify-between">
          <h2 class="text-xs font-medium uppercase tracking-wide text-muted">队列</h2>
          <span class="font-mono text-[11px] text-muted">{{ processedCount }}/{{ queue.length }}</span>
        </div>
        <div class="h-1 shrink-0 overflow-hidden rounded-full bg-border">
          <div
            class="h-full rounded-full bg-brand transition-all duration-200"
            :style="{ width: `${progressPercent}%` }"
          />
        </div>
        <ol class="flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto overscroll-contain">
          <li v-for="(id, i) in queue" :key="id">
            <button
              type="button"
              class="flex w-full items-center gap-2 rounded-control border-l-2 px-2 py-1.5 text-left transition-colors"
              :class="i === index ? 'border-brand bg-brand/5' : 'border-transparent hover:bg-surface-2'"
              @click="goTo(i)"
            >
              <span class="h-8 w-8 shrink-0 overflow-hidden rounded-control border border-border">
                <CoverThumb
                  :track-id="id"
                  :has-cover="tracksById[id]?.has_cover ?? false"
                  :version="coverVersion"
                  rounded="rounded-none"
                />
              </span>
              <span class="min-w-0 flex-1">
                <span
                  class="block truncate text-xs"
                  :title="tracksById[id]?.filename"
                >
                  {{ tracksById[id]?.title || tracksById[id]?.filename || `#${id}` }}
                </span>
                <span
                  v-if="tracksById[id]?.title"
                  class="mt-0.5 line-clamp-2 block break-all font-mono text-[10px] leading-snug text-muted"
                  :title="`${tracksById[id]?.artist || '未知艺术家'} · ${tracksById[id]?.filename}`"
                >
                  {{ tracksById[id]?.filename }}
                </span>
                <span v-else class="mt-0.5 block truncate text-[11px] text-muted">
                  {{ tracksById[id]?.artist || '未知艺术家' }}
                </span>
              </span>
              <span v-if="status[id] === 'done'" class="shrink-0 text-[11px] text-success">已写入</span>
              <span v-else-if="status[id] === 'skipped'" class="shrink-0 text-[11px] text-muted">已跳过</span>
            </button>
          </li>
        </ol>
      </aside>

        <!-- 候选 -->
        <div class="flex min-h-0 flex-col rounded-card border border-border bg-surface p-4">
          <div class="flex shrink-0 flex-wrap items-center justify-between gap-2">
            <h2 class="text-xs font-medium uppercase tracking-wide text-muted">
              候选 <span class="font-mono normal-case">（{{ candidates.length }}）</span>
            </h2>
            <div class="flex items-center gap-2">
              <button
                v-if="fingerprintReady"
                type="button"
                class="rounded-control border border-border px-2.5 py-1 text-xs text-muted transition-colors hover:text-text disabled:opacity-50"
                :disabled="fingerprinting || searching || currentId == null"
                title="用音频指纹识别（AcoustID）"
                @click="fingerprint"
              >
                {{ fingerprinting ? '识别中…' : '指纹识别' }}
              </button>
              <button
                type="button"
                class="rounded-control border px-2.5 py-1 text-xs transition-colors"
                :class="queryOpen ? 'border-brand/60 text-brand' : 'border-border text-muted hover:text-text'"
                title="就地调整检索词（无需回资源库），也便于匹配已下架歌曲"
                @click="queryOpen = !queryOpen"
              >
                搜索条件
              </button>
              <button
                type="button"
                class="rounded-control border border-border px-2.5 py-1 text-xs text-muted transition-colors hover:text-text disabled:opacity-50"
                :disabled="searching || currentId == null"
                @click="search(true)"
              >
                {{ searching ? '搜索中…' : '重新搜索' }}
              </button>
            </div>
          </div>

          <!-- 搜索条件：就地编辑 → 重新检索 / 写入标签 -->
          <div v-if="queryOpen" class="mt-3 shrink-0 rounded-control border border-border bg-bg p-2.5">
            <div class="flex flex-wrap items-center gap-2">
              <input
                v-model="queryForm.title"
                placeholder="标题"
                class="min-w-32 flex-1 rounded-control border border-border bg-surface px-2 py-1 text-xs text-text outline-none focus:border-brand"
                @keyup.enter="searchCustom"
              />
              <input
                v-model="queryForm.artist"
                placeholder="艺术家"
                class="min-w-24 flex-1 rounded-control border border-border bg-surface px-2 py-1 text-xs text-text outline-none focus:border-brand"
                @keyup.enter="searchCustom"
              />
              <input
                v-model="queryForm.album"
                placeholder="专辑"
                class="min-w-24 flex-1 rounded-control border border-border bg-surface px-2 py-1 text-xs text-text outline-none focus:border-brand"
                @keyup.enter="searchCustom"
              />
            </div>
            <div class="mt-2 flex flex-wrap items-center gap-2">
              <button
                type="button"
                class="rounded-control bg-brand px-3 py-1 text-xs font-medium text-bg transition-colors hover:bg-brand-600 disabled:opacity-50"
                :disabled="searching"
                @click="searchCustom"
              >
                用这些条件搜索
              </button>
              <button
                type="button"
                class="rounded-control border border-border px-3 py-1 text-xs text-muted transition-colors hover:text-text disabled:opacity-50"
                :disabled="savingQuery"
                title="把上面的标题/艺术家/专辑写入文件标签"
                @click="saveQueryTags"
              >
                {{ savingQuery ? '写入中…' : '写入标签' }}
              </button>
              <span class="text-[11px] text-muted">搜不到（如已下架）时，改标题或艺术家后再搜</span>
            </div>
          </div>

          <p v-if="searching" class="m-auto py-10 text-center text-sm text-muted">搜索中…</p>

          <EmptyState
            v-else-if="!candidates.length"
            class="m-auto"
            title="暂无候选"
            description="换个数据源或手动重新搜索；源可在「设置 → 刮削源」启用。"
          />

          <ul
            v-else
            class="mt-3 flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto overscroll-contain pr-1"
          >
            <li v-for="(candidate, i) in candidates" :key="scrapeApi.list(candidate)">
              <button
                type="button"
                class="flex w-full items-center gap-3 rounded-card border p-2.5 text-left transition-colors"
                :class="
                  chosenUid === scrapeApi.list(candidate)
                    ? 'border-brand bg-brand/5'
                    : 'border-border hover:border-brand/50 hover:bg-surface-2'
                "
                :aria-pressed="chosenUid === scrapeApi.list(candidate)"
                @click="chosenUid = scrapeApi.list(candidate)"
              >
                <span
                  class="relative h-14 w-14 shrink-0 overflow-hidden rounded-control border border-border bg-surface-2"
                >
                  <img
                    v-if="candidate.cover_url && !brokenCandidates.has(scrapeApi.list(candidate))"
                    :src="candidate.cover_url"
                    alt=""
                    loading="lazy"
                    class="h-full w-full object-cover"
                    @error="brokenCandidates = new Set(brokenCandidates).add(scrapeApi.list(candidate))"
                  />
                  <span v-else class="grid h-full w-full place-items-center text-muted" aria-hidden="true">
                    <svg viewBox="0 0 64 64" fill="none" class="h-6 w-6">
                      <circle cx="32" cy="32" r="26" stroke="currentColor" stroke-width="1.5" />
                      <circle cx="32" cy="32" r="9" stroke="currentColor" stroke-width="1.5" />
                      <circle cx="32" cy="32" r="2.5" fill="currentColor" />
                    </svg>
                  </span>
                  <span
                    v-if="i < 9"
                    class="absolute left-0 top-0 grid h-4 w-4 place-items-center rounded-br-control bg-black/60 font-mono text-[10px] text-white"
                  >
                    {{ i + 1 }}
                  </span>
                </span>

                <span class="min-w-0 flex-1">
                  <span class="flex items-center gap-2">
                    <span class="min-w-0 flex-1 truncate text-sm font-medium">
                      {{ candidate.title || '（无标题）' }}
                    </span>
                    <span v-if="i === 0" class="shrink-0 rounded-full bg-brand/15 px-1.5 py-0.5 text-[10px] text-brand">
                      最佳
                    </span>
                    <span class="shrink-0 font-mono text-sm font-medium" :class="scoreTone(candidate.score)">
                      {{ Math.round(candidate.score * 100) }}
                    </span>
                  </span>

                  <span class="mt-0.5 block truncate text-xs text-muted">
                    {{ candidate.artist || '未知艺术家' }}
                    <template v-if="candidate.album"> · {{ candidate.album }}</template>
                    <template v-if="candidate.year"> · {{ candidate.year }}</template>
                  </span>

                  <span class="mt-1.5 flex flex-wrap items-center gap-1.5">
                    <span
                      v-if="!candidateFields(candidate).length"
                      class="rounded-full border border-border px-1.5 py-0.5 text-[10px] text-muted"
                    >
                      标签一致
                    </span>
                    <span
                      v-for="diff in candidateFields(candidate)"
                      :key="diff.key"
                      class="rounded-full border border-success/40 px-1.5 py-0.5 text-[10px] text-success"
                    >
                      {{ fieldLabel(diff.key) }} ≠
                    </span>
                    <span class="ml-auto text-[10px] text-muted">
                      {{ providerNames[candidate.provider] ?? candidate.provider }}
                    </span>
                  </span>
                </span>
              </button>
            </li>
          </ul>
        </div>

        <!-- 匹配详情：当前 → 候选 对比 + 逐字段写入 + 操作 -->
        <aside
          class="flex min-h-0 flex-col gap-3 overflow-y-auto rounded-card border border-border bg-surface p-4"
        >
          <h2 class="text-xs font-medium uppercase tracking-wide text-muted">匹配详情</h2>

          <p v-if="!chosenCandidate" class="text-xs text-muted">
            在左侧选择一个候选，这里会列出将写入的内容。
          </p>

          <template v-else>
            <!-- 封面对比 -->
            <div class="flex gap-3">
              <div class="min-w-0 flex-1">
                <span class="block h-16 w-16 overflow-hidden rounded-control border border-border">
                  <CoverThumb
                    :track-id="currentTrack?.id ?? 0"
                    :has-cover="currentTrack?.has_cover ?? false"
                    :version="coverVersion"
                    rounded="rounded-none"
                  />
                </span>
                <span class="mt-1 block text-[10px] text-muted">当前</span>
              </div>
              <span class="mt-5 shrink-0 text-muted">→</span>
              <div class="min-w-0 flex-1">
                <span class="block h-16 w-16 overflow-hidden rounded-control border border-border bg-surface-2">
                  <img
                    v-if="chosenCandidate.cover_url"
                    :src="chosenCandidate.cover_url"
                    alt=""
                    loading="lazy"
                    class="h-full w-full object-cover"
                  />
                  <span v-else class="grid h-full w-full place-items-center text-[10px] text-muted">无封面</span>
                </span>
                <span class="mt-1 block truncate text-[10px] text-muted">
                  {{ providerNames[chosenCandidate.provider] ?? chosenCandidate.provider }}
                </span>
              </div>
            </div>

            <div class="min-w-0">
              <p class="truncate text-sm font-medium">{{ currentTrack?.title || '（无标题）' }}</p>
              <p class="truncate text-xs text-muted">
                {{ currentTrack?.artist || '未知艺术家' }} ·
                {{ formatDuration(currentTrack?.duration ?? null) }}
              </p>
            </div>

            <!-- 试听 -->
            <div class="flex items-center gap-2">
              <button
                type="button"
                class="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-brand text-bg transition-colors hover:bg-brand-600"
                :aria-label="playing ? '暂停' : '试听'"
                @click="togglePlay"
              >
                <svg v-if="!playing" viewBox="0 0 24 24" fill="currentColor" class="ml-0.5 h-3.5 w-3.5">
                  <path d="M8 5.14v13.72L19 12 8 5.14Z" />
                </svg>
                <svg v-else viewBox="0 0 24 24" fill="currentColor" class="h-3.5 w-3.5">
                  <path d="M7 5h4v14H7zM13 5h4v14h-4z" />
                </svg>
              </button>
              <span class="w-8 shrink-0 text-right font-mono text-[10px] text-muted">
                {{ clock(currentTime) }}
              </span>
              <SeekBar
                :current="currentTime"
                :duration="duration"
                :disabled="!duration"
                @seek="seekTo"
              />
              <span class="w-8 shrink-0 font-mono text-[10px] text-muted">{{ clock(duration) }}</span>
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
                @error="streamError = '该格式无法在浏览器内直接播放'"
              />
            </div>
            <p v-if="streamError" class="text-[10px] text-muted">{{ streamError }}</p>

            <label class="flex items-center gap-1.5 text-xs text-muted">
              <input v-model="applyCover" type="checkbox" :disabled="!chosenCandidate.cover_url" />
              写入封面
            </label>

            <!-- 逐字段勾选 -->
            <div class="border-t border-border/60 pt-3">
              <div class="flex items-center justify-between gap-2">
                <span class="text-[11px] text-muted">将写入</span>
                <div class="flex items-center gap-2 text-[11px] text-muted">
                  <button type="button" class="transition-colors hover:text-text" @click="selectAllFields">全选</button>
                  <button type="button" class="transition-colors hover:text-text" @click="selectEmptyFields">只补空</button>
                  <button type="button" class="transition-colors hover:text-text" @click="clearFields">全不选</button>
                </div>
              </div>
              <ul class="mt-2 space-y-1.5 text-xs">
                <li v-for="row in rows" :key="row.key" class="flex items-center gap-2">
                  <input
                    type="checkbox"
                    :checked="selectedFields[row.key] ?? false"
                    :disabled="row.blocked"
                    :aria-label="row.label"
                    @change="toggleField(row.key)"
                  />
                  <span class="w-10 shrink-0 text-muted">{{ row.label }}</span>
                  <span class="min-w-0 flex-1 truncate">
                    <span :class="row.changed ? 'line-through opacity-50' : 'text-text'">{{ row.from }}</span>
                    <template v-if="row.changed">
                      <span class="mx-1 text-muted">→</span>
                      <span class="text-success">{{ row.to }}</span>
                    </template>
                    <span v-else class="ml-1 text-[10px] text-muted">一致</span>
                  </span>
                </li>
              </ul>
            </div>

            <div class="space-y-1.5 border-t border-border/60 pt-3 text-xs text-muted">
              <label class="flex items-center gap-1.5">
                <input v-model="applyLyrics" type="checkbox" />
                写入内嵌歌词
              </label>
              <label class="flex items-center gap-1.5">
                <input v-model="writeLyricsFiles" type="checkbox" />
                写入歌词文件（.lrc 逐行 + .nilyric 逐字）
              </label>
            </div>

            <div class="border-t border-border/60 pt-3">
              <button
                type="button"
                class="w-full rounded-control bg-brand px-4 py-2 text-sm font-medium text-bg transition-colors hover:bg-brand-600 disabled:opacity-50"
                :disabled="applying"
                @click="applyCurrent(true)"
              >
                {{ applying ? '应用中…' : `应用并下一首${pendingCount ? `（${pendingCount} 项）` : ''}` }}
              </button>
              <div class="mt-2 flex gap-2">
                <button
                  type="button"
                  class="flex-1 rounded-control border border-border px-3 py-1.5 text-xs text-muted transition-colors hover:text-text disabled:opacity-50"
                  :disabled="applying"
                  @click="applyCurrent(false)"
                >
                  仅应用
                </button>
                <button
                  type="button"
                  class="flex-1 rounded-control border border-border px-3 py-1.5 text-xs text-muted transition-colors hover:text-text disabled:opacity-50"
                  :disabled="applying"
                  @click="skip"
                >
                  跳过本首（S）
                </button>
              </div>
            </div>
          </template>
        </aside>
    </div>
  </section>
</template>
