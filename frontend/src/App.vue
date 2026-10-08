<script setup lang="ts">
import { onMounted } from 'vue'

import AppShell from '@/components/AppShell.vue'
import { useTaskStore } from '@/stores/tasks'

const tasks = useTaskStore()

onMounted(() => {
  tasks.connect()
  void tasks.refresh()
})
</script>

<template>
  <AppShell>
    <RouterView />
  </AppShell>
</template>
