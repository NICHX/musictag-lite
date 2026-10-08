<script setup lang="ts">
import EmptyState from '@/components/EmptyState.vue'
</script>

<template>
  <section class="mx-auto w-full max-w-6xl px-4 py-6 md:px-6">
    <h1 class="font-display text-2xl font-semibold tracking-tight">刮削中心</h1>
    <p class="mt-1 text-sm text-muted">插件式数据源：MusicBrainz · Cover Art Archive · LRCLIB</p>

    <div class="mt-5 rounded-card border border-border bg-surface">
      <EmptyState
        title="刮削匹配将在 M1 开放"
        description="届时左侧为待处理队列，右侧为多源候选卡片，支持字段差异对比与「仅补空值」应用。"
      />
    </div>
  </section>
</template>
