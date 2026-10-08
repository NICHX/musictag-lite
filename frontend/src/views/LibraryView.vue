<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'

import CoverThumb from '@/components/CoverThumb.vue'
import EmptyState from '@/components/EmptyState.vue'
import SelectionBar from '@/components/SelectionBar.vue'
import TrackInspector from '@/components/TrackInspector.vue'
import { formatBitrate, formatDateTime, formatDuration } from '@/lib/format'
import { useLibraryStore } from '@/stores/library'
import { useTaskStore } from '@/stores/tasks'
import { useUiStore } from '@/stores/ui'

const store = useLibraryStore()
const tasks = useTaskStore()
const ui = useUiStore()

const keyword = ref('')
const view = ref<'table' | 'grid'>('table')
const activeTrackId = ref<number | null>(null)
const scanning = ref(false)
const notice = ref<string | null>(null)

const chips = [
  { key: 'all', label: '全部' },
  { key: 'no-cover', label: '缺封面' },
  { key: 'no-lyrics', label: '无歌词' },
  { key: 'incomplete', label: '缺标签' },
] as const
type ChipKey = (typeof chips)[number]['key']
const chip = ref<ChipKey>('all')

const sortOptions = [
  { key: 'filename', label: '文件名' },
  { key: 'mtime', label: '修改时间' },
  { key: 'size', label: '大小' },
  { key: 'duration', label: '时长' },
  { key: 'title', label: '标题' },
] as const

const statusTone: Record<string, string> = {
  OK: 'border-success/40 text-success',
  MISSING_TAGS: 'border-warning/40 text-warning',
  MISSING_TITLE: 'border-warning/40 text-warning',
  MISSING_ARTIST: 'border-warning/40 text-warning',
  MISSING_ALBUM: 'border-warning/40 text-warning',
}

const hasLibraries = computed(() => store.libraries.length > 0)
const allOnPageSelected = computed(
  () => store.tracks.length > 0 && store.tracks.every((track) => store.isSelected(track.id)),
)

function applyChip(next: ChipKey): void {
  chip.value = next
  store.query.has_cover = next === 'no-cover' ? false : undefined
  store.query.has_lyrics = next === 'no-lyrics' ? false : undefined
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

onMounted(() => {
  void store.load()
})
</script>

<template>
  <section class="mx-auto flex min-h-full w-full max-w-6xl flex-col px-4 py-6 md:px-6">
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
        <select
          :value="store.query.sort"
          class="rounded-control border border-border bg-surface px-2 py-1.5 text-sm text-text outline-none focus:border-brand"
          aria-label="排序"
          @change="changeSort(($event.target as HTMLSelectElement).value)"
        >
          <option v-for="option in sortOptions" :key="option.key" :value="option.key">
            按{{ option.label }}
          </option>
        </select>
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
        <table class="w-full border-collapse text-sm">
          <thead>
            <tr class="border-b border-border text-left text-xs text-muted">
              <th class="w-10 px-3 py-2">
                <input
                  type="checkbox"
                  :checked="allOnPageSelected"
                  aria-label="全选本页"
                  @change="toggleSelectAll"
                />
              </th>
              <th class="w-12 px-3 py-2 font-medium">封面</th>
              <th class="px-3 py-2 font-medium">文件名</th>
              <th class="px-3 py-2 font-medium">标题</th>
              <th class="px-3 py-2 font-medium">艺术家</th>
              <th class="px-3 py-2 font-medium">专辑</th>
              <th class="px-3 py-2 font-medium">时长</th>
              <th class="px-3 py-2 font-medium">格式</th>
              <th class="px-3 py-2 font-medium">码率</th>
              <th class="px-3 py-2 font-medium">状态</th>
              <th class="px-3 py-2 font-medium">修改时间</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="track in store.tracks"
              :key="track.id"
              class="cursor-pointer border-b border-border/60 transition-colors hover:bg-surface-2"
              :style="
                store.isSelected(track.id)
                  ? { boxShadow: 'inset 2px 0 0 var(--accent-dynamic)' }
                  : undefined
              "
              @click="activeTrackId = track.id"
            >
              <td class="px-3 py-2" @click.stop>
                <input
                  type="checkbox"
                  :checked="store.isSelected(track.id)"
                  :aria-label="`选择 ${track.title ?? track.filename}`"
                  @change="store.toggle(track.id)"
                />
              </td>
              <td class="px-3 py-2">
                <span class="block h-9 w-9">
                  <CoverThumb :track-id="track.id" :has-cover="track.has_cover" />
                </span>
              </td>
              <td class="px-3 py-2">
                <span
                  class="block max-w-[18rem] truncate font-mono text-xs text-muted"
                  :title="track.filename"
                >
                  {{ track.filename }}
                </span>
              </td>
              <td class="px-3 py-2">{{ track.title || '—' }}</td>
              <td class="px-3 py-2 text-muted">{{ track.artist || '—' }}</td>
              <td class="px-3 py-2 text-muted">{{ track.album || '—' }}</td>
              <td class="px-3 py-2 font-mono text-xs text-muted">{{ formatDuration(track.duration) }}</td>
              <td class="px-3 py-2">{{ track.format || '—' }}</td>
              <td class="px-3 py-2 font-mono text-xs text-muted">{{ formatBitrate(track.bitrate) }}</td>
              <td class="px-3 py-2">
                <span
                  class="rounded-full border px-2 py-0.5 text-[11px]"
                  :class="statusTone[track.tag_status] ?? 'border-border text-muted'"
                >
                  {{ track.tag_status }}
                </span>
              </td>
              <td class="whitespace-nowrap px-3 py-2 font-mono text-xs text-muted">
                {{ formatDateTime(track.mtime) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 封面墙视图 -->
      <div v-else class="grid grid-cols-2 gap-4 p-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
        <button
          v-for="track in store.tracks"
          :key="track.id"
          type="button"
          class="group text-left"
          @click="activeTrackId = track.id"
        >
          <span
            class="block aspect-square overflow-hidden rounded-card border transition-colors"
            :class="store.isSelected(track.id) ? 'border-brand' : 'border-border group-hover:border-brand/60'"
          >
            <CoverThumb :track-id="track.id" :has-cover="track.has_cover" rounded="rounded-none" />
          </span>
          <span class="mt-2 block truncate text-sm">{{ track.title || track.filename }}</span>
          <span class="block truncate text-xs text-muted">{{ track.artist || '未知艺术家' }}</span>
        </button>
      </div>
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
  </section>
</template>
