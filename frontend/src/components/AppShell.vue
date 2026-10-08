<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'

import CommandPalette from './CommandPalette.vue'
import SideNav from './SideNav.vue'
import TaskCenter from './TaskCenter.vue'
import TopBar from './TopBar.vue'
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()

function onKeydown(event: KeyboardEvent): void {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault()
    ui.toggleCommandPalette()
  }
  if (event.key === 'Escape') {
    ui.toggleCommandPalette(false)
  }
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <div class="flex min-h-screen bg-bg text-text">
    <SideNav />
    <div class="flex min-w-0 flex-1 flex-col">
      <TopBar />
      <main class="min-w-0 flex-1 overflow-y-auto">
        <slot />
      </main>
    </div>
    <TaskCenter />
    <CommandPalette />
  </div>
</template>
