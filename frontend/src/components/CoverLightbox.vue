<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'

import { coverApi } from '@/api/endpoints'

const props = defineProps<{ trackId: number; title?: string | null; artist?: string | null }>()
const emit = defineEmits<{ close: [] }>()

function onKey(event: KeyboardEvent): void {
  if (event.key === 'Escape') emit('close')
}

onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div
    class="fixed inset-0 z-[60] flex flex-col items-center justify-center gap-4 bg-black/80 p-6 backdrop-blur-sm"
    role="dialog"
    aria-modal="true"
    aria-label="查看封面"
    @click="emit('close')"
  >
    <img
      :src="coverApi.url(trackId)"
      :alt="title || '封面'"
      class="max-h-[78vh] max-w-[88vw] rounded-card object-contain shadow-2xl"
      @click.stop
    />
    <div class="flex items-center gap-3 text-center" @click.stop>
      <span class="min-w-0">
        <span class="block truncate text-sm text-white">{{ title || '（无标题）' }}</span>
        <span v-if="artist" class="block truncate text-xs text-white/60">{{ artist }}</span>
      </span>
      <button
        type="button"
        class="shrink-0 rounded-control border border-white/25 px-3 py-1 text-xs text-white/85 transition-colors hover:bg-white/10"
        @click="emit('close')"
      >
        关闭
      </button>
    </div>
  </div>
</template>
