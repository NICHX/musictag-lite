<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import CoverLightbox from '@/components/CoverLightbox.vue'
import CoverThumb from '@/components/CoverThumb.vue'
import EmptyState from '@/components/EmptyState.vue'
import SelectionBar from '@/components/SelectionBar.vue'
import TrackInspector from '@/components/TrackInspector.vue'
import type { Track } from '@/api/types'
import { formatBitrate, formatDateTime, formatDuration } from '@/lib/format'
import { useLibraryStore } from '@/stores/library'
import { useTaskStore } from '@/stores/tasks'
import { useUiStore } from '@/stores/ui'

const route = useRoute()
const router = useRouter()
const store = useLibraryStore()
const tasks = useTaskStore()
const ui = useUiStore()

/** 后台任务（扫描 / 批量编辑 / 刮削 / 逐字歌词等）完成后自动刷新当前列表。 */
watch(
  () => tasks.completed,
  () => {
    void store.load()
  },
)

const keyword = ref('')
/** 小屏默认封面墙（表格列多，横向滚动体验差）。 */
const view = ref<'table' | 'grid'>(window.innerWidth < 768 ? 'grid' : 'table')
const activeTrackId = ref<number | null>(null)
const scanning = ref(false)
const notice = ref<string | null>(null)

/** 封面放大查看（灯箱） */
const lightboxTrack = ref<Track | null>(null)

function openLightbox(track: Track): void {
  if (track.has_cover) lightboxTrack.value = track
}

/** 从刮削中心返回时定位到的曲目（用于轻量高亮） */
const matchedTrackId = ref<number | null>(null)

function isMatched(track: Track): boolean {
  return track.id === matchedTrackId.value
}

function rowStyle(track: Track): Record<string, string> | undefined {
  const shadows: string[] = []
  if (store.isSelected(track.id)) shadows.push('inset 2px 0 0 var(--accent-dynamic)')
  if (isMatched(track)) shadows.push('inset 0 0 0 1px var(--brand)')
  return shadows.length ? { boxShadow: shadows.join(', ') } : undefined
}

async function scrollToTrack(id: number): Promise<void> {
  await nextTick()
  document.getElementById(`track-${id}`)?.scrollIntoView({ block: 'center', behavior: 'smooth' })
}

const chips = [
  { key: 'all', label: '全部' },
  { key: 'no-cover', label: '缺封面' },
  { key: 'no-lyrics', label: '无歌词' },
  { key: 'no-word', label: '无逐字歌词' },
  { key: 'incomplete', label: '缺标签' },
] as const
type ChipKey = (typeof chips)[number]['key']
const chip = ref<ChipKey>('all')

const sortOptions = [
  { key: 'filename', label: '文件名' },
  { key: 'title', label: '标题' },
  { key: 'artist', label: '艺术家' },
  { key: 'album', label: '专辑' },
  { key: 'duration', label: '时长' },
  { key: 'size', label: '大小' },
  { key: 'mtime', label: '修改时间' },
] as const

/** 可排序字段（与后端 SortField 白名单一致）。 */
const sortableKeys = new Set<string>([
  'filename',
  'title',
  'artist',
  'album',
  'duration',
  'size',
  'mtime',
])

/** 标签完整度：把后端枚举映射为可读徽标。 */
const tagStatusMeta: Record<string, { label: string; tone: string }> = {
  OK: { label: '完整', tone: 'border-success/40 text-success' },
  MISSING_TAGS: { label: '缺标签', tone: 'border-warning/40 text-warning' },
  MISSING_TITLE: { label: '缺标题', tone: 'border-warning/40 text-warning' },
  MISSING_ARTIST: { label: '缺艺术家', tone: 'border-warning/40 text-warning' },
  MISSING_ALBUM: { label: '缺专辑', tone: 'border-warning/40 text-warning' },
  UNKNOWN: { label: '未知', tone: 'border-border text-muted' },
}

function statusMeta(status: string): { label: string; tone: string } {
  return tagStatusMeta[status] ?? { label: status, tone: 'border-border text-muted' }
}

