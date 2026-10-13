<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'

import EmptyState from '@/components/EmptyState.vue'
import { logsApi } from '@/api/endpoints'
import type { OperationLog } from '@/api/types'

const logs = ref<OperationLog[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const page = ref(1)
const pageSize = ref(50)
const total = ref(0)
const source = ref('')
const keyword = ref('')

const ACTION_LABELS: Record<string, string> = {
  'tag.edit': '标签修改',
  'cover.write': '封面写入',
  'cover.delete': '封面删除',
  'cover.export': '封面导出',
  'lyrics.write': '歌词写入',
  'organize.move': '整理移动',
}

const FIELD_LABELS: Record<string, string> = {
  title: '标题',
  artist: '艺术家',
  album: '专辑',
  album_artist: '专辑艺术家',
  composer: '作曲',
  genre: '流派',
  track_no: '音轨号',
  disc_no: '碟号',
  year: '年份',
  date: '日期',
  comment: '注释',
  lyrics: '歌词',
}

const SOURCES = [
  { key: '', label: '全部来源' },
  { key: 'manual', label: '手动' },
  { key: 'batch', label: '批量' },
  { key: 'scrape', label: '刮削' },
] as const

const pages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))

function actionLabel(action: string): string {
  return ACTION_LABELS[action] ?? action
}

function fieldLabel(field: string | null): string {
  if (!field) return '—'
  return FIELD_LABELS[field] ?? field
}

function cell(value: string | null | undefined): string {
  const text = value === null || value === undefined || value === '' ? '∅' : String(value)
  return text.length > 80 ? `${text.slice(0, 80)}…` : text
}

function formatTime(value: string): string {
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const result = await logsApi.list({
      page: page.value,
      page_size: pageSize.value,
      source: source.value || undefined,
      q: keyword.value.trim() || undefined,
    })
    logs.value = result.items
    total.value = result.total
  } catch (e) {
    error.value = e instanceof Error ? e.message : '加载失败'
  } finally {
    loading.value = false
  }
}

function applyFilter(): void {
  page.value = 1
  void load()
}

function goPage(next: number): void {
  page.value = Math.min(pages.value, Math.max(1, next))
  void load()
}

function search(): void {
  page.value = 1
  void load()
}

onMounted(load)
</script>

