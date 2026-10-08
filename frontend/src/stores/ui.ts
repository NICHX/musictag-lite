import { defineStore } from 'pinia'
import { ref } from 'vue'

import { applyTheme, loadTheme, persistTheme, resetAccent, setAccent } from '@/design/theme'
import type { ThemeName } from '@/design/theme'

export const useUiStore = defineStore('ui', () => {
  const theme = ref<ThemeName>('dark')
  const sidebarCollapsed = ref(false)
  const mobileNavOpen = ref(false)
  const taskCenterOpen = ref(false)
  const commandPaletteOpen = ref(false)

  /** 应用启动时初始化主题。 */
  function init(): void {
    theme.value = loadTheme()
    applyTheme(theme.value)
  }

  function toggleTheme(): void {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
    applyTheme(theme.value)
    persistTheme(theme.value)
  }

  function toggleSidebar(): void {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  function toggleMobileNav(value?: boolean): void {
    mobileNavOpen.value = value ?? !mobileNavOpen.value
  }

  function toggleTaskCenter(value?: boolean): void {
    taskCenterOpen.value = value ?? !taskCenterOpen.value
  }

  function toggleCommandPalette(value?: boolean): void {
    commandPaletteOpen.value = value ?? !commandPaletteOpen.value
  }

  /** 封面驱动强调色（检查器滑入/选中时调用）。 */
  function useAccent(color: string | null): void {
    if (color) setAccent(color)
    else resetAccent()
  }

  return {
    theme,
    sidebarCollapsed,
    mobileNavOpen,
    taskCenterOpen,
    commandPaletteOpen,
    init,
    toggleTheme,
    toggleSidebar,
    toggleMobileNav,
    toggleTaskCenter,
    toggleCommandPalette,
    useAccent,
  }
})
