<script setup lang="ts">
withDefaults(defineProps<{ title: string; description?: string }>(), { description: '' })
</script>

<template>
  <div class="flex flex-col items-center justify-center px-6 py-16 text-center">
    <svg class="mb-5 h-16 w-16 text-border" viewBox="0 0 64 64" fill="none" aria-hidden="true">
      <circle cx="32" cy="32" r="30" stroke="currentColor" stroke-width="1.5" />
      <circle cx="32" cy="32" r="19" stroke="currentColor" stroke-width="1" />
      <circle cx="32" cy="32" r="11" stroke="currentColor" stroke-width="1.5" />
      <circle cx="32" cy="32" r="2.5" fill="currentColor" />
    </svg>
    <h2 class="text-lg font-medium text-text">{{ title }}</h2>
    <p v-if="description" class="mt-2 max-w-md text-sm leading-relaxed text-muted">{{ description }}</p>
    <div class="mt-5">
      <slot />
    </div>
  </div>
</template>
