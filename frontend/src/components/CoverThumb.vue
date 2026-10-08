<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { coverApi } from '@/api/endpoints'

const props = withDefaults(
  defineProps<{ trackId: number; hasCover: boolean; version?: number; rounded?: string }>(),
  { version: 0, rounded: 'rounded-control' },
)

const broken = ref(false)
const src = computed(() => `${coverApi.url(props.trackId)}?v=${props.version}`)

watch(
  () => [props.trackId, props.version, props.hasCover],
  () => {
    broken.value = false
  },
)
</script>

<template>
  <span
    class="grid h-full w-full place-items-center overflow-hidden bg-surface-2"
    :class="rounded"
    aria-hidden="true"
  >
    <img
      v-if="hasCover && !broken"
      :src="src"
      alt=""
      loading="lazy"
      class="h-full w-full object-cover"
      @error="broken = true"
    />
    <svg v-else viewBox="0 0 64 64" fill="none" class="h-1/2 w-1/2 max-h-8 max-w-8 text-border">
      <circle cx="32" cy="32" r="26" stroke="currentColor" stroke-width="2" />
      <circle cx="32" cy="32" r="9" stroke="currentColor" stroke-width="2" />
      <circle cx="32" cy="32" r="2.5" fill="currentColor" />
    </svg>
  </span>
</template>
