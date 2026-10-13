<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import CommandPalette from './CommandPalette.vue'
import SideNav from './SideNav.vue'
import TaskCenter from './TaskCenter.vue'
import TopBar from './TopBar.vue'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()
const route = useRoute()
const mainEl = ref<HTMLElement | null>(null)

function onKeydown(event: KeyboardEvent): void {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault()
    ui.toggleCommandPalette()
  }
  if (event.key === 'Escape') {
    ui.toggleCommandPalette(false)
  }
}

// 主区域是内部滚动容器：切路由时把内容滚回顶部（等价于传统页面跳转的复位）
watch(
  () => route.fullPath,
  () => mainEl.value?.scrollTo({ top: 0 }),
)

onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <div class="flex h-screen overflow-hidden bg-bg text-text">
    <SideNav />
    <div class="flex min-h-0 min-w-0 flex-1 flex-col">
      <TopBar />
      <main ref="mainEl" class="min-h-0 min-w-0 flex-1 overflow-y-auto">
        <slot />
      </main>
    </div>
    <TaskCenter />
    <CommandPalette />
  </div>
</template>
