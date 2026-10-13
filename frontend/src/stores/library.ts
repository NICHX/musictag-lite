import { defineStore } from 'pinia'
import { computed, reactive, ref } from 'vue'

import { libraryApi, trackApi } from '@/api/endpoints'
import type { TrackQuery } from '@/api/endpoints'
import type { Library, Track, TaskAccepted } from '@/api/types'

export const useLibraryStore = defineStore('library', () => {
  const libraries = ref<Library[]>([])
  const tracks = ref<Track[]>([])
  const total = ref(0)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const selectedIds = ref<Set<number>>(new Set())

  const query = reactive<TrackQuery>({
    page: 1,
    page_size: 50,
    sort: 'filename',
    order: 'asc',
  })

  const selectedCount = computed(() => selectedIds.value.size)
  const selectedList = computed(() => tracks.value.filter((track) => selectedIds.value.has(track.id)))

  async function loadLibraries(): Promise<void> {
    libraries.value = await libraryApi.list()
  }

  async function loadTracks(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const active: TrackQuery = { ...query }
      const page = await trackApi.list(active)
      tracks.value = page.items
      total.value = page.total
    } catch (e) {
      error.value = e instanceof Error ? e.message : '加载失败'
    } finally {
      loading.value = false
    }
  }

  async function load(): Promise<void> {
    await Promise.all([loadLibraries(), loadTracks()])
  }

  async function scan(libraryId: number): Promise<TaskAccepted> {
    return libraryApi.scan(libraryId)
  }

  function isSelected(id: number): boolean {
    return selectedIds.value.has(id)
  }

  function toggle(id: number): void {
    const next = new Set(selectedIds.value)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    selectedIds.value = next
  }

  function selectOnly(ids: number[]): void {
    selectedIds.value = new Set(ids)
  }

  function selectAllOnPage(): void {
    selectedIds.value = new Set(tracks.value.map((track) => track.id))
  }

  /** 选择当前筛选命中的全部曲目（跨页），用于全库批量操作。 */
  async function selectAllMatching(): Promise<void> {
    const result = await trackApi.ids({ ...query })
    selectedIds.value = new Set(result.ids)
  }

  function clearSelection(): void {
    selectedIds.value = new Set()
  }

  async function removeLibrary(id: number): Promise<void> {
    await libraryApi.remove(id)
    libraries.value = libraries.value.filter((item) => item.id !== id)
    await loadTracks()
  }

  return {
    libraries,
    tracks,
    total,
    loading,
    error,
    query,
    selectedIds,
    selectedCount,
    selectedList,
    loadLibraries,
    loadTracks,
    load,
    scan,
    isSelected,
    toggle,
    selectOnly,
    selectAllOnPage,
    selectAllMatching,
    clearSelection,
    removeLibrary,
  }
})

export type LibraryStore = ReturnType<typeof useLibraryStore>
export type { Track }
