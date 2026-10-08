<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import EmptyState from '@/components/EmptyState.vue'
import { coverApi, providerApi, scrapeApi } from '@/api/endpoints'
import type { Candidate, ScrapeApplyResponse, Track } from '@/api/types'
import { formatDuration } from '@/lib/format'
import { PLAN_FIELDS, changedFields, planChanges } from '@/lib/scrapePlan'
import { useLibraryStore } from '@/stores/library'
import { useScrapeStore } from '@/stores/scrape'
import { useTaskStore } from '@/stores/tasks'

const route = useRoute()
const router = useRouter()
const store = useLibraryStore()
const tasks = useTaskStore()
const scrapeStore = useScrapeStore()

const selectedTrackId = ref<number | null>(null)
const candidates = ref<Candidate[]>([])
const chosenUid = ref<string | null>(null)
const providerNames = ref<Record<string, string>>({})
const searching = ref(false)
const applying = ref(false)
const error = ref<string | null>(null)

const onlyMissing = ref(true)
const applyCover = ref(true)
const applyLyrics = ref(false)

const applied = ref<ScrapeApplyResponse | null>(null)
const appliedTrack = ref<Track | null>(null)
const coverVersion = ref(0)
const brokeCover = ref(false)
const brokenCandidates = ref<Set<string>>(new Set())
const asideEl = ref<HTMLElement | null>(null)

/** 候选默认只展示前若干条，避免把整页撑长 */
const CANDIDATE_PREVIEW = 5
const showAllCandidates = ref(false)
const visibleCandidates = computed(() =>
  showAllCandidates.value ? candidates.value : candidates.value.slice(0, CANDIDATE_PREVIEW),
)

const currentTrack = computed<Track | null>(
  () => store.tracks.find((track) => track.id === selectedTrackId.value) ?? null,
)

const chosenCandidate = computed<Candidate | null>(
  () => candidates.value.find((item) => scrapeApi.list(item) === chosenUid.value) ?? null,
)

/** 点「应用」之前就能看到的完整写入清单（含被「仅补空值」跳过的字段）。 */
const planned = computed(() =>
  planChanges(
    currentTrack.value as unknown as Record<string, unknown> | null,
    chosenCandidate.value as unknown as Record<string, unknown> | null,
    onlyMissing.value,
  ),
)
const writableCount = computed(() => planned.value.filter((item) => !item.blocked).length)

const currentCoverUrl = computed(() =>
  currentTrack.value ? `${coverApi.url(currentTrack.value.id)}?v=${coverVersion.value}` : '',
)

const appliedCoverUrl = computed(() =>
  appliedTrack.value ? `${coverApi.url(appliedTrack.value.id)}?v=${coverVersion.value}` : '',
)

function candidateFields(candidate: Candidate) {
  return changedFields(
    currentTrack.value as unknown as Record<string, unknown> | null,
    candidate as unknown as Record<string, unknown>,
  )
}

function fieldLabel(key: string): string {
  return PLAN_FIELDS.find((item) => item.key === key)?.label ?? key
}

/** 匹配度配色：≥0.8 可信、≥0.6 尚可、以下偏弱（与后端 0.6 自动应用阈值呼应）。 */
function scoreTone(score: number): string {
  if (score >= 0.8) return 'text-success'
  if (score >= 0.6) return 'text-text'
  return 'text-muted'
}

function markCoverBroken(uid: string): void {
  brokenCandidates.value = new Set(brokenCandidates.value).add(uid)
}

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
  candidates.value = []
  chosenUid.value = null
  applied.value = null
  appliedTrack.value = null
  showAllCandidates.value = false
  try {
    const response = await scrapeApi.search({ track_id: selectedTrackId.value, limit: 10 })
    candidates.value = response.candidates
    if (candidates.value.length) chosenUid.value = scrapeApi.list(candidates.value[0])
  } catch (e) {
    error.value = e instanceof Error ? e.message : '搜索失败'
  } finally {
    searching.value = false
  }
}

async function apply(): Promise<void> {
  const trackId = selectedTrackId.value
  if (!trackId || !chosenUid.value) return
  applying.value = true
  error.value = null
  try {
    applied.value = await scrapeApi.apply({
      track_id: trackId,
      candidate_ids: [chosenUid.value],
      only_missing: onlyMissing.value,
      apply_cover: applyCover.value,
      apply_lyrics: applyLyrics.value,
    })
    await loadTracks()
    const refreshed = store.tracks.find((track) => track.id === trackId) ?? null
    appliedTrack.value = refreshed
    coverVersion.value += 1
    brokeCover.value = false
    scrapeStore.setLastMatched({
      id: trackId,
      title: refreshed?.title ?? null,
      artist: refreshed?.artist ?? null,
      fields: applied.value.applied_fields,
      coverApplied: applied.value.cover_applied,
      lyricsApplied: applied.value.lyrics_applied,
    })
    tasks.connect()
    void tasks.refresh()
    // 回执出现在左栏（按钮处），确保与小屏用户当前视线一致
    await nextTick()
    asideEl.value?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  } catch (e) {
    error.value = e instanceof Error ? e.message : '应用失败'
  } finally {
    applying.value = false
  }
}

