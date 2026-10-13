<script setup lang="ts">
import { computed, ref } from 'vue'

const props = withDefaults(
  defineProps<{ current: number; duration: number; disabled?: boolean }>(),
  { disabled: false },
)
const emit = defineEmits<{ seek: [value: number] }>()

const barEl = ref<HTMLElement | null>(null)
let dragging = false

const percent = computed(() =>
  props.duration > 0 ? Math.min(100, Math.max(0, (props.current / props.duration) * 100)) : 0,
)

/** 点击/拖拽位置 → 目标秒数（整条都可点，命中区高 12px）。 */
function seekAt(event: PointerEvent): void {
  if (props.disabled || props.duration <= 0) return
  const rect = barEl.value?.getBoundingClientRect()
  if (!rect || rect.width <= 0) return
  const ratio = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width))
  emit('seek', ratio * props.duration)
}

function onPointerDown(event: PointerEvent): void {
  if (props.disabled || props.duration <= 0) return
  dragging = true
  ;(event.currentTarget as HTMLElement).setPointerCapture?.(event.pointerId)
  seekAt(event)
}

function onPointerMove(event: PointerEvent): void {
  if (dragging) seekAt(event)
}

function onPointerUp(event: PointerEvent): void {
  if (!dragging) return
  dragging = false
  ;(event.currentTarget as HTMLElement).releasePointerCapture?.(event.pointerId)
}
</script>

<template>
  <div
    ref="barEl"
    class="group relative h-3 min-w-0 flex-1 touch-none select-none"
    :class="disabled ? 'cursor-default' : 'cursor-pointer'"
    role="slider"
    aria-label="播放进度"
    :aria-valuemin="0"
    :aria-valuemax="Math.round(duration)"
    :aria-valuenow="Math.round(current)"
    @pointerdown="onPointerDown"
    @pointermove="onPointerMove"
    @pointerup="onPointerUp"
    @pointercancel="onPointerUp"
  >
    <div class="absolute inset-x-0 top-1/2 h-1 -translate-y-1/2 overflow-hidden rounded-full bg-border">
      <div class="h-full rounded-full bg-accent" :style="{ width: `${percent}%` }" />
    </div>
    <div
      class="absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-accent opacity-0 transition-opacity group-hover:opacity-100"
      :style="{ left: `${percent}%` }"
      aria-hidden="true"
    />
  </div>
</template>
