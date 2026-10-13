<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { api } from '@/api/client'
import { acoustidApi, aiApi, apiTokenApi, extensionApi } from '@/api/endpoints'
import type {
  AISettings,
  AISettingsUpdate,
  AcoustIDSettings,
  AcoustIDSettingsUpdate,
  ApiToken,
  Extension,
  Health,
  Library,
  Provider,
} from '@/api/types'

const libraries = ref<Library[]>([])
const providers = ref<Provider[]>([])
const health = ref<Health | null>(null)
const error = ref<string | null>(null)
const notice = ref<string | null>(null)
const creating = ref(false)
const newName = ref('')
const newPath = ref('')

const ai = ref<AISettings | null>(null)
const aiForm = ref({ enabled: false, base_url: '', model: '', api_key: '' })
const aiSaving = ref(false)
const aiMessage = ref<string | null>(null)

const acoustid = ref<AcoustIDSettings | null>(null)
const acoustidKey = ref('')
const acoustidSaving = ref(false)
const acoustidMessage = ref<string | null>(null)

const installedExtensions = ref<Extension[]>([])
const catalogExtensions = ref<Extension[]>([])
const extensionBusy = ref(false)
const extensionMessage = ref<string | null>(null)
const zipInput = ref<HTMLInputElement | null>(null)

const token = ref<ApiToken | null>(null)
const tokenSaving = ref(false)
const tokenMessage = ref<string | null>(null)
const tokenRevealed = ref(false)
const tokenCopied = ref(false)

function syncAiForm(data: AISettings): void {
  ai.value = data
  aiForm.value = { enabled: data.enabled, base_url: data.base_url, model: data.model, api_key: '' }
}

async function load(): Promise<void> {
  error.value = null
  try {
    const [libs, provs, status, aiSettings, acoustidSettings, exts, apiToken] = await Promise.all([
      api.get<Library[]>('/libraries'),
      api.get<Provider[]>('/providers'),
      api.get<Health>('/health'),
      aiApi.get(),
      acoustidApi.get(),
      extensionApi.list(),
      apiTokenApi.get(),
    ])
    libraries.value = libs
    providers.value = provs
    health.value = status
    syncAiForm(aiSettings)
    acoustid.value = acoustidSettings
    installedExtensions.value = exts.installed
    catalogExtensions.value = exts.catalog
    token.value = apiToken
  } catch (e) {
    error.value = e instanceof Error ? e.message : '加载失败'
  }
}

function applyExtensions(list: { installed: Extension[]; catalog: Extension[] }): void {
  installedExtensions.value = list.installed
  catalogExtensions.value = list.catalog
}

async function installExtension(key: string): Promise<void> {
  extensionBusy.value = true
  error.value = null
  extensionMessage.value = null
  try {
    const info = await extensionApi.installFromCatalog(key)
    extensionMessage.value = `已安装扩展「${info.name}」，到「刮削源」中启用即可使用`
    applyExtensions(await extensionApi.list())
  } catch (e) {
    error.value = e instanceof Error ? e.message : '安装失败'
  } finally {
    extensionBusy.value = false
  }
}

async function uninstallExtension(key: string): Promise<void> {
  extensionBusy.value = true
  error.value = null
  extensionMessage.value = null
  try {
    await extensionApi.uninstall(key)
    extensionMessage.value = '已卸载扩展'
    applyExtensions(await extensionApi.list())
  } catch (e) {
    error.value = e instanceof Error ? e.message : '卸载失败'
  } finally {
    extensionBusy.value = false
  }
}

async function onZipSelected(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  extensionBusy.value = true
  error.value = null
  extensionMessage.value = null
  try {
    const info = await extensionApi.installZip(file)
    extensionMessage.value = `已安装扩展「${info.name}」`
    applyExtensions(await extensionApi.list())
  } catch (e) {
    error.value = e instanceof Error ? e.message : '安装失败'
  } finally {
    extensionBusy.value = false
  }
}

