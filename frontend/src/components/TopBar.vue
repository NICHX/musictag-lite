<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'

import { useTaskStore } from '@/stores/tasks'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const tasks = useTaskStore()

const runningCount = computed(
  () => tasks.tasks.filter((task) => task.status === 'running' || task.status === 'queued').length,
)
</script>

<template>
  <header
    class="sticky top-0 z-30 flex items-center gap-3 border-b border-border bg-bg/90 px-3 py-2.5 backdrop-blur md:px-4"
  >
    <button
      type="button"
      class="grid h-9 w-9 place-items-center rounded-control text-muted transition-colors hover:bg-surface-2 hover:text-text md:hidden"
      aria-label="打开导航"
      @click="ui.toggleMobileNav(true)"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="h-5 w-5">
        <path d="M4 7h16M4 12h16M4 17h16" stroke-linecap="round" />
      </svg>
    </button>

    <RouterLink to="/library" class="flex items-center gap-2">
      <span class="grid h-7 w-7 place-items-center rounded-full bg-brand text-bg" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" class="h-4 w-4">
          <circle cx="12" cy="12" r="8" />
          <circle cx="12" cy="12" r="2.4" fill="currentColor" stroke="none" />
        </svg>
      </span>
      <span class="font-display text-[15px] font-semibold tracking-tight">
        MusicTag<span class="text-muted"> Lite</span>
      </span>
    </RouterLink>

    <button
      type="button"
      class="ml-2 hidden min-w-0 flex-1 items-center gap-2 rounded-control border border-border bg-surface px-3 py-1.5 text-left text-sm text-muted transition-colors hover:border-brand/60 hover:text-text sm:flex md:max-w-md"
      @click="ui.toggleCommandPalette(true)"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="h-4 w-4 shrink-0">
        <circle cx="11" cy="11" r="6.5" />
        <path d="m16 16 4 4" stroke-linecap="round" />
      </svg>
      <span class="truncate">搜索曲目、专辑、艺术家…</span>
      <kbd class="ml-auto rounded border border-border px-1.5 py-0.5 font-mono text-[10px] text-muted">⌘K</kbd>
    </button>

    <div class="ml-auto flex items-center gap-1.5">
      <span
        class="hidden items-center gap-1.5 rounded-full border border-border bg-surface px-2.5 py-1 text-[11px] text-muted lg:flex"
        title="服务状态"
      >
        <span class="h-1.5 w-1.5 rounded-full bg-success" aria-hidden="true" />
        就绪
      </span>

      <button
        type="button"
        class="relative grid h-9 w-9 place-items-center rounded-control text-muted transition-colors hover:bg-surface-2 hover:text-text"
        aria-label="任务中心"
        :aria-expanded="ui.taskCenterOpen"
        @click="ui.toggleTaskCenter()"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="h-5 w-5">
          <path d="M3 12h4l2.5-6 4 12L16 12h5" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
        <span
          v-if="runningCount"
          class="absolute -right-0.5 -top-0.5 grid h-4 min-w-4 place-items-center rounded-full bg-brand px-1 text-[10px] font-medium text-bg"
        >
          {{ runningCount }}
        </span>
      </button>

      <button
        type="button"
        class="grid h-9 w-9 place-items-center rounded-control text-muted transition-colors hover:bg-surface-2 hover:text-text"
        :aria-label="ui.theme === 'dark' ? '切换到浅色主题' : '切换到深色主题'"
        @click="ui.toggleTheme()"
      >
        <svg
          v-if="ui.theme === 'dark'"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
          class="h-5 w-5"
        >
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5 19 19M19 5l-1.5 1.5M6.5 17.5 5 19" stroke-linecap="round" />
        </svg>
        <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="h-5 w-5">
          <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z" stroke-linejoin="round" />
        </svg>
      </button>

      <RouterLink
        to="/settings"
        class="grid h-9 w-9 place-items-center rounded-control text-muted transition-colors hover:bg-surface-2 hover:text-text"
        aria-label="设置"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="h-5 w-5">
          <circle cx="12" cy="12" r="3" />
          <path
            d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-2.9 1.2V21a2 2 0 1 1-4 0v-.1A1.7 1.7 0 0 0 7 19.2l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.7 1.7 0 0 0 3 13.6H3a2 2 0 1 1 0-4h.1A1.7 1.7 0 0 0 4.8 7l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1A1.7 1.7 0 0 0 10 3.1V3a2 2 0 1 1 4 0v.1A1.7 1.7 0 0 0 17 4.8l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0 1.2 2.9H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z"
            stroke-linejoin="round"
          />
        </svg>
      </RouterLink>
    </div>
  </header>
</template>