<template>
  <section class="mx-auto w-full max-w-[110rem] px-4 py-6 md:px-6">
    <header class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 class="font-display text-2xl font-semibold tracking-tight">操作日志</h1>
        <p class="mt-1 text-sm text-muted">
          共 {{ total }} 条 · 记录每次写入的字段、前后值与来源
        </p>
      </div>
      <button
        type="button"
        class="rounded-control border border-border px-3 py-1.5 text-sm text-muted transition-colors hover:border-brand/60 hover:text-text"
        @click="load"
      >
        刷新
      </button>
    </header>

    <div class="mt-4 flex flex-wrap items-center gap-2">
      <form class="flex min-w-0 items-center gap-2" @submit.prevent="search">
        <input
          v-model="keyword"
          type="search"
          placeholder="搜索字段值 / 动作"
          class="w-40 rounded-control border border-border bg-surface px-3 py-1.5 text-sm text-text outline-none placeholder:text-muted focus:border-brand sm:w-56"
        />
        <button type="submit" class="rounded-control border border-border px-3 py-1.5 text-sm text-muted transition-colors hover:text-text">
          搜索
        </button>
      </form>
      <div class="flex flex-wrap items-center gap-1.5">
        <button
          v-for="item in SOURCES"
          :key="item.key"
          type="button"
          class="rounded-full border px-3 py-1 text-xs transition-colors"
          :class="
            source === item.key
              ? 'border-brand bg-brand/10 text-brand'
              : 'border-border text-muted hover:border-brand/50 hover:text-text'
          "
          @click="source = item.key; applyFilter()"
        >
          {{ item.label }}
        </button>
      </div>
    </div>

    <p v-if="error" class="mt-4 rounded-control border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
      {{ error }}
    </p>

    <div class="mt-4 overflow-hidden rounded-card border border-border bg-surface">
      <p v-if="loading" class="px-4 py-10 text-center text-sm text-muted">加载中…</p>
      <EmptyState
        v-else-if="!logs.length"
        title="暂无操作记录"
        description="单条/批量编辑、刮削应用与封面写入都会在此留痕。"
      />

      <template v-else>
        <!-- 小屏：卡片列表 -->
        <ul class="divide-y divide-border/60 md:hidden">
        <li v-for="log in logs" :key="log.id" class="px-3 py-2.5 text-xs">
          <div class="flex items-center justify-between gap-2">
            <span class="font-mono text-muted">{{ formatTime(log.created_at) }}</span>
            <span class="rounded-full border border-border px-1.5 py-0.5 text-[10px] text-muted">{{ log.source }}</span>
          </div>
          <div class="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
            <span class="text-text">{{ actionLabel(log.action) }}</span>
            <span v-if="log.field" class="text-muted">· {{ fieldLabel(log.field) }}</span>
            <RouterLink
              v-if="log.track_id"
              :to="{ name: 'library', query: { track: String(log.track_id) } }"
              class="font-mono text-[11px] text-muted hover:text-brand"
            >
              #{{ log.track_id }}
            </RouterLink>
          </div>
          <p v-if="log.field" class="mt-1 break-all text-muted">
            {{ cell(log.old_value) }} → <span class="text-text">{{ cell(log.new_value) }}</span>
          </p>
        </li>
      </ul>

      <!-- 大屏：表格 -->
      <div class="hidden overflow-x-auto md:block">
        <table class="w-full border-collapse text-sm">
          <thead>
            <tr class="border-b border-border text-left text-xs text-muted">
              <th class="whitespace-nowrap px-3 py-2 font-medium">时间</th>
              <th class="px-3 py-2 font-medium">曲目</th>
              <th class="px-3 py-2 font-medium">操作</th>
              <th class="px-3 py-2 font-medium">字段</th>
              <th class="px-3 py-2 font-medium">旧值 → 新值</th>
              <th class="px-3 py-2 font-medium">来源</th>
              <th class="px-3 py-2 font-medium">结果</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="log in logs" :key="log.id" class="border-b border-border/60 hover:bg-surface-2">
              <td class="whitespace-nowrap px-3 py-2 font-mono text-xs text-muted">{{ formatTime(log.created_at) }}</td>
              <td class="px-3 py-2">
                <RouterLink
                  v-if="log.track_id"
                  :to="{ name: 'library', query: { track: String(log.track_id) } }"
                  class="font-mono text-xs text-muted transition-colors hover:text-brand"
                >
                  #{{ log.track_id }}
                </RouterLink>
                <span v-else class="font-mono text-xs text-muted">—</span>
              </td>
              <td class="px-3 py-2">{{ actionLabel(log.action) }}</td>
              <td class="px-3 py-2 text-muted">{{ fieldLabel(log.field) }}</td>
              <td class="max-w-[24rem] truncate px-3 py-2 text-muted" :title="`${log.old_value ?? '∅'} → ${log.new_value ?? '∅'}`">
                {{ cell(log.old_value) }} → <span class="text-text">{{ cell(log.new_value) }}</span>
              </td>
              <td class="px-3 py-2 text-muted">{{ log.source }}</td>
              <td class="px-3 py-2 text-muted">{{ log.result }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      </template>
    </div>

    <div v-if="pages > 1" class="mt-4 flex items-center justify-center gap-3 text-sm">
      <button
        type="button"
        class="rounded-control border border-border px-3 py-1.5 text-muted transition-colors hover:text-text disabled:opacity-40"
        :disabled="page <= 1"
        @click="goPage(page - 1)"
      >
        上一页
      </button>
      <span class="font-mono text-xs text-muted">{{ page }} / {{ pages }}</span>
      <button
        type="button"
        class="rounded-control border border-border px-3 py-1.5 text-muted transition-colors hover:text-text disabled:opacity-40"
        :disabled="page >= pages"
        @click="goPage(page + 1)"
      >
        下一页
      </button>
    </div>
  </section>
</template>