async function saveToken(body: { enabled?: boolean; regenerate?: boolean }): Promise<void> {
  tokenSaving.value = true
  error.value = null
  tokenMessage.value = null
  try {
    token.value = await apiTokenApi.update(body)
    tokenMessage.value = body.regenerate ? '已重新生成令牌' : '已保存'
  } catch (e) {
    error.value = e instanceof Error ? e.message : '保存失败'
  } finally {
    tokenSaving.value = false
  }
}

async function copyToken(): Promise<void> {
  if (!token.value?.token) return
  try {
    await navigator.clipboard.writeText(token.value.token)
    tokenCopied.value = true
    window.setTimeout(() => (tokenCopied.value = false), 1500)
  } catch {
    error.value = '复制失败，请手动选择复制'
  }
}

const openApiBase = computed(() =>
  token.value ? `${window.location.origin}${token.value.base_url}` : '',
)

async function saveAi(extra: AISettingsUpdate = {}): Promise<void> {
  aiSaving.value = true
  error.value = null
  aiMessage.value = null
  try {
    const body: AISettingsUpdate = {
      enabled: aiForm.value.enabled,
      base_url: aiForm.value.base_url.trim(),
      model: aiForm.value.model.trim(),
      ...extra,
    }
    // 留空表示不改动密钥；如需清除请用「清除密钥」
    if (!extra.api_key && aiForm.value.api_key.trim()) {
      body.api_key = aiForm.value.api_key.trim()
    }
    syncAiForm(await aiApi.update(body))
    aiMessage.value = '已保存'
  } catch (e) {
    error.value = e instanceof Error ? e.message : '保存失败'
  } finally {
    aiSaving.value = false
  }
}

