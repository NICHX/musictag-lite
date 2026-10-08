/** 主题与封面取色辅助。 */

export type ThemeName = 'dark' | 'light'

const THEME_KEY = 'musictag.theme'

/** 应用到 <html data-theme>。 */
export function applyTheme(name: ThemeName, root: HTMLElement = document.documentElement): void {
  root.dataset.theme = name
}

/** 运行时注入封面提取的主色，用于高亮/进度/选中态。 */
export function setAccent(color: string, root: HTMLElement = document.documentElement): void {
  root.style.setProperty('--accent-dynamic', color)
}

/** 恢复品牌强调色。 */
export function resetAccent(root: HTMLElement = document.documentElement): void {
  root.style.removeProperty('--accent-dynamic')
}

export function loadTheme(): ThemeName {
  try {
    const stored = localStorage.getItem(THEME_KEY)
    if (stored === 'light' || stored === 'dark') return stored
  } catch {
    /* localStorage 不可用时忽略 */
  }
  return 'dark'
}

export function persistTheme(name: ThemeName): void {
  try {
    localStorage.setItem(THEME_KEY, name)
  } catch {
    /* 忽略 */
  }
}