/** 回到资源库并定位到刚匹配的这首（列表会高亮并滚动到它）。 */
function backToLibrary(): void {
  const id = applied.value?.track_id ?? selectedTrackId.value
  void router.push({ name: 'library', query: id ? { track: String(id) } : {} })
}

function resetResult(): void {
  applied.value = null
  appliedTrack.value = null
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
  <section class="mx-auto flex min-h-full w-full max-w-6xl flex-col px-4 py-6 md:px-6">
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
        <h1 class="font-display text-2xl font-semibold tracking-tight">刮削中心</h1>
        <p class="mt-1 text-sm text-muted">
          MusicBrainz · Cover Art Archive · LRCLIB（开放数据源，可插拔）
        </p>
      </div>

      <div class="flex flex-wrap items-center gap-2">
        <select
          v-model.number="selectedTrackId"
          class="min-w-56 max-w-72 rounded-control border border-border bg-surface px-2.5 py-1.5 text-sm text-text outline-none focus:border-brand"
          aria-label="选择曲目"
          @change="resetResult"
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
      </div>
    </header>

    <p
      v-if="error"
      class="mt-3 rounded-control border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger"
    >
      {{ error }}
    </p>

    <div class="mt-5 grid gap-5 lg:grid-cols-[20rem_1fr]">
      <!-- 当前曲目 + 本次将写入 -->
      <aside ref="asideEl" class="flex flex-col gap-4 self-start lg:sticky lg:top-4">
        <div class="rounded-card border border-border bg-surface p-4">
          <h2 class="text-xs font-medium uppercase tracking-wide text-muted">当前曲目</h2>

          <div v-if="currentTrack" class="mt-3 flex gap-3">
            <div class="h-20 w-20 shrink-0 overflow-hidden rounded-card border border-border bg-surface-2">
              <img
                v-if="currentTrack.has_cover && !brokeCover"
                :src="currentCoverUrl"
                alt="当前封面"
                class="h-full w-full object-cover"
                @error="brokeCover = true"
              />
              <div v-else class="grid h-full w-full place-items-center text-muted" aria-hidden="true">
                <svg viewBox="0 0 64 64" fill="none" class="h-8 w-8">
                  <circle cx="32" cy="32" r="26" stroke="currentColor" stroke-width="1.5" />
                  <circle cx="32" cy="32" r="9" stroke="currentColor" stroke-width="1.5" />
                  <circle cx="32" cy="32" r="2.5" fill="currentColor" />
                </svg>
              </div>
            </div>
            <div class="min-w-0">
              <p class="truncate text-sm font-medium">{{ currentTrack.title || '（无标题）' }}</p>
              <p class="mt-0.5 truncate text-xs text-muted">
                {{ currentTrack.artist || '未知艺术家' }}
              </p>
              <p class="mt-1 truncate font-mono text-[11px] text-muted" :title="currentTrack.filename">
                {{ currentTrack.filename }}
              </p>
            </div>
          </div>
          <p v-else class="mt-3 text-sm text-muted">尚未选择曲目。</p>

          <dl v-if="currentTrack" class="mt-3 space-y-1.5 border-t border-border/60 pt-3 text-xs">
            <div v-for="field in PLAN_FIELDS" :key="field.key" class="flex gap-2">
              <dt class="w-12 shrink-0 text-muted">{{ field.label }}</dt>
              <dd
                class="min-w-0 truncate"
                :class="currentTrack[field.key as keyof Track] ? 'text-text' : 'text-muted'"
              >
                {{ currentTrack[field.key as keyof Track] || '∅' }}
              </dd>
            </div>
            <div class="flex gap-2">
              <dt class="w-12 shrink-0 text-muted">时长</dt>
              <dd class="font-mono text-muted">{{ formatDuration(currentTrack.duration) }}</dd>
            </div>
          </dl>
        </div>

        <!-- 已写入回执：原地替换「本次将写入」，与点击位置同屏 -->
        <div
          v-if="applied"
          aria-live="polite"
          class="rounded-card border border-success/40 bg-success/5 p-4"
        >
          <div class="flex items-center justify-between">
            <h2 class="text-xs font-medium uppercase tracking-wide text-success">已写入</h2>
            <span class="text-[11px] text-muted">匹配完成</span>
          </div>

          <div class="mt-3 flex gap-3">
            <div class="h-16 w-16 shrink-0 overflow-hidden rounded-card border border-border bg-surface-2">
              <img :src="appliedCoverUrl" alt="写入后的封面" class="h-full w-full object-cover" />
            </div>
            <div class="min-w-0">
              <p class="truncate text-sm font-medium">{{ appliedTrack?.title || '（无标题）' }}</p>
              <p class="truncate text-xs text-muted">
                {{ appliedTrack?.artist || '未知艺术家' }}
              </p>
              <p class="mt-1 text-[11px] text-muted">
                封面{{ applied.cover_applied ? '已写入' : '未写入' }} · 歌词{{
                  applied.lyrics_applied ? '已写入' : '未写入'
                }}
              </p>
            </div>
          </div>

          <ul v-if="applied.diffs.length" class="mt-3 space-y-1 border-t border-success/20 pt-3 text-xs">
            <li v-for="diff in applied.diffs" :key="diff.field" class="flex flex-wrap items-center gap-2">
              <span class="w-12 shrink-0 text-muted">{{ fieldLabel(diff.field) }}</span>
              <span class="min-w-0 max-w-[6rem] truncate line-through opacity-60">
                {{ diff.old_value ?? '∅' }}
              </span>
              <span class="shrink-0 text-muted">→</span>
              <span class="min-w-0 max-w-[8rem] truncate text-success">{{ diff.new_value ?? '∅' }}</span>
            </li>
          </ul>
          <p v-else class="mt-3 border-t border-success/20 pt-3 text-xs text-muted">
            标签与原有值一致，未做改动。
          </p>

          <div class="mt-3 flex flex-col gap-2">
            <button
              type="button"
              class="rounded-control bg-brand px-3.5 py-2 text-sm font-medium text-bg transition-colors hover:bg-brand-600"
              @click="backToLibrary"
            >
              返回资源库（已定位到这首）
            </button>
            <button
              type="button"
              class="rounded-control border border-border px-3.5 py-2 text-sm text-muted transition-colors hover:text-text"
              @click="resetResult"
            >
              继续匹配其他候选
            </button>
          </div>
        </div>

        <!-- 本次将写入：点应用前即可见 -->
        <div v-else class="rounded-card border border-border bg-surface p-4">
          <h2 class="text-xs font-medium uppercase tracking-wide text-muted">本次将写入</h2>

          <p v-if="!chosenCandidate" class="mt-3 text-xs text-muted">
            先搜索并选择一个候选，这里会列出将要写入的字段。
          </p>
          <ul v-else-if="planned.length" class="mt-3 space-y-1.5 text-xs">
            <li
              v-for="item in planned"
              :key="item.key"
              class="flex flex-wrap items-center gap-x-2 gap-y-0.5"
              :class="item.blocked ? 'text-muted' : 'text-text'"
            >
              <span class="w-12 shrink-0 text-muted">{{ item.label }}</span>
              <span class="min-w-0 max-w-[7rem] truncate line-through opacity-60">{{ item.from }}</span>
              <span class="shrink-0 text-muted">→</span>
              <span class="min-w-0 max-w-[9rem] truncate" :class="item.blocked ? 'opacity-60' : 'text-success'">
                {{ item.to }}
              </span>
              <span v-if="item.blocked" class="shrink-0 rounded-full border border-border px-1.5 text-[10px] text-muted">
                跳过
              </span>
            </li>
          </ul>
          <p v-else class="mt-3 text-xs text-success">与当前标签一致，无需修改。</p>

          <div class="mt-3 space-y-1.5 border-t border-border/60 pt-3 text-xs text-muted">
            <label class="flex items-center gap-1.5">
              <input v-model="onlyMissing" type="checkbox" /> 仅补空值（不覆盖已有标签）
            </label>
            <label class="flex items-center gap-1.5">
              <input v-model="applyCover" type="checkbox" /> 同时写封面
            </label>
            <label class="flex items-center gap-1.5">
              <input v-model="applyLyrics" type="checkbox" /> 同时写歌词
            </label>
          </div>

          <button
            type="button"
            class="mt-3 w-full rounded-control bg-brand px-4 py-2 text-sm font-medium text-bg transition-colors hover:bg-brand-600 disabled:opacity-50"
            :disabled="applying || !chosenUid"
            @click="apply"
          >
            {{ applying ? '应用中…' : `应用选中候选${writableCount ? `（${writableCount} 项）` : ''}` }}
          </button>
        </div>
      </aside>

      <!-- 候选列表 -->
      <div class="rounded-card border border-border bg-surface p-4">
        <div class="flex items-center justify-between">
          <h2 class="text-xs font-medium uppercase tracking-wide text-muted">
            候选（{{ candidates.length }}）
          </h2>
          <span v-if="candidates.length" class="text-[11px] text-muted">
            {{
              showAllCandidates
                ? `共 ${candidates.length} 条 · 按匹配度排序`
                : `显示前 ${Math.min(CANDIDATE_PREVIEW, candidates.length)} / ${candidates.length} 条 · 按匹配度排序`
            }}
          </span>
        </div>

        <p v-if="searching" class="py-10 text-center text-sm text-muted">搜索中…</p>

        <EmptyState
          v-else-if="!candidates.length"
          title="暂无候选"
          description="在上方选择一首曲目并点击「搜索候选」，结果会按匹配度排序，并标注与当前标签的差异。"
        />

        <ul v-else class="mt-3 space-y-2">
          <li v-for="(candidate, index) in visibleCandidates" :key="scrapeApi.list(candidate)">
            <button
              type="button"
              class="flex w-full items-start gap-2.5 rounded-card border p-2.5 text-left transition-colors"
              :class="
                chosenUid === scrapeApi.list(candidate)
                  ? 'border-brand bg-brand/5'
                  : 'border-border hover:border-brand/50'
              "
              :aria-pressed="chosenUid === scrapeApi.list(candidate)"
              @click="chosenUid = scrapeApi.list(candidate)"
            >
              <!-- 候选封面 -->
              <span
                class="h-12 w-12 shrink-0 overflow-hidden rounded-control border border-border bg-surface-2"
              >
                <img
                  v-if="candidate.cover_url && !brokenCandidates.has(scrapeApi.list(candidate))"
                  :src="candidate.cover_url"
                  alt=""
                  loading="lazy"
                  class="h-full w-full object-cover"
                  @error="markCoverBroken(scrapeApi.list(candidate))"
                />
                <span v-else class="grid h-full w-full place-items-center text-muted" aria-hidden="true">
                  <svg viewBox="0 0 64 64" fill="none" class="h-5 w-5">
                    <circle cx="32" cy="32" r="26" stroke="currentColor" stroke-width="1.5" />
                    <circle cx="32" cy="32" r="9" stroke="currentColor" stroke-width="1.5" />
                    <circle cx="32" cy="32" r="2.5" fill="currentColor" />
                  </svg>
                </span>
              </span>

              <span class="min-w-0 flex-1">
                <span class="flex items-center gap-1.5">
                  <span v-if="index === 0" class="shrink-0 rounded-full bg-brand/15 px-1.5 py-0.5 text-[10px] text-brand">
                    最佳
                  </span>
                  <span class="min-w-0 flex-1 truncate text-sm font-medium">
                    {{ candidate.title || '（无标题）' }}
                  </span>
                  <span class="shrink-0 font-mono text-[11px]" :class="scoreTone(candidate.score)">
                    {{ Math.round(candidate.score * 100) }} 分
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

                <span class="mt-1.5 block h-0.5 overflow-hidden rounded-full bg-border" aria-hidden="true">
                  <span
                    class="block h-full rounded-full bg-brand"
                    :style="{ width: `${Math.round(candidate.score * 100)}%` }"
                  />
                </span>
              </span>
            </button>
          </li>
        </ul>

        <div v-if="candidates.length > CANDIDATE_PREVIEW" class="mt-3 text-center">
          <button
            type="button"
            class="rounded-control border border-border px-3 py-1 text-xs text-muted transition-colors hover:text-text"
            @click="showAllCandidates = !showAllCandidates"
          >
            {{ showAllCandidates ? '收起' : `显示全部 ${candidates.length} 条` }}
          </button>
        </div>

        <!-- 小屏：动作放在列表下方，避免来回滚动 -->
        <button
          v-if="candidates.length && !applied"
          type="button"
          class="mt-3 w-full rounded-control bg-brand px-4 py-2 text-sm font-medium text-bg transition-colors hover:bg-brand-600 disabled:opacity-50 lg:hidden"
          :disabled="applying || !chosenUid"
          @click="apply"
        >
          {{ applying ? '应用中…' : `应用选中候选${writableCount ? `（${writableCount} 项）` : ''}` }}
        </button>

        <div v-if="applied" class="mt-3 lg:hidden">
          <div class="rounded-control border border-success/40 bg-success/5 px-3 py-2">
            <p class="text-xs text-success">
              已写入 {{ applied.diffs.length }} 项改动（完整回执见上方）
            </p>
            <button
              type="button"
              class="mt-2 w-full rounded-control bg-brand px-3 py-1.5 text-sm font-medium text-bg transition-colors hover:bg-brand-600"
              @click="backToLibrary"
            >
              返回资源库（已定位到这首）
            </button>
          </div>
        </div>
      </div>
    </div>

  </section>
</template>