async function saveAcoustid(extra: AcoustIDSettingsUpdate = {}): Promise<void> {
  acoustidSaving.value = true
  error.value = null
  acoustidMessage.value = null
  try {
    const body: AcoustIDSettingsUpdate = { ...extra }
    // 留空表示不改动密钥；如需清除请用「清除密钥」
    if (!('api_key' in extra) && acoustidKey.value.trim()) {
      body.api_key = acoustidKey.value.trim()
    }
    acoustid.value = await acoustidApi.update(body)
    acoustidKey.value = ''
    acoustidMessage.value = '已保存'
  } catch (e) {
    error.value = e instanceof Error ? e.message : '保存失败'
  } finally {
    acoustidSaving.value = false
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
    notice.value = `已移除「${library.name}」及其 ${library.track_count} 条曲目索引（磁盘文件未改动）`
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

/** 拖动排序：生效顺序即列表顺序（优先级按 10/20/30… 重新编号）。 */
const draggingIndex = ref<number | null>(null)

const providerList = computed(() =>
  [...providers.value].sort((a, b) => a.priority - b.priority || a.key.localeCompare(b.key)),
)

async function onDrop(targetIndex: number): Promise<void> {
  const from = draggingIndex.value
  draggingIndex.value = null
  if (from === null || from === targetIndex) return
  const list = [...providerList.value]
  const [moved] = list.splice(from, 1)
  list.splice(targetIndex, 0, moved)
  const before = new Map(providers.value.map((item) => [item.key, item.priority]))
  const renumbered = list.map((item, index) => ({ ...item, priority: (index + 1) * 10 }))
  providers.value = renumbered
  const changed = renumbered.filter((item) => before.get(item.key) !== item.priority)
  if (!changed.length) return
  try {
    await Promise.all(
      changed.map((item) => api.patch<Provider>(`/providers/${item.key}`, { priority: item.priority })),
    )
    notice.value = `已按新顺序更新 ${changed.length} 个数据源的优先级`
  } catch (e) {
    error.value = e instanceof Error ? e.message : '保存优先级失败'
    await load()
  }
}

onMounted(load)
</script>

<template>
  <section class="mx-auto w-full max-w-[110rem] px-4 py-6 md:px-6">
    <h1 class="font-display text-2xl font-semibold tracking-tight">设置</h1>
    <p class="mt-1 text-sm text-muted">库路径、刮削源、AI 辅助与运行状态</p>

    <p v-if="error" class="mt-4 rounded-control border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
      {{ error }}
    </p>
    <p v-if="notice" class="mt-4 rounded-control border border-info/40 bg-info/10 px-3 py-2 text-sm text-info">
      {{ notice }}
    </p>

    <div class="mt-6 gap-4 xl:columns-2">
      <section class="mb-4 break-inside-avoid rounded-card border border-border bg-surface p-4">
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
        <p class="mt-2 text-xs text-muted">扫描会增量识别新文件与变更，已完成落库与标签读取。</p>
      </section>

      <section class="mb-4 break-inside-avoid rounded-card border border-border bg-surface p-4">
        <h2 class="text-base font-medium">刮削源</h2>
        <p class="mt-1 text-xs text-muted">
          默认仅启用开放数据源；高风险源不内置，以「扩展」形式提供，安装后在此启用。
          <span class="text-muted">按住右侧手柄拖动排序</span>：越靠前越先使用，同时决定元数据检索顺序与歌词回退顺序。
        </p>

        <ul class="mt-3 divide-y divide-border/60">
          <li
            v-for="(provider, index) in providerList"
            :key="provider.key"
            class="flex items-center gap-3 py-2.5 text-sm transition-opacity"
            :class="draggingIndex === index ? 'opacity-40' : ''"
            draggable="true"
            @dragstart="draggingIndex = index"
            @dragover.prevent
            @drop="onDrop(index)"
            @dragend="draggingIndex = null"
          >
            <span class="w-6 shrink-0 text-center font-mono text-xs text-muted">
              {{ index + 1 }}
            </span>
            <span class="min-w-0 flex-1">
              <span class="block">{{ provider.name }}</span>
              <span class="block truncate font-mono text-xs text-muted">
                {{ provider.key }} · {{ provider.capabilities.join(' / ') || '—' }}
              </span>
            </span>
            <button
              type="button"
              role="switch"
              :aria-checked="provider.enabled"
              class="relative h-5 w-9 shrink-0 rounded-full border transition-colors"
              :class="provider.enabled ? 'border-brand bg-brand/30' : 'border-border bg-surface-2'"
              @click="toggleProvider(provider)"
            >
              <span
                class="absolute top-0.5 h-3.5 w-3.5 rounded-full transition-all"
                :class="provider.enabled ? 'left-4 bg-brand' : 'left-0.5 bg-muted'"
              />
            </button>
            <span
              class="shrink-0 cursor-grab select-none rounded-control p-1 text-muted transition-colors hover:bg-surface-2 hover:text-text active:cursor-grabbing"
              title="拖动调整顺序"
              aria-hidden="true"
            >
              <svg viewBox="0 0 24 24" fill="currentColor" class="h-4 w-4">
                <circle cx="9" cy="6" r="1.6" />
                <circle cx="15" cy="6" r="1.6" />
                <circle cx="9" cy="12" r="1.6" />
                <circle cx="15" cy="12" r="1.6" />
                <circle cx="9" cy="18" r="1.6" />
                <circle cx="15" cy="18" r="1.6" />
              </svg>
            </span>
          </li>
        </ul>
      </section>

      <section class="mb-4 break-inside-avoid rounded-card border border-border bg-surface p-4">
        <div class="flex items-start justify-between gap-3">
          <div>
            <h2 class="text-base font-medium">扩展</h2>
            <p class="mt-1 text-xs text-muted">
              刮削源以可安装「扩展」形式分发：安装后在「刮削源」中启用即可使用。卸载会同时移除其数据源与配置。
            </p>
          </div>
          <button
            type="button"
            class="shrink-0 rounded-control border border-border px-2.5 py-1 text-xs text-muted transition-colors hover:border-brand hover:text-text disabled:opacity-50"
            :disabled="extensionBusy"
            @click="zipInput?.click()"
          >
            上传安装
          </button>
          <input ref="zipInput" type="file" accept=".zip" class="hidden" @change="onZipSelected" />
        </div>

        <ul class="mt-3 divide-y divide-border/60">
          <li
            v-for="ext in catalogExtensions"
            :key="ext.key"
            class="flex items-start gap-3 py-2.5 text-sm"
          >
            <span class="min-w-0 flex-1">
              <span class="flex items-center gap-2">
                <span class="block truncate">{{ ext.name }}</span>
                <span class="font-mono text-xs text-muted">v{{ ext.version }}</span>
                <span
                  v-if="ext.installed"
                  class="rounded-full border border-brand/40 bg-brand/10 px-1.5 py-0.5 text-[10px] text-brand"
                >
                  已安装
                </span>
              </span>
              <span v-if="ext.description" class="mt-0.5 block text-xs text-muted">
                {{ ext.description }}
              </span>
            </span>
            <button
              v-if="!ext.installed"
              type="button"
              class="shrink-0 rounded-control bg-brand px-2.5 py-1 text-xs font-medium text-bg transition-colors hover:bg-brand-600 disabled:opacity-50"
              :disabled="extensionBusy"
              @click="installExtension(ext.key)"
            >
              安装
            </button>
            <button
              v-else
              type="button"
              class="shrink-0 rounded-control border border-border px-2.5 py-1 text-xs text-muted transition-colors hover:border-danger/60 hover:text-danger disabled:opacity-50"
              :disabled="extensionBusy"
              @click="uninstallExtension(ext.key)"
            >
              卸载
            </button>
          </li>
          <li v-if="!catalogExtensions.length" class="py-3 text-sm text-muted">暂无可安装扩展。</li>
        </ul>

        <ul
          v-if="installedExtensions.some((item) => !item.builtin)"
          class="mt-2 divide-y divide-border/60"
        >
          <li
            v-for="ext in installedExtensions.filter((item) => !item.builtin)"
            :key="ext.key"
            class="flex items-center gap-3 py-2 text-sm"
          >
            <span class="min-w-0 flex-1">
              <span class="block truncate">{{ ext.name }}</span>
              <span class="block truncate font-mono text-xs text-muted">
                {{ ext.key }} · {{ ext.providers.join(' / ') || '—' }}
              </span>
            </span>
            <button
              type="button"
              class="shrink-0 rounded-control border border-border px-2.5 py-1 text-xs text-muted transition-colors hover:border-danger/60 hover:text-danger disabled:opacity-50"
              :disabled="extensionBusy"
              @click="uninstallExtension(ext.key)"
            >
              卸载
            </button>
          </li>
        </ul>
        <p v-if="extensionMessage" class="mt-2 text-xs text-success">{{ extensionMessage }}</p>
      </section>

      <section class="mb-4 break-inside-avoid rounded-card border border-border bg-surface p-4">
        <div class="flex items-start justify-between gap-3">
          <div>
            <h2 class="text-base font-medium">AI 辅助识别</h2>
            <p class="mt-1 text-xs text-muted">
              可选：由模型把复杂文件名解析为标签。默认关闭；只发送文件名字符串（不含路径与音频）；
              仅在你点击「AI 解析」时调用，不会自动上传。兼容任意 OpenAI 接口。
            </p>
          </div>
          <button
            type="button"
            role="switch"
            :aria-checked="aiForm.enabled"
            aria-label="启用 AI 辅助"
            class="relative mt-1 h-5 w-9 shrink-0 rounded-full border transition-colors"
            :class="aiForm.enabled ? 'border-brand bg-brand/30' : 'border-border bg-surface-2'"
            @click="aiForm.enabled = !aiForm.enabled"
          >
            <span
              class="absolute top-0.5 h-3.5 w-3.5 rounded-full transition-all"
              :class="aiForm.enabled ? 'left-4 bg-brand' : 'left-0.5 bg-muted'"
            />
          </button>
        </div>

        <div class="mt-4 grid gap-3 sm:grid-cols-2">
          <label class="flex flex-col gap-1 text-xs text-muted">
            Base URL
            <input
              v-model="aiForm.base_url"
              type="text"
              placeholder="https://api.openai.com/v1"
              class="rounded-control border border-border bg-bg px-2.5 py-1.5 font-mono text-sm text-text outline-none placeholder:text-muted focus:border-brand"
            />
          </label>
          <label class="flex flex-col gap-1 text-xs text-muted">
            模型
            <input
              v-model="aiForm.model"
              type="text"
              placeholder="gpt-4o-mini"
              class="rounded-control border border-border bg-bg px-2.5 py-1.5 font-mono text-sm text-text outline-none placeholder:text-muted focus:border-brand"
            />
          </label>
          <label class="flex flex-col gap-1 text-xs text-muted sm:col-span-2">
            API Key
            <input
              v-model="aiForm.api_key"
              type="password"
              autocomplete="off"
              :placeholder="
                ai?.has_api_key ? `已配置（${ai.api_key_masked}），留空表示不修改` : 'sk-…'
              "
              class="rounded-control border border-border bg-bg px-2.5 py-1.5 font-mono text-sm text-text outline-none placeholder:text-muted focus:border-brand"
            />
          </label>
        </div>

        <div class="mt-3 flex flex-wrap items-center gap-3">
          <button
            type="button"
            class="rounded-control bg-brand px-3.5 py-1.5 text-sm font-medium text-bg transition-colors hover:bg-brand-600 disabled:opacity-50"
            :disabled="aiSaving"
            @click="saveAi()"
          >
            {{ aiSaving ? '保存中…' : '保存设置' }}
          </button>
          <button
            v-if="ai?.has_api_key"
            type="button"
            class="rounded-control border border-border px-3 py-1.5 text-sm text-muted transition-colors hover:border-danger/60 hover:text-danger disabled:opacity-50"
            :disabled="aiSaving"
            @click="saveAi({ enabled: false, api_key: '' })"
          >
            清除密钥
          </button>
          <span v-if="aiMessage" class="text-xs text-success">{{ aiMessage }}</span>
          <span
            class="ml-auto text-xs"
            :class="ai?.available ? 'text-success' : 'text-muted'"
          >
            {{ ai?.available ? '已启用 · 检查器将出现「AI 解析」' : '未启用' }}
          </span>
        </div>
      </section>

      <section class="mb-4 break-inside-avoid rounded-card border border-border bg-surface p-4">
        <div class="flex items-start justify-between gap-3">
          <div>
            <h2 class="text-base font-medium">指纹识别（AcoustID）</h2>
            <p class="mt-1 text-xs text-muted">
              可选：对无标签、文件名混乱的曲目用音频指纹识别。指纹在本地（fpcalc）计算，
              仅发送指纹与时长到 AcoustID，不上传音频本体；需先申请免费的 AcoustID API Key。
            </p>
          </div>
          <span
            class="mt-1 shrink-0 text-xs"
            :class="acoustid?.available ? 'text-success' : 'text-muted'"
          >
            {{ acoustid?.available ? '已配置' : '未配置' }}
          </span>
        </div>

        <label class="mt-4 flex flex-col gap-1 text-xs text-muted">
          API Key
          <input
            v-model="acoustidKey"
            type="password"
            autocomplete="off"
            :placeholder="
              acoustid?.has_api_key
                ? `已配置（${acoustid.api_key_masked}），留空表示不修改`
                : 'AcoustID API Key'
            "
            class="rounded-control border border-border bg-bg px-2.5 py-1.5 font-mono text-sm text-text outline-none placeholder:text-muted focus:border-brand"
          />
        </label>

        <div class="mt-3 flex flex-wrap items-center gap-3">
          <button
            type="button"
            class="rounded-control bg-brand px-3.5 py-1.5 text-sm font-medium text-bg transition-colors hover:bg-brand-600 disabled:opacity-50"
            :disabled="acoustidSaving"
            @click="saveAcoustid()"
          >
            {{ acoustidSaving ? '保存中…' : '保存设置' }}
          </button>
          <button
            v-if="acoustid?.has_api_key"
            type="button"
            class="rounded-control border border-border px-3 py-1.5 text-sm text-muted transition-colors hover:border-danger/60 hover:text-danger disabled:opacity-50"
            :disabled="acoustidSaving"
            @click="saveAcoustid({ api_key: '' })"
          >
            清除密钥
          </button>
          <span v-if="acoustidMessage" class="text-xs text-success">{{ acoustidMessage }}</span>
        </div>
        <p class="mt-2 text-xs text-muted">
          在「刮削源」中启用 AcoustID 后，刮削搜索无命中时会自动用指纹兜底；也可在刮削页手动点「指纹识别」。
        </p>
      </section>

      <section class="mb-4 break-inside-avoid rounded-card border border-border bg-surface p-4">
        <div class="flex items-start justify-between gap-3">
          <div>
            <h2 class="text-base font-medium">对外 API</h2>
            <p class="mt-1 text-xs text-muted">
              供外部系统（Navidrome / 脚本 / 自建前端 / 智能音箱等）集成的接口，统一前缀
              <span class="font-mono">/api/open</span>：开放浏览、匹配（发起检索 / 返回候选 / 写入结果）
              与单条写入；库管理、数据源配置、批量任务等不开放。所有请求需携带下方 Token。
            </p>
          </div>
          <button
            type="button"
            role="switch"
            :aria-checked="token?.enabled ?? false"
            aria-label="启用对外 API"
            class="relative mt-1 h-5 w-9 shrink-0 rounded-full border transition-colors"
            :class="token?.enabled ? 'border-brand bg-brand/30' : 'border-border bg-surface-2'"
            :disabled="tokenSaving"
            @click="saveToken({ enabled: !token?.enabled })"
          >
            <span
              class="absolute top-0.5 h-3.5 w-3.5 rounded-full transition-all"
              :class="token?.enabled ? 'left-4 bg-brand' : 'left-0.5 bg-muted'"
            />
          </button>
        </div>

        <label class="mt-4 flex flex-col gap-1 text-xs text-muted">
          API Token
          <div class="flex items-center gap-2">
            <input
              :type="tokenRevealed ? 'text' : 'password'"
              readonly
              :value="token?.token ?? ''"
              class="min-w-0 flex-1 rounded-control border border-border bg-bg px-2.5 py-1.5 font-mono text-sm text-text outline-none"
            />
            <button
              type="button"
              class="shrink-0 rounded-control border border-border px-2.5 py-1.5 text-xs text-muted transition-colors hover:border-brand hover:text-text"
              @click="tokenRevealed = !tokenRevealed"
            >
              {{ tokenRevealed ? '隐藏' : '显示' }}
            </button>
            <button
              type="button"
              class="shrink-0 rounded-control border border-border px-2.5 py-1.5 text-xs text-muted transition-colors hover:border-brand hover:text-text"
              @click="copyToken()"
            >
              {{ tokenCopied ? '已复制' : '复制' }}
            </button>
          </div>
        </label>

        <p class="mt-3 text-xs text-muted">
          接口地址：<span class="font-mono">{{ openApiBase }}</span> ·
          <a href="/docs" target="_blank" rel="noopener" class="text-brand hover:underline">
            接口文档
          </a>
        </p>
        <p class="mt-1 text-xs text-muted">
          用法：请求头 <span class="font-mono">Authorization: Bearer &lt;token&gt;</span>
          或 <span class="font-mono">X-API-Token: &lt;token&gt;</span>
        </p>

        <div class="mt-3 flex flex-wrap items-center gap-3">
          <button
            type="button"
            class="rounded-control border border-border px-3 py-1.5 text-sm text-muted transition-colors hover:border-danger/60 hover:text-danger disabled:opacity-50"
            :disabled="tokenSaving"
            @click="saveToken({ regenerate: true })"
          >
            重新生成令牌
          </button>
          <span v-if="tokenMessage" class="text-xs text-success">{{ tokenMessage }}</span>
          <span class="ml-auto text-xs" :class="token?.enabled ? 'text-success' : 'text-muted'">
            {{ token?.enabled ? '已启用' : '已停用' }}
          </span>
        </div>
      </section>

      <section class="mb-4 break-inside-avoid rounded-card border border-border bg-surface p-4">
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
