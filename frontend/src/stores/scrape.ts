import { defineStore } from 'pinia'
import { ref } from 'vue'

export type MatchedTrack = {
  id: number
  title: string | null
  artist: string | null
  fields: string[]
  coverApplied: boolean
  lyricsApplied: boolean
}

/** 记录最近一次刮削匹配，供资源库页高亮定位与提示条使用。 */
export const useScrapeStore = defineStore('scrape', () => {
  const lastMatched = ref<MatchedTrack | null>(null)

  function setLastMatched(value: MatchedTrack): void {
    lastMatched.value = value
  }

  function clearLastMatched(): void {
    lastMatched.value = null
  }

  return { lastMatched, setLastMatched, clearLastMatched }
})