const orderAsc = computed(() => (store.query.order ?? 'asc') === 'asc')

/** 点击表头：同列切换升降序，换列则以升序开始。 */
function sortBy(key: string): void {
  if (!sortableKeys.has(key)) return
  if (store.query.sort === key) store.query.order = orderAsc.value ? 'desc' : 'asc'
  else {
    store.query.sort = key
    store.query.order = 'asc'
  }
  store.query.page = 1
  void store.loadTracks()
}

function sortMark(key: string): string {
  if (store.query.sort !== key) return ''
  return orderAsc.value ? '↑' : '↓'
}

/** 表格列定义：标签列可点击排序，其余为纯展示列。 */
const columns: { key: string; label: string; sortable: boolean; className: string }[] = [
  { key: 'filename', label: '文件名', sortable: true, className: 'px-3 py-2 font-medium' },
  { key: 'title', label: '标题', sortable: true, className: 'px-3 py-2 font-medium' },
  { key: 'artist', label: '艺术家', sortable: true, className: 'px-3 py-2 font-medium' },
  { key: 'album', label: '专辑', sortable: true, className: 'px-3 py-2 font-medium' },
  { key: 'year', label: '年份', sortable: false, className: 'px-3 py-2 font-medium' },
  { key: 'duration', label: '时长', sortable: true, className: 'px-3 py-2 font-medium' },
  { key: 'format', label: '格式', sortable: false, className: 'px-3 py-2 font-medium' },
  { key: 'status', label: '状态', sortable: false, className: 'px-3 py-2 font-medium' },
  { key: 'mtime', label: '修改时间', sortable: true, className: 'px-3 py-2 font-medium' },
]

const hasLibraries = computed(() => store.libraries.length > 0)
const allOnPageSelected = computed(
  () => store.tracks.length > 0 && store.tracks.every((track) => store.isSelected(track.id)),
)
/** 已选中当前筛选命中的全部曲目（跨页）。 */
const allMatchingSelected = computed(() => store.total > 0 && store.selectedCount === store.total)
/** 本页已全选、但还有更多页时，提示「选择全部」。 */
const showSelectAllHint = computed(
  () => allOnPageSelected.value && store.total > store.tracks.length && !allMatchingSelected.value,
)

async function selectAllMatching(): Promise<void> {
  await store.selectAllMatching()
}

const PAGE_SIZE_OPTIONS = [50, 100, 200]
const currentPage = computed(() => store.query.page ?? 1)
const pageSize = computed(() => store.query.page_size ?? 50)
const pages = computed(() => Math.max(1, Math.ceil(store.total / pageSize.value)))

function goPage(next: number): void {
  store.query.page = Math.min(pages.value, Math.max(1, next))
  void store.loadTracks()
}

function changePageSize(value: number): void {
  store.query.page_size = value
  store.query.page = 1
  void store.loadTracks()
}

function applyChip(next: ChipKey): void {
  chip.value = next
  store.query.has_cover = next === 'no-cover' ? false : undefined
  store.query.has_lyrics = next === 'no-lyrics' ? false : undefined
  store.query.has_word_lyrics = next === 'no-word' ? false : undefined
  store.query.tag_status = next === 'incomplete' ? 'MISSING_TAGS' : undefined
  store.query.page = 1
  void store.loadTracks()
}

function search(): void {
  store.query.q = keyword.value.trim() || undefined
  store.query.page = 1
  void store.loadTracks()
}

function changeSort(value: string): void {
  store.query.sort = value
  store.query.page = 1
  void store.loadTracks()
}

function toggleOrder(): void {
  store.query.order = orderAsc.value ? 'desc' : 'asc'
  store.query.page = 1
  void store.loadTracks()
}

