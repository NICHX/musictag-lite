<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { api } from '@/api/client'
import type { Health, Library, Provider } from '@/api/types'

const libraries = ref<Library[]>([])
const providers = ref<Provider[]>([])
const health = ref<Health | null>(null)
const error = ref<string | null>(null)
const creating = ref(false)
const newName = ref('')
const newPath = ref('')

async function load(): Promise<void> {
  error.value = null
  try {
    const [libs, provs, status] = await Promise.all([
      api.get<Library[]>('/libraries'),
      api.get<Provider[]>('/providers'),
      api.get<Health>('/health'),
    ])
    libraries.value = libs
    providers.value = provs
    health.value = status
  } catch (e) {
    error.value = e instanceof Error ? e.message : '加载失败'
  }
}

async function addLibrary(): Promise<void> {
  const name = newName.value.trim()
  const rootPath = newPath.value.trim()
  if (!name || !rootPath || creating.value) return
  creating.value = true
  error.value = null
  try {
    const created = await api.post<Library>('/libraries', { name, root_path: rootPath })
    libraries.value = [...libraries.value, created]
    newName.value = ''
    newPath.value = ''
  } catch (e) {
    error.value = e instanceof Error ? e.message : '创建失败'
  } finally {
    creating.value = false
  }
}

async function removeLibrary(library: Library): Promise<void> {
  try {
    await api.delete(`/libraries/${library.id}`)
    libraries.value = libraries.value.filter((item) => item.id !== library.id)
  } catch (e) {
    error.value = e instanceof Error ? e.message : '删除失败'
  }
}

async function toggleProvider(provider: Provider): Promise<void> {
  try {
    const updated = await api.patch<Provider>(`/providers/${provider.key}`, { enabled: !provider.enabled })
    providers.value = providers.value.map((item) => (item.key === updated.key ? updated : item))
  } catch (e) {
    error.value = e instanceof Error ? e.message : '更新失败'
  }
}

onMounted(load)
</script>

<template>
  <section class="mx-auto w-full max-w-4xl px-4 py-6 md:px-6">
    <h1 class="font-display text-2xl font-semibold tracking-tight">设置</h1>
    <p class="mt-1 text-sm text-muted">库路径、刮削源与运行状态</p>

    <p v-if="error" class="mt-4 rounded-control border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
      {{ error }}
    </p>

    <div class="mt-6 space-y-6">
      <section class="rounded-card border border-border bg-surface p-4">
        <h2 class="text-base font-medium">音乐库</h2>
        <p class="mt-1 text-xs text-muted">库根目录为路径白名单，所有文件访问都会校验是否位于其内。</p>

        <ul class="mt-3 divide-y divide-border/60">
          <li v-for="library in libraries" :key="library.id" class="flex items-center gap-3 py-2 text-sm">
            <span class="min-w-0 flex-1">
              <span class="block truncate">{{ library.name }}</span>
              <span class="block truncate font-mono text-xs text-muted">{{ library.root_path }}</span>
            </span>
            <span class="text-xs text-muted">{{ library.track_count }} 首</span>
            <button
              type="button"
              class="rounded-control border border-border px-2 py-1 text-xs text-muted transition-colors hover:border-danger/60 hover:text-danger"
              @click="removeLibrary(library)"
            >
              移除
            </button>
          </li>
          <li v-if="!libraries.length" class="py-3 text-sm text-muted">尚未配置任何音乐库。</li>
        </ul>

        <form class="mt-4 flex flex-col gap-2 sm:flex-row" @submit.prevent="addLibrary">
          <input
            v-model="newName"
            type="text"
            placeholder="库名称"
            class="rounded-control border border-border bg-bg px-3 py-1.5 text-sm text-text outline-none placeholder:text-muted focus:border-brand sm:w-40"
          />
          <input
            v-model="newPath"
            type="text"
            placeholder="服务器上的绝对路径，如 /music"
            class="min-w-0 flex-1 rounded-control border border-border bg-bg px-3 py-1.5 font-mono text-sm text-text outline-none placeholder:text-muted focus:border-brand"
          />
          <button
            type="submit"
            class="rounded-control bg-brand px-3.5 py-1.5 text-sm font-medium text-bg transition-colors hover:bg-brand-600 disabled:opacity-50"
            :disabled="creating"
          >
            添加
          </button>
        </form>
        <p class="mt-2 text-xs text-muted">已可添加库；目录扫描（增量）与曲目落库将在 M1 启用。</p>
      </section>

      <section class="rounded-card border border-border bg-surface p-4">
        <h2 class="text-base font-medium">刮削源</h2>
        <p class="mt-1 text-xs text-muted">默认仅启用开放数据源；高风险源不内置，以社区插件形式提供。</p>

        <ul class="mt-3 divide-y divide-border/60">
          <li v-for="provider in providers" :key="provider.key" class="flex items-center gap-3 py-2.5 text-sm">
            <span class="min-w-0 flex-1">
              <span class="block">{{ provider.name }}</span>
              <span class="block font-mono text-xs text-muted">
                {{ provider.key }} · {{ provider.capabilities.join(' / ') || '—' }} · 优先级 {{ provider.priority }}
              </span>
            </span>
            <button
              type="button"
              role="switch"
              :aria-checked="provider.enabled"
              class="relative h-5 w-9 rounded-full border transition-colors"
              :class="provider.enabled ? 'border-brand bg-brand/30' : 'border-border bg-surface-2'"
              @click="toggleProvider(provider)"
            >
              <span
                class="absolute top-0.5 h-3.5 w-3.5 rounded-full transition-all"
                :class="provider.enabled ? 'left-4 bg-brand' : 'left-0.5 bg-muted'"
              />
            </button>
          </li>
        </ul>
      </section>

      <section class="rounded-card border border-border bg-surface p-4">
        <h2 class="text-base font-medium">运行状态</h2>
        <dl v-if="health" class="mt-3 grid grid-cols-2 gap-y-2 text-sm sm:grid-cols-4">
          <div>
            <dt class="text-xs text-muted">应用</dt>
            <dd class="font-mono text-xs">{{ health.name }}</dd>
          </div>
          <div>
            <dt class="text-xs text-muted">版本</dt>
            <dd class="font-mono text-xs">{{ health.version }}</dd>
          </div>
          <div>
            <dt class="text-xs text-muted">环境</dt>
            <dd class="font-mono text-xs">{{ health.environment }}</dd>
          </div>
          <div>
            <dt class="text-xs text-muted">ffmpeg</dt>
            <dd class="font-mono text-xs" :class="health.ffmpeg ? 'text-success' : 'text-muted'">
              {{ health.ffmpeg ? '已检测' : '未安装（核心功能不受影响）' }}
            </dd>
          </div>
        </dl>
        <p v-else class="mt-3 text-sm text-muted">加载中…</p>
      </section>
    </div>
  </section>
</template>
