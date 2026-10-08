<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink } from 'vue-router'

import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const collapsed = computed(() => ui.sidebarCollapsed)

const items = [
  { to: '/library', label: '资源库', icon: 'grid' },
  { to: '/scrape', label: '刮削中心', icon: 'spark' },
  { to: '/organize', label: '整理', icon: 'wand' },
  { to: '/tasks', label: '任务与日志', icon: 'activity' },
  { to: '/logs', label: '操作日志', icon: 'list' },
  { to: '/settings', label: '设置', icon: 'sliders' },
] as const
</script>

<template>
  <div
    v-if="ui.mobileNavOpen"
    class="fixed inset-0 z-40 bg-black/60 md:hidden"
    aria-hidden="true"
    @click="ui.toggleMobileNav(false)"
  />

  <aside
    class="fixed inset-y-0 left-0 z-50 flex h-screen w-60 shrink-0 flex-col border-r border-border bg-surface transition-transform duration-200 md:static md:translate-x-0"
    :class="[ui.mobileNavOpen ? 'translate-x-0' : '-translate-x-full', collapsed ? 'md:w-16' : 'md:w-60']"
  >
    <nav class="flex flex-1 flex-col gap-1 p-2" aria-label="主导航">
      <RouterLink
        v-for="item in items"
        :key="item.to"
        :to="item.to"
        class="group flex items-center gap-3 rounded-control px-3 py-2 text-sm text-muted transition-colors hover:bg-surface-2 hover:text-text"
        active-class="bg-surface-2 text-text"
        @click="ui.toggleMobileNav(false)"
      >
        <span
          class="grid h-5 w-5 shrink-0 place-items-center text-current"
          :class="collapsed && 'md:mx-auto'"
          aria-hidden="true"
        >
          <svg
            v-if="item.icon === 'grid'"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.5"
            class="h-5 w-5"
          >
            <rect x="3" y="3" width="7" height="7" rx="1.5" />
            <rect x="14" y="3" width="7" height="7" rx="1.5" />
            <rect x="3" y="14" width="7" height="7" rx="1.5" />
            <rect x="14" y="14" width="7" height="7" rx="1.5" />
          </svg>
          <svg
            v-else-if="item.icon === 'spark'"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.5"
            class="h-5 w-5"
          >
            <path d="M12 3v4M12 17v4M3 12h4M17 12h4" stroke-linecap="round" />
            <circle cx="12" cy="12" r="3.5" />
          </svg>
          <svg
            v-else-if="item.icon === 'wand'"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.5"
            class="h-5 w-5"
          >
            <path d="M14 4l6 6-9.5 9.5-6-6L14 4z" stroke-linejoin="round" />
            <path d="M4 4l1 2 2 1-2 1-1 2-1-2-2-1 2-1 1-2z" stroke-linejoin="round" />
            <path d="M19 15l.7 1.3L21 17l-1.3.7L19 19l-.7-1.3L17 17l1.3-.7L19 15z" stroke-linejoin="round" />
          </svg>
          <svg
            v-else-if="item.icon === 'activity'"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.5"
            class="h-5 w-5"
          >
            <path d="M3 12h4l2.5-6 4 12L16 12h5" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
          <svg
            v-else-if="item.icon === 'list'"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.5"
            class="h-5 w-5"
          >
            <path d="M4 6h16M4 12h16M4 18h10" stroke-linecap="round" />
          </svg>
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="h-5 w-5">
            <path d="M4 8h10M18 8h2M4 16h4M12 16h8" stroke-linecap="round" />
            <circle cx="16" cy="8" r="2" />
            <circle cx="10" cy="16" r="2" />
          </svg>
        </span>
        <span class="truncate" :class="collapsed && 'md:hidden'">{{ item.label }}</span>
      </RouterLink>
    </nav>

    <div class="border-t border-border p-3" :class="collapsed && 'md:px-2'">
      <button
        type="button"
        class="w-full rounded-control px-2 py-1.5 text-left text-xs text-muted transition-colors hover:bg-surface-2 hover:text-text"
        :title="collapsed ? '展开侧栏' : '折叠侧栏'"
        @click="ui.toggleSidebar()"
      >
        <span :class="collapsed && 'md:hidden'">折叠侧栏</span>
        <span v-if="collapsed" class="md:hidden lg:inline">‹</span>
        <span v-else class="hidden">›</span>
      </button>
      <p class="mt-2 px-2 text-[11px] text-muted" :class="collapsed && 'md:hidden'">MusicTag Lite</p>
    </div>
  </aside>
</template>
