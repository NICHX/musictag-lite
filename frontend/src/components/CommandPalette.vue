<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const router = useRouter()

const query = ref('')
const activeIndex = ref(0)
const inputRef = ref<HTMLInputElement | null>(null)

const commands = [
  { label: '资源库', to: '/library', hint: '浏览与筛选曲目' },
  { label: '刮削中心', to: '/scrape', hint: '在线匹配元数据与封面' },
  { label: '任务与日志', to: '/tasks', hint: '查看任务进度' },
  { label: '操作日志', to: '/logs', hint: '查看写入前后值' },
  { label: '设置', to: '/settings', hint: '库路径与刮削源' },
]

const filtered = computed(() => {
  const keyword = query.value.trim().toLowerCase()
  if (!keyword) return commands
  return commands.filter(
    (item) => item.label.toLowerCase().includes(keyword) || item.hint.toLowerCase().includes(keyword),
  )
})

watch(filtered, () => {
  activeIndex.value = 0
})

watch(
  () => ui.commandPaletteOpen,
  async (open) => {
    if (open) {
      query.value = ''
      activeIndex.value = 0
      await nextTick()
      inputRef.value?.focus()
    }
  },
)

function close(): void {
  ui.toggleCommandPalette(false)
}

function run(index: number): void {
  const command = filtered.value[index]
  if (!command) return
  void router.push(command.to)
  close()
}

function onKeydown(event: KeyboardEvent): void {
  const total = filtered.value.length
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    if (total) activeIndex.value = (activeIndex.value + 1) % total
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    if (total) activeIndex.value = (activeIndex.value - 1 + total) % total
  } else if (event.key === 'Enter') {
    event.preventDefault()
    run(activeIndex.value)
  } else if (event.key === 'Escape') {
    close()
  }
}
</script>

<template>
  <div
    v-if="ui.commandPaletteOpen"
    class="fixed inset-0 z-[60] flex items-start justify-center bg-black/50 p-4 pt-[12vh] backdrop-blur-sm"
    role="dialog"
    aria-modal="true"
    aria-label="命令面板"
    @click.self="close"
  >
    <div class="w-full max-w-lg overflow-hidden rounded-card border border-border bg-surface shadow-xl">
      <input
        ref="inputRef"
        v-model="query"
        type="text"
        class="w-full border-b border-border bg-transparent px-4 py-3 text-sm text-text outline-none placeholder:text-muted"
        placeholder="输入以跳转或执行（扫描、刮削、切换视图…）"
        @keydown="onKeydown"
      />
      <ul class="max-h-72 overflow-y-auto p-1.5">
        <li v-for="(command, index) in filtered" :key="command.to">
          <button
            type="button"
            class="flex w-full items-center justify-between gap-3 rounded-control px-3 py-2 text-left text-sm transition-colors"
            :class="index === activeIndex ? 'bg-surface-2 text-text' : 'text-muted hover:bg-surface-2'"
            @mouseenter="activeIndex = index"
            @click="run(index)"
          >
            <span>{{ command.label }}</span>
            <span class="text-xs text-muted">{{ command.hint }}</span>
          </button>
        </li>
        <li v-if="!filtered.length" class="px-3 py-6 text-center text-sm text-muted">没有匹配的命令</li>
      </ul>
    </div>
  </div>
</template>
