<script setup lang="ts">
import { RouterLink } from 'vue-router'

import EmptyState from '@/components/EmptyState.vue'
</script>

<template>
  <section class="mx-auto w-full max-w-4xl px-4 py-6 md:px-6">
    <div class="rounded-card border border-border bg-surface">
      <EmptyState title="页面不存在" description="你访问的地址没有对应的页面。">
        <RouterLink
          to="/library"
          class="inline-flex items-center rounded-control bg-brand px-3.5 py-2 text-sm font-medium text-bg transition-colors hover:bg-brand-600"
        >
          返回资源库
        </RouterLink>
      </EmptyState>
    </div>
  </section>
</template>