async function scanSelectedLibrary(): Promise<void> {
  const libraryId = store.query.library_id ?? store.libraries[0]?.id
  if (!libraryId) return
  scanning.value = true
  notice.value = null
  try {
    const task = await store.scan(libraryId)
    notice.value = `已启动扫描（任务 #${task.task_id}）`
    tasks.connect()
    void tasks.refresh()
    ui.toggleTaskCenter(true)
  } catch (e) {
    notice.value = e instanceof Error ? e.message : '启动扫描失败'
  } finally {
    scanning.value = false
  }
}

function toggleSelectAll(): void {
  if (allOnPageSelected.value) store.clearSelection()
  else store.selectAllOnPage()
}

async function onSaved(): Promise<void> {
  await store.loadTracks()
}

onMounted(async () => {
  const matchedId = Number(route.query.track) || null
  matchedTrackId.value = matchedId
  await store.load()
  if (matchedId) {
    // 从刮削中心返回：直接打开该曲目详情并滚动定位，省去额外的提示条与二次操作
    activeTrackId.value = matchedId
    await scrollToTrack(matchedId)
    if (route.query.track) void router.replace({ name: 'library' })
  }
})
</script>

<template>
  <section class="mx-auto flex min-h-full w-full max-w-[110rem] flex-col px-4 py-6 md:px-6">
    <header class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 class="font-display text-2xl font-semibold tracking-tight">资源库</h1>
        <p class="mt-1 text-sm text-muted">
          共 {{ store.total }} 首 · {{ store.libraries.length }} 个库
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <select
          v-if="store.libraries.length > 1"
          v-model.number="store.query.library_id"
          class="rounded-control border border-border bg-surface px-2 py-1.5 text-sm text-text outline-none focus:border-brand"
          aria-label="选择库"
          @change="store.loadTracks()"
        >
          <option :value="undefined">全部库</option>
          <option v-for="library in store.libraries" :key="library.id" :value="library.id">
            {{ library.name }}
          </option>
        </select>
        <div class="flex items-center">
          <select
            :value="store.query.sort"
            class="rounded-l-control border border-border bg-surface px-2 py-1.5 text-sm text-text outline-none focus:border-brand"
            aria-label="排序字段"
            @change="changeSort(($event.target as HTMLSelectElement).value)"
          >
            <option v-for="option in sortOptions" :key="option.key" :value="option.key">
              按{{ option.label }}
            </option>
          </select>
          <button
            type="button"
            class="-ml-px rounded-r-control border border-border bg-surface px-2 py-1.5 text-sm text-muted transition-colors hover:text-text"
            :title="orderAsc ? '升序（点击改为降序）' : '降序（点击改为升序）'"
            :aria-label="orderAsc ? '当前升序，切换为降序' : '当前降序，切换为升序'"
            @click="toggleOrder"
          >
            {{ orderAsc ? '↑' : '↓' }}
          </button>
        </div>
        <div class="flex overflow-hidden rounded-control border border-border">
          <button
            type="button"
            class="px-2.5 py-1.5 text-sm transition-colors"
            :class="view === 'table' ? 'bg-surface-2 text-text' : 'text-muted hover:text-text'"
            @click="view = 'table'"
          >
            表格
          </button>
          <button
            type="button"
            class="px-2.5 py-1.5 text-sm transition-colors"
            :class="view === 'grid' ? 'bg-surface-2 text-text' : 'text-muted hover:text-text'"
            @click="view = 'grid'"
          >
            封面墙
          </button>
        </div>
        <button
          type="button"
          class="rounded-control bg-brand px-3 py-1.5 text-sm font-medium text-bg transition-colors hover:bg-brand-600 disabled:opacity-50"
          :disabled="scanning || !hasLibraries"
          @click="scanSelectedLibrary"
        >
          {{ scanning ? '启动中…' : '扫描' }}
        </button>
      </div>
    </header>

    <div class="mt-4 flex flex-wrap items-center gap-2">
      <form class="flex items-center gap-2" @submit.prevent="search">
        <label class="sr-only" for="library-search">搜索曲目</label>
        <input
          id="library-search"
          v-model="keyword"
          type="search"
          placeholder="标题 / 艺术家 / 专辑 / 文件名"
          class="w-56 rounded-control border border-border bg-surface px-3 py-1.5 text-sm text-text outline-none placeholder:text-muted focus:border-brand"
        />
        <button type="submit" class="rounded-control border border-border px-3 py-1.5 text-sm text-muted hover:text-text">
          搜索
        </button>
      </form>
      <button
        v-for="item in chips"
        :key="item.key"
        type="button"
        class="rounded-full border px-3 py-1 text-xs transition-colors"
        :class="
          chip === item.key
            ? 'border-brand bg-brand/10 text-brand'
            : 'border-border text-muted hover:border-brand/50 hover:text-text'
        "
        @click="applyChip(item.key)"
      >
        {{ item.label }}
      </button>
      <button
        type="button"
        class="ml-auto rounded-control border border-border px-2.5 py-1 text-xs text-muted transition-colors hover:text-text"
        @click="store.loadTracks()"
      >
        刷新
      </button>
    </div>

    <p v-if="notice" class="mt-3 rounded-control border border-info/40 bg-info/10 px-3 py-2 text-sm text-info">
      {{ notice }}
    </p>

    <p
      v-if="store.error"
      class="mt-3 rounded-control border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger"
    >
      {{ store.error }}
    </p>

    <div
      v-if="showSelectAllHint || allMatchingSelected"
      class="mt-4 flex flex-wrap items-center gap-x-2 gap-y-1 rounded-control border border-brand/40 bg-brand/5 px-3 py-2 text-xs"
    >
      <template v-if="showSelectAllHint">
        <span class="text-muted">已选中本页 {{ store.tracks.length }} 首。</span>
        <button type="button" class="font-medium text-brand hover:underline" @click="selectAllMatching">
          选择全部 {{ store.total }} 首
        </button>
      </template>
      <template v-else>
        <span class="text-muted">已选中全部 {{ store.total }} 首（跨页批量操作）。</span>
        <button type="button" class="text-brand hover:underline" @click="store.clearSelection()">
          清除选择
        </button>
      </template>
    </div>

    <div class="mt-5 overflow-hidden rounded-card border border-border bg-surface">
      <p v-if="store.loading" class="px-4 py-10 text-center text-sm text-muted">加载中…</p>

      <EmptyState
        v-else-if="!hasLibraries"
        title="还没有音乐库"
        description="先在设置里添加一个音乐库根目录，再回来扫描曲目。"
      >
        <RouterLink
          to="/settings"
          class="inline-flex items-center rounded-control bg-brand px-3.5 py-2 text-sm font-medium text-bg transition-colors hover:bg-brand-600"
        >
          前往设置
        </RouterLink>
      </EmptyState>

      <EmptyState
        v-else-if="!store.tracks.length"
        title="没有符合条件的曲目"
        description="换个筛选条件，或点击右上角「扫描」把库里的曲目读取进来。"
      />

      <!-- 表格视图 -->
      <div v-else-if="view === 'table'" class="overflow-x-auto">
        <table class="w-full min-w-[1100px] table-fixed border-collapse text-sm">
          <colgroup>
            <col class="w-[3%]" />
            <col class="w-[7%]" />
            <col class="w-[15%]" />
            <col class="w-[13%]" />
            <col class="w-[8%]" />
            <col class="w-[10%]" />
            <col class="w-[5%]" />
            <col class="w-[5%]" />
            <col class="w-[9%]" />
            <col class="w-[13%]" />
            <col class="w-[12%]" />
          </colgroup>
          <thead>
            <tr class="border-b border-border text-left text-xs text-muted">
              <th class="px-2 py-2 align-middle">
                <input
                  type="checkbox"
                  :checked="allOnPageSelected"
                  aria-label="全选本页"
                  @change="toggleSelectAll"
                />
              </th>
              <th class="px-3 py-2 font-medium">封面</th>
              <th
                v-for="column in columns"
                :key="column.key"
                :class="column.className"
                :aria-sort="
                  column.sortable && store.query.sort === column.key
                    ? orderAsc
                      ? 'ascending'
                      : 'descending'
                    : undefined
                "
              >
                <button
                  v-if="column.sortable"
                  type="button"
                  class="inline-flex items-center gap-1 transition-colors hover:text-text"
                  @click="sortBy(column.key)"
                >
                  {{ column.label }}
                  <span class="text-brand">{{ sortMark(column.key) }}</span>
                </button>
                <template v-else>{{ column.label }}</template>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="track in store.tracks"
              :id="`track-${track.id}`"
              :key="track.id"
              class="cursor-pointer border-b border-border/60 transition-colors hover:bg-surface-2"
              :class="isMatched(track) ? 'bg-brand/5' : ''"
              :style="rowStyle(track)"
              @click="activeTrackId = track.id"
            >
              <td class="px-2 py-2 align-middle" @click.stop>
                <input
                  type="checkbox"
                  :checked="store.isSelected(track.id)"
                  :aria-label="`选择 ${track.title ?? track.filename}`"
                  @change="store.toggle(track.id)"
                />
              </td>
              <td class="px-3 py-2 align-middle">
                <button
                  type="button"
                  class="block h-12 w-12 overflow-hidden rounded-control border border-border transition-transform"
                  :class="track.has_cover ? 'cursor-zoom-in hover:scale-105' : 'cursor-default'"
                  :title="track.has_cover ? '点击放大封面' : '无封面'"
                  :aria-label="track.has_cover ? '放大封面' : '无封面'"
                  @click.stop="openLightbox(track)"
                >
                  <CoverThumb :track-id="track.id" :has-cover="track.has_cover" />
                </button>
              </td>
              <td class="px-3 py-2 align-middle">
                <span class="line-clamp-2 block break-all font-mono text-xs text-muted" :title="track.filename">
                  {{ track.filename }}
                </span>
              </td>
              <td class="px-3 py-2 align-middle">
                <span class="line-clamp-2 block break-words font-medium" :title="track.title ?? undefined">
                  {{ track.title || '—' }}
                </span>
              </td>
              <td class="px-3 py-2 align-middle">
                <span class="line-clamp-2 block break-words text-muted" :title="track.artist ?? undefined">
                  {{ track.artist || '—' }}
                </span>
              </td>
              <td class="px-3 py-2 align-middle">
                <span class="line-clamp-2 block break-words text-muted" :title="track.album ?? undefined">
                  {{ track.album || '—' }}
                </span>
              </td>
              <td class="px-3 py-2 align-middle font-mono text-xs text-muted">{{ track.year || '—' }}</td>
              <td class="px-3 py-2 align-middle font-mono text-xs text-muted">{{ formatDuration(track.duration) }}</td>
              <td class="px-3 py-2 align-middle font-mono text-xs">
                <span class="line-clamp-2 block">
                  {{ track.format || '—' }}
                  <span v-if="track.bitrate" class="ml-1 text-muted">{{ formatBitrate(track.bitrate) }}</span>
                </span>
              </td>
              <td class="px-3 py-2 align-middle">
                <div class="flex flex-wrap items-center gap-1">
                  <span
                    v-if="track.tag_status !== 'OK'"
                    class="rounded-full border px-1.5 py-0.5 text-[11px]"
                    :class="statusMeta(track.tag_status).tone"
                  >
                    {{ statusMeta(track.tag_status).label }}
                  </span>
                  <span
                    v-if="!track.has_cover"
                    class="rounded-full border border-border px-1.5 py-0.5 text-[11px] text-muted"
                  >
                    缺封面
                  </span>
                  <span
                    v-if="track.has_word_lyrics"
                    class="rounded-full border border-info/40 px-1.5 py-0.5 text-[11px] text-info"
                  >
                    逐字歌词
                  </span>
                  <span
                    v-else-if="!track.has_lyrics"
                    class="rounded-full border border-border px-1.5 py-0.5 text-[11px] text-muted"
                  >
                    无歌词
                  </span>
                  <span
                    v-if="track.tag_status === 'OK' && track.has_cover && track.has_lyrics"
                    class="rounded-full border border-success/40 px-1.5 py-0.5 text-[11px] text-success"
                  >
                    完整
                  </span>
                </div>
              </td>
              <td class="px-3 py-2 align-middle font-mono text-xs text-muted">
                <span class="line-clamp-2 block" :title="formatDateTime(track.mtime)">
                  {{ formatDateTime(track.mtime) }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 封面墙视图 -->
      <div v-else class="grid grid-cols-2 gap-4 p-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
        <button
          v-for="track in store.tracks"
          :id="`track-${track.id}`"
          :key="track.id"
          type="button"
          class="group text-left"
          @click="activeTrackId = track.id"
        >
          <span
            class="relative block aspect-square overflow-hidden rounded-card border transition-colors"
            :class="
              isMatched(track)
                ? 'border-brand ring-2 ring-brand/40'
                : store.isSelected(track.id)
                  ? 'border-brand'
                  : 'border-border group-hover:border-brand/60'
            "
          >
            <CoverThumb :track-id="track.id" :has-cover="track.has_cover" rounded="rounded-none" />
            <span
              v-if="track.has_word_lyrics"
              class="pointer-events-none absolute right-1.5 top-1.5 rounded-full bg-black/55 px-1.5 py-0.5 text-[10px] text-white/95 backdrop-blur-sm"
            >
              逐字
            </span>
            <span
              class="pointer-events-none absolute inset-x-0 bottom-0 flex items-center justify-between gap-2 bg-gradient-to-t from-black/70 to-transparent px-2 pb-1.5 pt-4 font-mono text-[10px] text-white/90 opacity-0 transition-opacity group-hover:opacity-100"
            >
              <span>{{ formatDuration(track.duration) }}</span>
              <span v-if="track.format">{{ track.format }}</span>
            </span>
          </span>
          <span class="mt-2 block truncate text-sm">{{ track.title || track.filename }}</span>
          <span class="block truncate text-xs text-muted">{{ track.artist || '未知艺术家' }}</span>
        </button>
      </div>
    </div>

    <div
      v-if="store.tracks.length"
      class="mt-4 flex flex-wrap items-center justify-center gap-3 text-sm"
    >
      <select
        :value="pageSize"
        class="rounded-control border border-border bg-surface px-2 py-1.5 text-xs text-text outline-none focus:border-brand"
        aria-label="每页数量"
        @change="changePageSize(Number(($event.target as HTMLSelectElement).value))"
      >
        <option v-for="size in PAGE_SIZE_OPTIONS" :key="size" :value="size">每页 {{ size }} 首</option>
      </select>
      <button
        type="button"
        class="rounded-control border border-border px-3 py-1.5 text-muted transition-colors hover:text-text disabled:opacity-40"
        :disabled="currentPage <= 1"
        @click="goPage(currentPage - 1)"
      >
        上一页
      </button>
      <span class="font-mono text-xs text-muted">
        第 {{ currentPage }} / {{ pages }} 页 · 共 {{ store.total }} 首
      </span>
      <button
        type="button"
        class="rounded-control border border-border px-3 py-1.5 text-muted transition-colors hover:text-text disabled:opacity-40"
        :disabled="currentPage >= pages"
        @click="goPage(currentPage + 1)"
      >
        下一页
      </button>
    </div>

    <SelectionBar
      v-if="store.selectedCount"
      :ids="[...store.selectedIds]"
      @clear="store.clearSelection()"
      @done="onSaved"
    />

    <TrackInspector
      v-if="activeTrackId != null"
      :track-id="activeTrackId"
      @close="activeTrackId = null"
      @saved="onSaved"
    />

    <CoverLightbox
      v-if="lightboxTrack"
      :track-id="lightboxTrack.id"
      :title="lightboxTrack.title"
      :artist="lightboxTrack.artist"
      @close="lightboxTrack = null"
    />
  </section>
</template>
